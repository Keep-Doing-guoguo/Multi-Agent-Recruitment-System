from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from recruitment_system.models import CandidateProfile, DocumentExtractionResult
from recruitment_system.tools.document_extraction import DocumentExtractionTool, ExtractionMethod


class ResumeIntakeAgent:
    """处理简历输入、解析方式选择和原始文本提取。"""

    def __init__(
        self,
        document_tool: DocumentExtractionTool | None = None,
    ) -> None:
        """初始化简历接收 Agent，可注入文档提取工具。"""
        self.document_tool = document_tool or DocumentExtractionTool()

    def run(self, resume_input: str) -> tuple[DocumentExtractionResult, str | None]:
        """从上传文件、URL 或内联文本中提取简历原文。"""
        source_type = self._detect_source_type(resume_input)
        method = self._choose_extraction_method(source_type, resume_input)
        document = self.document_tool.extract(resume_input, "resume", method)
        if document.errors:
            return document, None
        if not document.extracted_text.strip():
            return document, "未能从文件中提取到有效文本"
        return document, None

    def _detect_source_type(self, resume_input: str) -> str:
        """在选择工具前识别输入来源类型。"""
        if not resume_input.strip():
            return "empty"
        parsed = urlparse(resume_input)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            suffix = Path(parsed.path).suffix.lower().lstrip(".")
            return suffix or "url"
        path = Path(resume_input)
        if path.exists() and path.is_file():
            return path.suffix.lower().lstrip(".") or "file"
        return "inline_text"

    def _choose_extraction_method(self, source_type: str, resume_input: str) -> ExtractionMethod:
        """根据来源类型选择具体的文档提取方式。"""
        if source_type == "empty":
            return "unsupported"
        if source_type == "inline_text":
            return "inline_text"
        if source_type in {"txt", "md", "markdown", "csv", "json"}:
            return "text"
        if source_type == "pdf":
            return "pdf"
        if source_type == "docx":
            return "docx"
        if source_type in {"url", "png", "jpg", "jpeg", "webp", "gif", "bmp"}:
            return "multimodal"
        return self.document_tool.choose_default_method(resume_input)

    def looks_like_resume(self, candidate: CandidateProfile, document: DocumentExtractionResult) -> bool:
        """根据结构化字段和文本信号判断内容是否像简历。"""
        text = document.extracted_text.lower()
        signals = 0
        if candidate.email or candidate.phone:
            signals += 1
        if candidate.skills:
            signals += 1
        if candidate.years_experience is not None:
            signals += 1
        if candidate.education_level != "unknown":
            signals += 1
        if candidate.projects or candidate.work_experience:
            signals += 1
        if any(keyword in text for keyword in ("简历", "工作经历", "项目经历", "教育背景", "resume", "experience", "education")):
            signals += 1
        return signals >= 2
