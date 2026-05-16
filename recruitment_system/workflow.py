from __future__ import annotations

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.agents.job_matching import JobMatchingAgent
from recruitment_system.agents.resume_parsing import ResumeParsingAgent
from recruitment_system.models import WorkflowState


class RecruitmentWorkflow:
    """Runs document extraction -> resume parsing -> job matching workflow."""

    def __init__(
        self,
        document_agent: DocumentExtractionAgent | None = None,
        resume_agent: ResumeParsingAgent | None = None,
        matching_agent: JobMatchingAgent | None = None,
    ) -> None:
        self.document_agent = document_agent or DocumentExtractionAgent()
        self.resume_agent = resume_agent or ResumeParsingAgent()
        self.matching_agent = matching_agent or JobMatchingAgent()

    def run(self, resume_input: str, jd_input: str) -> WorkflowState:
        state = WorkflowState(resume_input=resume_input, jd_input=jd_input)

        resume_document = self.document_agent.run(resume_input, "resume")
        jd_document = self.document_agent.run(jd_input, "jd")
        state.resume_document = resume_document
        state.jd_document = jd_document
        state.resume_text = resume_document.extracted_text
        state.jd_text = jd_document.extracted_text

        state.warnings.extend(resume_document.warnings)
        state.warnings.extend(jd_document.warnings)
        state.errors.extend(resume_document.errors)
        state.errors.extend(jd_document.errors)

        if state.errors:
            return state

        if not state.resume_text.strip():
            state.errors.append("resume_text extraction returned empty content")
            return state
        if not state.jd_text.strip():
            state.errors.append("jd_text extraction returned empty content")
            return state

        candidate = self.resume_agent.run(state.resume_text)
        state.candidate_profile = candidate
        if candidate.uncertain_fields:
            state.warnings.append("简历字段不完整：" + ", ".join(candidate.uncertain_fields))

        job, match_result = self.matching_agent.run(candidate, state.jd_text)
        state.job_profile = job
        state.match_result = match_result
        return state
