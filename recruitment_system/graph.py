from __future__ import annotations

from dataclasses import fields
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from recruitment_system.agents.interview_agent import InterviewAgent
from recruitment_system.agents.job_matching_agent import JobMatchingAgent
from recruitment_system.agents.resume_intake_agent import ResumeIntakeAgent
from recruitment_system.agents.resume_parsing_agent import ResumeParsingAgent
from recruitment_system.agents.screening_agent import ScreeningAgent
from recruitment_system.agents.supervisor_agent import SupervisorAgent
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
    RunEvent,
)
from recruitment_system.tracing import RunTracer
from recruitment_system.tools.document_extraction import DocumentExtractionTool


GraphRoute = Literal["continue", "end"]
WORKFLOW_NODE_ORDER = ["resume_intake", "resume_parsing", "jd_extraction", "job_matching", "screening", "interview", "supervisor"]


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
    run_events: list[RunEvent]
    warnings: list[str]
    errors: list[str]


class RecruitmentGraph:
    """LangGraph orchestrator for the multi-agent recruitment pipeline."""

    def __init__(
        self,
        document_tool: DocumentExtractionTool | None = None,
        resume_intake_agent: ResumeIntakeAgent | None = None,
        resume_parsing_agent: ResumeParsingAgent | None = None,
        matching_agent: JobMatchingAgent | None = None,
        screening_agent: ScreeningAgent | None = None,
        interview_agent: InterviewAgent | None = None,
        supervisor_agent: SupervisorAgent | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.document_tool = document_tool or DocumentExtractionTool()
        self.resume_intake_agent = resume_intake_agent or ResumeIntakeAgent(document_tool=self.document_tool)
        self.resume_parsing_agent = resume_parsing_agent or ResumeParsingAgent(llm_client=llm_client)
        self.matching_agent = matching_agent or JobMatchingAgent(llm_client=llm_client)
        self.screening_agent = screening_agent or ScreeningAgent(llm_client=llm_client)
        self.interview_agent = interview_agent or InterviewAgent(llm_client=llm_client)
        self.supervisor_agent = supervisor_agent or SupervisorAgent(llm_client=llm_client)
        self.tracer = RunTracer()
        self.app = self._build_graph("resume_intake").compile()
        self.partial_apps = {node: self._build_graph(node).compile() for node in WORKFLOW_NODE_ORDER}

    def run(self, resume_input: str, jd_input: str) -> WorkflowState:
        """Run the complete recruitment workflow from resume intake."""
        initial = WorkflowState(resume_input=resume_input, jd_input=jd_input)
        result = self.app.invoke(initial.__dict__.copy())
        return self._to_workflow_state(result)

    def run_from_state(self, state: dict[str, Any], entry_node: str) -> WorkflowState:
        """Run the workflow from a specific LangGraph node using restored state.

        This is used by the conversation API for partial reruns, such as updating
        JD matching without re-uploading or re-parsing the resume.
        """
        if entry_node not in self.partial_apps:
            raise ValueError(f"unsupported_graph_entry_node: {entry_node}")
        initial = {
            "resume_input": "",
            "jd_input": "",
            "resume_text": "",
            "jd_text": "",
            "run_events": [],
            "warnings": [],
            "errors": [],
            **state,
        }
        result = self.partial_apps[entry_node].invoke(initial)
        return self._to_workflow_state(result)

    def _build_graph(self, entry_point: str):
        """Build a LangGraph app whose entry point can be the full or partial flow."""
        graph = StateGraph(RecruitmentGraphState)
        graph.add_node("resume_intake", self._resume_intake_node)
        graph.add_node("resume_parsing", self._resume_parsing_node)
        graph.add_node("jd_extraction", self._jd_extraction_node)
        graph.add_node("job_matching", self._job_matching_node)
        graph.add_node("screening", self._screening_node)
        graph.add_node("interview", self._interview_node)
        graph.add_node("supervisor", self._supervisor_node)

        graph.set_entry_point(entry_point)
        graph.add_conditional_edges(
            "resume_intake",
            self._route_after_resume_intake,
            {"continue": "resume_parsing", "end": END},
        )
        graph.add_conditional_edges(
            "resume_parsing",
            self._route_after_resume_parsing,
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
        """Extract raw resume text from the uploaded resume document."""
        started_at, run_events = self.tracer.started(state, "resume_intake")
        warnings = list(state.get("warnings", []))
        errors = list(state.get("errors", []))
        try:
            document, intake_message = self.resume_intake_agent.run(str(state.get("resume_input", "")))
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "resume_intake", started_at, error), "errors": errors + [str(error)]}

        warnings.extend(document.warnings)
        errors.extend(document.errors)
        if intake_message:
            errors.append(intake_message)
        decision = "continue" if not errors else "end"
        completed_state = {**state, "run_events": run_events}

        return {
            "resume_document": document,
            "resume_text": document.extracted_text,
            "warnings": warnings,
            "errors": errors,
            "run_events": self.tracer.completed(
                completed_state,
                "resume_intake",
                started_at,
                decision=decision,
                metadata={
                    "file_type": document.file_type,
                    "confidence": document.confidence,
                    "extracted_chars": len(document.extracted_text),
                },
                warnings=document.warnings,
                errors=errors,
            ),
        }

    def _resume_parsing_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Parse extracted resume text into a structured candidate profile."""
        started_at, run_events = self.tracer.started(state, "resume_parsing")
        warnings = list(state.get("warnings", []))
        errors = list(state.get("errors", []))
        document = state.get("resume_document")
        try:
            candidate = self.resume_parsing_agent.run(str(state.get("resume_text", "")))
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "resume_parsing", started_at, error), "errors": errors + [str(error)]}

        if document is not None and not self.resume_intake_agent.looks_like_resume(candidate, document):
            errors.append("上传内容不像一份简历，请上传包含教育背景、工作经历、项目经历或技能信息的简历文件。")
        if candidate.uncertain_fields:
            warnings.append("简历字段不完整：" + ", ".join(candidate.uncertain_fields))
        decision = "continue" if not errors else "end"

        return {
            "candidate_profile": candidate,
            "warnings": warnings,
            "errors": errors,
            "run_events": self.tracer.completed(
                {**state, "run_events": run_events},
                "resume_parsing",
                started_at,
                decision=decision,
                metadata={
                    "has_candidate": candidate is not None,
                    "skill_count": len(candidate.skills),
                    "uncertain_count": len(candidate.uncertain_fields),
                },
                warnings=warnings,
                errors=errors,
            ),
        }

    def _jd_extraction_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Extract usable JD text before matching."""
        started_at, run_events = self.tracer.started(state, "jd_extraction")
        warnings = list(state.get("warnings", []))
        errors = list(state.get("errors", []))
        try:
            document = self.document_tool.run(str(state.get("jd_input", "")), "jd")
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "jd_extraction", started_at, error), "errors": errors + [str(error)]}

        warnings.extend(document.warnings)
        errors.extend(document.errors)
        if not document.extracted_text.strip():
            errors.append("jd_text extraction returned empty content")
        if state.get("candidate_profile") is None:
            errors.append("candidate_profile was not produced")
        decision = "continue" if not errors else "end"

        return {
            "jd_document": document,
            "jd_text": document.extracted_text,
            "warnings": warnings,
            "errors": errors,
            "run_events": self.tracer.completed(
                {**state, "run_events": run_events},
                "jd_extraction",
                started_at,
                decision=decision,
                metadata={
                    "file_type": document.file_type,
                    "confidence": document.confidence,
                    "extracted_chars": len(document.extracted_text),
                },
                warnings=document.warnings,
                errors=errors,
            ),
        }

    def _job_matching_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Parse the JD and score the candidate against the role."""
        started_at, run_events = self.tracer.started(state, "job_matching")
        candidate = state["candidate_profile"]
        warnings = list(state.get("warnings", []))
        try:
            job, match_result = self.matching_agent.run(candidate, str(state.get("jd_text", "")))
            if candidate.uncertain_fields:
                warnings.append("简历字段不完整：" + ", ".join(candidate.uncertain_fields))
            return {
                "job_profile": job,
                "match_result": match_result,
                "warnings": warnings,
                "run_events": self.tracer.completed(
                    {**state, "run_events": run_events},
                    "job_matching",
                    started_at,
                    decision=str(match_result.match_score),
                    metadata={
                        "match_score": match_result.match_score,
                        "matched_count": len(match_result.matched_requirements),
                        "missing_count": len(match_result.missing_requirements),
                    },
                    warnings=warnings,
                    errors=[],
                ),
            }
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "job_matching", started_at, error), "errors": list(state.get("errors", [])) + [str(error)]}

    def _screening_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Produce the initial screening recommendation."""
        started_at, run_events = self.tracer.started(state, "screening")
        try:
            result = self.screening_agent.run(
                state["candidate_profile"],
                state["job_profile"],
                state["match_result"],
            )
            return {
                "screening_result": result,
                "run_events": self.tracer.completed(
                    {**state, "run_events": run_events},
                    "screening",
                    started_at,
                    decision=result.recommendation,
                    metadata={
                        "confidence": result.confidence,
                        "requires_human_review": result.requires_human_review,
                    },
                    warnings=[],
                    errors=[],
                ),
            }
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "screening", started_at, error), "errors": list(state.get("errors", [])) + [str(error)]}

    def _interview_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate an interview strategy and question plan."""
        started_at, run_events = self.tracer.started(state, "interview")
        try:
            plan = self.interview_agent.run(
                state["candidate_profile"],
                state["job_profile"],
                state["match_result"],
                state["screening_result"],
            )
            return {
                "interview_plan": plan,
                "run_events": self.tracer.completed(
                    {**state, "run_events": run_events},
                    "interview",
                    started_at,
                    decision=plan.selected_strategy,
                    metadata={
                        "question_count": len(plan.questions),
                        "risk_question_count": len(plan.risk_validation_questions),
                        "requires_human_review": plan.requires_human_review,
                    },
                    warnings=[],
                    errors=[],
                ),
            }
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "interview", started_at, error), "errors": list(state.get("errors", [])) + [str(error)]}

    def _supervisor_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Create the final supervisor review for the workflow run."""
        started_at, run_events = self.tracer.started(state, "supervisor")
        try:
            review = self.supervisor_agent.run(
                state["match_result"],
                state["screening_result"],
                state["interview_plan"],
            )
            return {
                "supervisor_review": review,
                "run_events": self.tracer.completed(
                    {**state, "run_events": run_events},
                    "supervisor",
                    started_at,
                    decision=review.final_recommendation,
                    metadata={"human_review_required": review.human_review_required},
                    warnings=[],
                    errors=[],
                ),
            }
        except Exception as error:
            return {"run_events": self.tracer.failed({**state, "run_events": run_events}, "supervisor", started_at, error), "errors": list(state.get("errors", [])) + [str(error)]}

    def _route_after_resume_intake(self, state: dict[str, Any]) -> GraphRoute:
        """Continue only when resume intake produced no errors."""
        return "end" if state.get("errors") else "continue"

    def _route_after_resume_parsing(self, state: dict[str, Any]) -> GraphRoute:
        """Continue only when resume parsing produced a valid candidate profile."""
        return "end" if state.get("errors") else "continue"

    def _route_after_jd_extraction(self, state: dict[str, Any]) -> GraphRoute:
        """Continue only when JD extraction produced no errors."""
        return "end" if state.get("errors") else "continue"

    def _to_workflow_state(self, state: dict[str, Any]) -> WorkflowState:
        """Convert raw LangGraph state into the public WorkflowState dataclass."""
        allowed = {field.name for field in fields(WorkflowState)}
        data = {key: value for key, value in state.items() if key in allowed}
        return WorkflowState(**data)
