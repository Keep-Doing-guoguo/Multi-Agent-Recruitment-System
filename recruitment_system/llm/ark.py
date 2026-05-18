from __future__ import annotations

import base64
import json
import mimetypes
import uuid
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from recruitment_system.config import LLMConfig
from recruitment_system.llm.base import StructuredLLMClient, parse_json_object
from recruitment_system.models import DocumentExtractionResult, DocumentPurpose
from recruitment_system.tools.document_extraction import MultimodalExtractor


class ArkResponsesClient:
    """火山方舟 Responses API 和 Files API 的轻量客户端。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        """初始化 Ark 客户端配置，并确保 API Key 已配置。"""
        self.config = config or LLMConfig.from_env()
        if not self.config.api_key:
            raise ValueError("LLM_API_KEY is required")

    def create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用 Responses API 创建一次模型响应。"""
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.config.responses_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        # 对网络错误、HTTP 错误和超时做有限重试，避免瞬时故障直接中断 workflow。
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError) as error:
                last_error = error
                if attempt >= self.config.max_retries:
                    break
                time.sleep(2**attempt)

        raise RuntimeError(f"Ark response request failed: {last_error}") from last_error

    def upload_file(self, file_path: str | Path, purpose: str = "user_data") -> dict[str, Any]:
        """把本地文件上传到 Ark Files API，并返回文件对象。"""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))

        boundary = f"----ark-form-{uuid.uuid4().hex}"
        body = self._multipart_body(
            boundary=boundary,
            fields={"purpose": purpose},
            file_field="file",
            file_path=path,
        )
        request = Request(
            self.config.files_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        # Files API 可能因为网络或限流短暂失败，这里沿用 Responses API 的重试策略。
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError) as error:
                last_error = error
                if attempt >= self.config.max_retries:
                    break
                time.sleep(2**attempt)

        raise RuntimeError(f"Ark file upload failed: {last_error}") from last_error

    def _multipart_body(
        self,
        boundary: str,
        fields: dict[str, str],
        file_field: str,
        file_path: Path,
    ) -> bytes:
        """构造 multipart/form-data 请求体，用于上传一个文件和若干文本字段。"""
        lines: list[bytes] = []
        for name, value in fields.items():
            lines.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        lines.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{file_field}"; '
                    f'filename="{file_path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_path.read_bytes(),
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        return b"".join(lines)


class ArkStructuredLLMClient(StructuredLLMClient):
    """基于 Ark Responses API 的结构化 JSON 生成客户端。"""

    def __init__(self, client: ArkResponsesClient | None = None, config: LLMConfig | None = None) -> None:
        """初始化结构化 LLM 客户端，可注入假的 Ark 客户端用于测试。"""
        self.config = config or LLMConfig.from_env()
        self.client = client or ArkResponsesClient(self.config)

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        """让模型按 prompt 生成 JSON，并解析成 Python dict。"""
        payload = {
            "model": self.config.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=False)}],
                },
            ],
        }
        response = self.client.create_response(payload)
        return parse_json_object(extract_response_text(response))


class ArkMultimodalExtractor(MultimodalExtractor):
    """使用 Ark 多模态模型把简历/JD 文件提取成纯文本。"""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    def __init__(self, client: ArkResponsesClient | None = None, config: LLMConfig | None = None) -> None:
        """初始化多模态提取器，可复用同一个 Ark 客户端。"""
        self.config = config or LLMConfig.from_env()
        self.client = client or ArkResponsesClient(self.config)

    def extract(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """根据输入类型选择 image 或 file 协议，并返回标准化文档提取结果。"""
        source_text = str(source)
        try:
            input_content = self._input_content_for(source)
            payload = {
                "model": self.config.multimodal_model,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            input_content,
                            {
                                "type": "input_text",
                                "text": self._prompt_for(purpose),
                            },
                        ],
                    }
                ],
            }
            response = self.client.create_response(payload)
            extracted_text = extract_response_text(response)
            return DocumentExtractionResult(
                source=source_text,
                purpose=purpose,
                file_type=self._file_type(source),
                extracted_text=extracted_text,
                confidence=0.8 if extracted_text else 0.0,
                warnings=[] if extracted_text else ["多模态模型未返回可用文本"],
            )
        except Exception as error:
            # 文档提取工具的契约是不向上抛出 provider 异常，而是把错误写入结果。
            return DocumentExtractionResult(
                source=source_text,
                purpose=purpose,
                file_type=self._file_type(source),
                confidence=0.0,
                errors=[f"multimodal_extraction_failed: {error}"],
            )

    def _prompt_for(self, purpose: DocumentPurpose) -> str:
        """根据文档用途生成提取提示词。"""
        if purpose == "resume":
            return (
                "请从这份简历文件中提取所有有效内容，保留姓名、联系方式、教育背景、工作经历、"
                "项目经历、技能、证书、年限等信息。只输出可用于后续结构化解析的纯文本，不要输出解释。"
            )
        return "请从这份岗位 JD 文件中提取岗位名称、职责、必备要求、加分项、年限和学历要求。只输出纯文本，不要输出解释。"

    def _input_content_for(self, source: str | Path) -> dict[str, str]:
        """把本地路径或远程 URL 转成 Responses API 的 input_image 或 input_file 内容块。"""
        source_text = str(source)
        parsed = urlparse(source_text)
        if parsed.scheme in {"http", "https"}:
            # 图片 URL 走 input_image；PDF、DOCX 等远程文档 URL 走 input_file.file_url。
            if self._is_image_source(source_text):
                return {"type": "input_image", "image_url": source_text}
            return {"type": "input_file", "file_url": source_text}

        path = Path(source)
        if self._is_image_source(path.name):
            # 本地图片不需要先上传，直接转成 data URL 后作为 input_image 传入。
            return {"type": "input_image", "image_url": self._to_image_data_url(path)}

        # 本地 PDF、DOCX、TXT 等文档需要先上传 Files API，再用 file_id 传给模型。
        uploaded = self.client.upload_file(path, purpose="user_data")
        file_id = uploaded.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise ValueError("Ark file upload did not return a file id")
        return {"type": "input_file", "file_id": file_id}

    def _to_image_data_url(self, path: Path) -> str:
        """把本地图片文件编码成 Responses API 可接受的 base64 data URL。"""
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _is_image_source(self, source: str) -> bool:
        """通过 URL path 或文件名后缀判断输入是否为图片。"""
        suffix = Path(urlparse(source).path).suffix.lower()
        return suffix in self.IMAGE_EXTENSIONS

    def _file_type(self, source: str | Path) -> str:
        """从本地路径或 URL 中提取文件类型，用于写入 DocumentExtractionResult。"""
        source_text = str(source)
        parsed = urlparse(source_text)
        suffix = Path(parsed.path if parsed.scheme else source_text).suffix.lower()
        return suffix.lstrip(".") or ("url" if parsed.scheme else "unknown")

def extract_response_text(response: dict[str, Any]) -> str:
    """从 Ark Responses API 返回体中提取模型输出文本。"""
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()

    texts: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(texts).strip()
