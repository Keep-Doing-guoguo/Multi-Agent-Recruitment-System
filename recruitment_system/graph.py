from __future__ import annotations

from dataclasses import fields
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.agents.interview import InterviewAgent
from recruitment_system.agents.job_matching import JobMatchingAgent
from recruitment_system.agents.resume_intake import ResumeIntakeAgent
from recruitment_system.agents.resume_parsing import ResumeParsingAgent
from recruitment_system.agents.screening import ScreeningAgent
from recruitment_system.agents.supervisor import SupervisorAgent
from recruitment_system.llm import StructuredLLMClient
from recruitment_system.models import (
    CandidateProfile,
    DocumentExtractionResult,
    InterviewPlan,
    JobProfile,
    MatchResult,
    ScreeningResult,
    SupervisorReview,
    WorkflowState,
)


GraphRoute = Literal["continue", "end"]


class RecruitmentGraphState(TypedDict, total=False):
    resume_input: str
    jd_input: str
    resume_text: str
    jd_text: str
    session_id: str
    run_id: str
    resume_document: DocumentExtractionResult | None
    jd_document: DocumentExtractionResult | None
    candidate_profile: CandidateProfile | None
    job_profile: JobProfile | None
    match_result: MatchResult | None
    screening_result: ScreeningResult | None
    interview_plan: InterviewPlan | None
    supervisor_review: SupervisorReview | None
    warnings: list[str]
    errors: list[str]


class RecruitmentGraph:
    """LangGraph orchestrator for the multi-agent recruitment pipeline."""

    def __init__(
        self,
        document_agent: DocumentExtractionAgent | None = None,
        resume_intake_agent: ResumeIntakeAgent | None = None,
        matching_agent: JobMatchingAgent | None = None,
        screening_agent: ScreeningAgent | None = None,
        interview_agent: InterviewAgent | None = None,
        supervisor_agent: SupervisorAgent | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.document_agent = document_agent or DocumentExtractionAgent()
        self.resume_intake_agent = resume_intake_agent or ResumeIntakeAgent(
            document_agent=self.document_agent,
            resume_agent=ResumeParsingAgent(llm_client=llm_client),
        )
        self.matching_agent = matching_agent or JobMatchingAgent(llm_client=llm_client)
        self.screening_agent = screening_agent or ScreeningAgent(llm_client=llm_client)
        self.interview_agent = interview_agent or InterviewAgent(llm_client=llm_client)
        self.supervisor_agent = supervisor_agent or SupervisorAgent(llm_client=llm_client)
        self.app = self._build_graph().compile()

    def run(self, resume_input: str, jd_input: str) -> WorkflowState:
        initial = WorkflowState(resume_input=resume_input, jd_input=jd_input)
        result = self.app.invoke(initial.__dict__.copy())
        return self._to_workflow_state(result)

    def _build_graph(self):
        graph = StateGraph(RecruitmentGraphState)
        graph.add_node("resume_intake", self._resume_intake_node)
        graph.add_node("jd_extraction", self._jd_extraction_node)
        graph.add_node("job_matching", self._job_matching_node)
        graph.add_node("screening", self._screening_node)
        graph.add_node("interview", self._interview_node)
        graph.add_node("supervisor", self._supervisor_node)

        graph.set_entry_point("resume_intake")
        graph.add_conditional_edges(
            "resume_intake",
            self._route_after_resume_intake,
            {"continue": "jd_extraction", "end": END},
        )
        graph.add_conditional_edges(
            "jd_extraction",
            self._route_after_jd_extraction,
            {"continue": "job_matching", "end": END},
        )
        graph.add_edge("job_matching", "screening")
        graph.add_edge("screening", "interview")
        graph.add_edge("interview", "supervisor")
        graph.add_edge("supervisor", END)
        return graph

    def _resume_intake_node(self, state: dict[str, Any]) -> dict[str, Any]:
        warnings = list(state.get("warnings", []))
        errors = list(state.get("errors", []))
        document, candidate, intake_message = self.resume_intake_agent.run(str(state.get("resume_input", "")))

        warnings.extend(document.warnings)
        errors.extend(document.errors)
        if intake_message:
            errors.append(intake_message)

        return {
            "resume_document": document,
            "resume_text": document.extracted_text,
            "candidate_profile": candidate,
            "warnings": warnings,
            "errors": errors,
        }

    def _jd_extraction_node(self, state: dict[str, Any]) -> dict[str, Any]:
        warnings = list(state.get("warnings", []))
        errors = list(state.get("errors", []))
        document = self.document_agent.run(str(state.get("jd_input", "")), "jd")

        warnings.extend(document.warnings)
        errors.extend(document.errors)
        if not document.extracted_text.strip():
            errors.append("jd_text extraction returned empty content")
        if state.get("candidate_profile") is None:
            errors.append("candidate_profile was not produced")

        return {
            "jd_document": document,
            "jd_text": document.extracted_text,
            "warnings": warnings,
            "errors": errors,
        }

    def _job_matching_node(self, state: dict[str, Any]) -> dict[str, Any]:
        candidate = state["candidate_profile"]
        job, match_result = self.matching_agent.run(candidate, str(state.get("jd_text", "")))
        warnings = list(state.get("warnings", []))
        if candidate.uncertain_fields:
            warnings.append("简历字段不完整：" + ", ".join(candidate.uncertain_fields))
        return {"job_profile": job, "match_result": match_result, "warnings": warnings}

    def _screening_node(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "screening_result": self.screening_agent.run(
                state["candidate_profile"],
                state["job_profile"],
                state["match_result"],
            )
        }

    def _interview_node(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "interview_plan": self.interview_agent.run(
                state["candidate_profile"],
                state["job_profile"],
                state["match_result"],
                state["screening_result"],
            )
        }

    def _supervisor_node(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "supervisor_review": self.supervisor_agent.run(
                state["match_result"],
                state["screening_result"],
                state["interview_plan"],
            )
        }

    def _route_after_resume_intake(self, state: dict[str, Any]) -> GraphRoute:
        return "end" if state.get("errors") else "continue"

    def _route_after_jd_extraction(self, state: dict[str, Any]) -> GraphRoute:
        return "end" if state.get("errors") else "continue"

    def _to_workflow_state(self, state: dict[str, Any]) -> WorkflowState:
        allowed = {field.name for field in fields(WorkflowState)}
        data = {key: value for key, value in state.items() if key in allowed}
        return WorkflowState(**data)
