from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from recruitment_system.config import env_flag
from recruitment_system.services.message_service import MessageRoutingService
from recruitment_system.services.resume_service import ResumeParsingService
from recruitment_system.storage import ConversationStore


app = FastAPI(title="Multi-Agent Recruitment System API")


DEFAULT_ALGORITHM_ENGINEER_JD = """职位: 算法工程师

岗位职责:
- 负责机器学习、深度学习或大模型相关算法的设计、训练、评估和上线
- 结合业务场景完成特征工程、模型优化、效果分析和实验迭代
- 与后端、数据工程和产品团队协作，推动算法能力落地到实际系统
- 维护模型评估指标、实验记录和线上效果监控

岗位要求:
- 本科及以上学历，计算机、人工智能、数学、统计学或相关专业
- 3 年以上算法工程或机器学习项目经验
- 熟悉 Python、PyTorch 或 TensorFlow，具备扎实的数据结构和算法基础
- 熟悉机器学习基础模型、深度学习模型、NLP/CV/推荐系统中的至少一个方向
- 具备数据处理、模型训练、模型调参、模型部署和效果评估经验

加分项:
- 有大模型、RAG、向量检索、推荐系统或搜索排序经验
- 熟悉 Docker、Linux、FastAPI、模型服务化或 MLOps 流程
- 有真实业务场景中的算法上线和 A/B 测试经验"""


class ConversationMessageJsonRequest(BaseModel):
    """JSON request for messages after a conversation already exists."""

    message: str
    jd_input: str | None = None
    conversation_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal API health response."""
    return {"status": "ok"}


@app.post("/api/resume/parse")
async def parse_resume(file: UploadFile = File(...)) -> dict:
    """Parse a standalone uploaded resume file without running the full workflow."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空")

    service = ResumeParsingService()
    return service.parse_uploaded_file(file.filename or "resume.txt", content)


@app.post("/api/conversations")
def create_conversation(title: str = "招聘会话") -> dict:
    """Create an empty persisted conversation record."""
    store = ConversationStore()
    return {"success": True, "conversation": store.create_conversation(title=title)}


@app.get("/api/conversations")
def list_conversations(limit: int = 50) -> dict:
    """List recent conversations ordered by last update time."""
    store = ConversationStore()
    return {"success": True, "conversations": store.list_conversations(limit=limit)}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    """Return one conversation with its persisted message history."""
    store = ConversationStore()
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation 不存在")
    return {
        "success": True,
        "conversation": conversation,
        "messages": store.list_messages(conversation_id),
    }


@app.post("/api/conversation/message")
async def handle_conversation_message(
    message: str = Form("请分析这份简历是否匹配这个岗位"),
    resume_file: UploadFile | None = File(None),
    jd_input: str | None = Form(DEFAULT_ALGORITHM_ENGINEER_JD),
    conversation_id: str | None = Form(None),
) -> dict:
    """Handle the file-upload conversation entrypoint.

    First business requests must upload a resume file. Follow-up requests can pass
    only conversation_id and optional jd_input; the previous state is restored
    from the database.
    """
    message = message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")
    if not conversation_id and resume_file is None:
        raise HTTPException(status_code=400, detail="首次招聘分析必须上传 resume_file")

    payload: dict[str, Any] = {
        "message": message,
        "conversation_id": conversation_id,
        "jd_input": jd_input,
    }

    temp_resume_path = await _save_upload_to_temp_file(resume_file)
    if resume_file is not None:
        payload["resume_filename"] = resume_file.filename

    try:
        return _handle_message_payload(payload, temp_resume_path)
    finally:
        if temp_resume_path is not None:
            Path(temp_resume_path).unlink(missing_ok=True)


@app.post("/api/conversation/message/json")
def handle_conversation_message_json(request: ConversationMessageJsonRequest) -> dict:
    """Handle JSON follow-up messages for an existing conversation."""
    payload = _model_to_dict(request)
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")
    if not payload.get("conversation_id"):
        raise HTTPException(status_code=400, detail="JSON 消息接口必须提供 conversation_id；首次招聘分析请使用 resume_file 上传接口")
    return _handle_message_payload(payload)


def _handle_message_payload(payload: dict[str, Any], temp_resume_path: str | None = None) -> dict:
    """Persist the user message, route it, run the graph, and persist the result."""
    store = ConversationStore()
    conversation_id = str(payload.get("conversation_id") or "").strip()

    if conversation_id:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation 不存在")
        state = dict(conversation["current_state"])
    else:
        conversation = store.create_conversation(title=_conversation_title(str(payload.get("message") or "")))
        conversation_id = conversation["id"]
        state: dict[str, Any] = {}

    run_id = str(uuid4())
    resume_input = temp_resume_path
    jd_input = payload.get("jd_input")
    store.add_message(
        conversation_id=conversation_id,
        role="user",
        content=str(payload.get("message") or ""),
        message_type="user_message",
        run_id=run_id,
        payload={
            "has_resume_file": temp_resume_path is not None,
            "resume_filename": payload.get("resume_filename"),
            "has_jd_input": bool(jd_input),
        },
    )

    try:
        service = MessageRoutingService.from_env(use_llm=env_flag("ENABLE_LLM", False))
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    response = service.handle_message(
        message=str(payload.get("message") or ""),
        conversation_state=state,
        resume_input=resume_input,
        jd_input=jd_input,
        run_id=run_id,
    )
    response["conversation_id"] = conversation_id

    store.update_conversation_state(conversation_id, response.get("conversation_state", {}))
    store.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=str(response.get("message") or ""),
        message_type="agent_result",
        run_id=run_id,
        route=response.get("route_decision", {}).get("route"),
        payload=response,
    )
    return response


async def _save_upload_to_temp_file(upload: UploadFile | None) -> str | None:
    """Save an uploaded resume to a temporary file and return its path."""
    if upload is None:
        return None
    content = await upload.read()
    await upload.close()
    if not content:
        raise HTTPException(status_code=400, detail="resume_file 不能为空")
    suffix = Path(upload.filename or "resume.txt").suffix or ".txt"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        return temp_file.name


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Convert Pydantic v1 or v2 models into plain dictionaries."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _conversation_title(message: str) -> str:
    """Create a short conversation title from the initial user message."""
    title = message.strip().replace("\n", " ")
    return title[:40] or "招聘会话"
