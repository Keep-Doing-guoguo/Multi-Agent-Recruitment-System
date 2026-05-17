from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from recruitment_system.agents.resume_parsing_agent import ResumeParsingAgent
from recruitment_system.agents.resume_intake_agent import ResumeIntakeAgent
from recruitment_system.config import LLMConfig
from recruitment_system.llm import ArkMultimodalExtractor
from recruitment_system.tools.document_extraction import DocumentExtractionTool


class ResumeParsingService:
    """Runs the upload-file resume parsing use case."""

    def __init__(
        self,
        document_tool: DocumentExtractionTool | None = None,
        resume_agent: ResumeParsingAgent | None = None,
    ) -> None:
        self.document_tool = document_tool or self._default_document_tool()
        self.resume_agent = resume_agent or ResumeParsingAgent()
        self.resume_intake_agent = ResumeIntakeAgent(
            document_tool=self.document_tool,
        )

    def parse_uploaded_file(self, filename: str, content: bytes) -> dict:
        suffix = Path(filename).suffix or ".txt"
        with NamedTemporaryFile(delete=True, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            document, intake_message = self.resume_intake_agent.run(temp_file.name)

        if document.errors:
            return {
                "success": False,
                "message": "简历文件解析失败",
                "errors": document.errors,
                "document": asdict(document),
            }

        if intake_message:
            return {
                "success": False,
                "message": intake_message,
                "document": asdict(document),
            }

        candidate = self.resume_agent.run(document.extracted_text)
        if not self.resume_intake_agent.looks_like_resume(candidate, document):
            return {
                "success": False,
                "message": "上传内容不像一份简历，请上传包含教育背景、工作经历、项目经历或技能信息的简历文件。",
                "document": asdict(document),
            }

        if candidate is None:
            return {
                "success": False,
                "message": "简历解析未生成候选人画像",
                "document": asdict(document),
            }

        return {
            "success": True,
            "message": "简历解析成功",
            "data": {
                "candidate_profile": asdict(candidate),
                "document": asdict(document),
            },
        }

    def _default_document_tool(self) -> DocumentExtractionTool:
        config = LLMConfig.from_env()
        if config.api_key:
            return DocumentExtractionTool(multimodal_extractor=ArkMultimodalExtractor(config=config))
        return DocumentExtractionTool()
