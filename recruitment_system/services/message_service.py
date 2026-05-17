from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import Any

from recruitment_system.agents import (
    DirectAnswerAgent,
    InterviewAgent,
    JobMatchingAgent,
    MessageRouterAgent,
    ResumeIntakeAgent,
    ScreeningAgent,
    StateAnswerAgent,
    SupervisorAgent,
)
from recruitment_system.config import LLMConfig
from recruitment_system.graph import RecruitmentGraph
from recruitment_system.llm import ArkMultimodalExtractor, ArkStructuredLLMClient, StructuredLLMClient
from recruitment_system.models import (
    CandidateProfile,
    InterviewPlan,
    InterviewQuestion,
    JobProfile,
    MatchResult,
    MessageRouteDecision,
    ScreeningResult,
    SupervisorReview,
    WorkflowState,
)
from recruitment_system.tools.document_extraction import DocumentExtractionTool


class MessageRoutingService:
    """Routes conversation messages into recruitment business agents when needed."""

    def __init__(
        self,
        router_agent: MessageRouterAgent | None = None,
        document_tool: DocumentExtractionTool | None = None,
        resume_intake_agent: ResumeIntakeAgent | None = None,
        matching_agent: JobMatchingAgent | None = None,
        screening_agent: ScreeningAgent | None = None,
        interview_agent: InterviewAgent | None = None,
        supervisor_agent: SupervisorAgent | None = None,
        state_answer_agent: StateAnswerAgent | None = None,
        direct_answer_agent: DirectAnswerAgent | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.document_tool = document_tool or self._default_document_tool()
        self.router_agent = router_agent or MessageRouterAgent(llm_client=llm_client)
        self.resume_intake_agent = resume_intake_agent or ResumeIntakeAgent(document_tool=self.document_tool)
        self.matching_agent = matching_agent or JobMatchingAgent(llm_client=llm_client)
        self.screening_agent = screening_agent or ScreeningAgent(llm_client=llm_client)
        self.interview_agent = interview_agent or InterviewAgent(llm_client=llm_client)
        self.supervisor_agent = supervisor_agent or SupervisorAgent(llm_client=llm_client)
        self.state_answer_agent = state_answer_agent or StateAnswerAgent(llm_client=llm_client)
        self.direct_answer_agent = direct_answer_agent or DirectAnswerAgent(llm_client=llm_client)
        self.graph = RecruitmentGraph(
            document_tool=self.document_tool,
            resume_intake_agent=self.resume_intake_agent,
            matching_agent=self.matching_agent,
            screening_agent=self.screening_agent,
            interview_agent=self.interview_agent,
            supervisor_agent=self.supervisor_agent,
            llm_client=llm_client,
        )

    @classmethod
    def from_env(cls, use_llm: bool = False) -> "MessageRoutingService":
        """Create the service using environment-based LLM configuration."""
        llm_client: StructuredLLMClient | None = None
        if use_llm:
            config = LLMConfig.from_env()
            if not config.api_key:
                raise ValueError("ENABLE_LLM=true requires LLM_API_KEY")
            llm_client = ArkStructuredLLMClient(config=config)
        return cls(llm_client=llm_client)

    def handle_message(
        self,
        message: str,
        conversation_state: dict[str, Any] | None = None,
        resume_input: str | None = None,
        jd_input: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Route one conversation message and execute the selected graph path."""
        state = dict(conversation_state or {})
        if resume_input:
            state["resume_input"] = resume_input
        if jd_input:
            state["jd_input"] = jd_input
        if run_id:
            state["run_id"] = run_id

        decision = self.router_agent.run(message, state)
        if decision.route == "answer_from_state":
            return self._response(True, decision, self.state_answer_agent.run(message, state), state=state, run_id=run_id)
        if decision.route == "direct_answer":
            return self._response(True, decision, self.direct_answer_agent.run(message, state), state=state, run_id=run_id)

        workflow_state = self._run_graph(decision, state)
        updated_state = self._workflow_state_to_dict(workflow_state)
        success = not workflow_state.errors
        response_message = "消息已通过 LangGraph 路由到对应业务节点并完成处理。"
        if workflow_state.errors:
            response_message = "业务 Graph 执行失败：" + "; ".join(workflow_state.errors)

        return self._response(
            success,
            decision,
            response_message,
            data=self._selected_data(decision, updated_state),
            state=updated_state,
            run_id=run_id,
        )

    def _run_graph(self, decision: MessageRouteDecision, state: dict[str, Any]) -> WorkflowState:
        """Execute LangGraph from the route decision's first workflow node."""
        nodes = decision.required_nodes or [decision.route]
        entry_node = nodes[0]
        if entry_node == "job_matching" and state.get("jd_input"):
            entry_node = "jd_extraction"
        graph_state = self._prepare_graph_state(state)
        return self.graph.run_from_state(graph_state, entry_node)

    def _prepare_graph_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Restore persisted dict state into dataclass objects expected by agents."""
        graph_state = dict(state)
        for key, cls in (
            ("candidate_profile", CandidateProfile),
            ("job_profile", JobProfile),
            ("match_result", MatchResult),
            ("screening_result", ScreeningResult),
            ("interview_plan", InterviewPlan),
            ("supervisor_review", SupervisorReview),
        ):
            value = self._get_dataclass(graph_state, key, cls)
            if value is not None:
                graph_state[key] = value
        return graph_state

    def _workflow_state_to_dict(self, workflow_state: WorkflowState) -> dict[str, Any]:
        """Convert WorkflowState into JSON-safe conversation state."""
        state = self._jsonable(workflow_state)
        state.pop("resume_input", None)
        state.pop("jd_input", None)
        return state

    def _get_dataclass(self, state: dict[str, Any], key: str, cls: type[Any]) -> Any | None:
        """Read a state value and restore it to the requested dataclass type."""
        value = state.get(key)
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return None
        return self._from_dict(cls, value)

    def _from_dict(self, cls: type[Any], value: dict[str, Any]) -> Any:
        """Build a dataclass from persisted JSON data, including nested questions."""
        allowed = {field.name for field in fields(cls)}
        data = {key: item for key, item in value.items() if key in allowed}
        if cls is InterviewPlan:
            data["questions"] = [self._from_dict(InterviewQuestion, item) for item in data.get("questions", []) if isinstance(item, dict)]
            data["risk_validation_questions"] = [
                self._from_dict(InterviewQuestion, item)
                for item in data.get("risk_validation_questions", [])
                if isinstance(item, dict)
            ]
        return cls(**data)

    def _selected_data(self, decision: MessageRouteDecision, state: dict[str, Any]) -> dict[str, Any]:
        """Return the response data most relevant to the selected route."""
        keys_by_route = {
            "resume_intake": ["resume_document", "candidate_profile"],
            "job_matching": ["job_profile", "match_result", "screening_result", "interview_plan", "supervisor_review"],
            "screening": ["screening_result", "interview_plan", "supervisor_review"],
            "interview": ["interview_plan", "supervisor_review"],
            "supervisor": ["supervisor_review"],
        }
        keys = keys_by_route.get(decision.route, [])
        return {key: state[key] for key in keys if key in state}

    def _response(
        self,
        success: bool,
        decision: MessageRouteDecision,
        message: str,
        data: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Create the API response envelope for routed message handling."""
        return {
            "success": success,
            "message": message,
            "run_id": run_id,
            "route_decision": asdict(decision),
            "data": self._jsonable(data or {}),
            "conversation_state": self._jsonable(state or {}),
        }

    def _jsonable(self, value: Any) -> Any:
        """Recursively convert dataclasses and containers into JSON-safe values."""
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value

    def _default_document_tool(self) -> DocumentExtractionTool:
        """Create the document tool, using Ark multimodal extraction when configured."""
        config = LLMConfig.from_env()
        if config.api_key:
            return DocumentExtractionTool(multimodal_extractor=ArkMultimodalExtractor(config=config))
        return DocumentExtractionTool()
