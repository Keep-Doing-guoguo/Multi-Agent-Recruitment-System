from __future__ import annotations

import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from recruitment_system.agents.document_extraction import MultimodalExtractor
from recruitment_system.config import LLMConfig
from recruitment_system.llm.base import StructuredLLMClient, parse_json_object
from recruitment_system.models import DocumentExtractionResult, DocumentPurpose


class ArkResponsesClient:
    """Small stdlib client for Volcengine Ark Responses API."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        if not self.config.api_key:
            raise ValueError("LLM_API_KEY is required")

    def create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
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


class ArkStructuredLLMClient(StructuredLLMClient):
    """Structured JSON client backed by Ark Responses API."""

    def __init__(self, client: ArkResponsesClient | None = None, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self.client = client or ArkResponsesClient(self.config)

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
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
    """Uses Ark multimodal model to extract useful resume/JD content."""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    def __init__(self, client: ArkResponsesClient | None = None, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self.client = client or ArkResponsesClient(self.config)

    def extract(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        source_text = str(source)
        try:
            image_url = self._to_image_url(source)
            payload = {
                "model": self.config.multimodal_model,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": image_url,
                            },
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
            return DocumentExtractionResult(
                source=source_text,
                purpose=purpose,
                file_type=self._file_type(source),
                confidence=0.0,
                errors=[f"multimodal_extraction_failed: {error}"],
            )

    def _prompt_for(self, purpose: DocumentPurpose) -> str:
        if purpose == "resume":
            return (
                "请从这份简历图片中提取所有有效内容，保留姓名、联系方式、教育背景、工作经历、"
                "项目经历、技能、证书、年限等信息。只输出可用于后续结构化解析的纯文本，不要输出解释。"
            )
        return "请从这份岗位 JD 图片中提取岗位名称、职责、必备要求、加分项、年限和学历要求。只输出纯文本，不要输出解释。"

    def _to_image_url(self, source: str | Path) -> str:
        source_text = str(source)
        parsed = urlparse(source_text)
        if parsed.scheme in {"http", "https"}:
            return source_text

        path = Path(source)
        suffix = path.suffix.lower()
        if suffix not in self.IMAGE_EXTENSIONS:
            raise ValueError(f"unsupported_multimodal_file_type: {suffix or 'unknown'}")
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _file_type(self, source: str | Path) -> str:
        source_text = str(source)
        parsed = urlparse(source_text)
        suffix = Path(parsed.path if parsed.scheme else source_text).suffix.lower()
        return suffix.lstrip(".") or ("url" if parsed.scheme else "unknown")

def extract_response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()

    texts: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(texts).strip()
