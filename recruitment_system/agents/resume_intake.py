from __future__ import annotations

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.agents.resume_parsing import ResumeParsingAgent
from recruitment_system.models import CandidateProfile, DocumentExtractionResult


class ResumeIntakeAgent:
    """Handles resume input, extraction, and resume-likeness classification."""

    def __init__(
        self,
        document_agent: DocumentExtractionAgent | None = None,
        resume_agent: ResumeParsingAgent | None = None,
    ) -> None:
        self.document_agent = document_agent or DocumentExtractionAgent()
        self.resume_agent = resume_agent or ResumeParsingAgent()

    def run(self, resume_input: str) -> tuple[DocumentExtractionResult, CandidateProfile | None, str | None]:
        document = self.document_agent.run(resume_input, "resume")
        if document.errors:
            return document, None, None
        if not document.extracted_text.strip():
            return document, None, "未能从文件中提取到有效文本"

        candidate = self.resume_agent.run(document.extracted_text)
        if not self._looks_like_resume(candidate, document):
            return document, None, "上传内容不像一份简历，请上传包含教育背景、工作经历、项目经历或技能信息的简历文件。"
        return document, candidate, None

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
