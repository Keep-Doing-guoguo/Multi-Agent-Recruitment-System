from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.agents.resume_parsing import ResumeParsingAgent
from recruitment_system.config import LLMConfig
from recruitment_system.llm import ArkMultimodalExtractor
from recruitment_system.models import CandidateProfile, DocumentExtractionResult


class ResumeParsingService:
    """Runs the upload-file resume parsing use case."""

    def __init__(
        self,
        document_agent: DocumentExtractionAgent | None = None,
        resume_agent: ResumeParsingAgent | None = None,
    ) -> None:
        self.document_agent = document_agent or self._default_document_agent()
        self.resume_agent = resume_agent or ResumeParsingAgent()

    def parse_uploaded_file(self, filename: str, content: bytes) -> dict:
        suffix = Path(filename).suffix or ".txt"
        with NamedTemporaryFile(delete=True, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            document = self.document_agent.run(temp_file.name, "resume")

        if document.errors:
            return {
                "success": False,
                "message": "简历文件解析失败",
                "errors": document.errors,
                "document": asdict(document),
            }

        if not document.extracted_text.strip():
            return {
                "success": False,
                "message": "未能从文件中提取到有效文本",
                "document": asdict(document),
            }

        candidate = self.resume_agent.run(document.extracted_text)
        if not self._looks_like_resume(candidate, document):
            return {
                "success": False,
                "message": "上传内容不像一份简历，请上传包含教育背景、工作经历、项目经历或技能信息的简历文件。",
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

    def _default_document_agent(self) -> DocumentExtractionAgent:
        config = LLMConfig.from_env()
        if config.api_key:
            return DocumentExtractionAgent(multimodal_extractor=ArkMultimodalExtractor(config=config))
        return DocumentExtractionAgent()

    def _looks_like_resume(self, candidate: CandidateProfile, document: DocumentExtractionResult) -> bool:
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
