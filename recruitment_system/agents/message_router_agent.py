from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from recruitment_system.llm import StructuredLLMClient
from recruitment_system.graph import WORKFLOW_NODE_ORDER
from recruitment_system.models import MessageRoute, MessageRouteDecision


ROUTE_LABELS: dict[MessageRoute, str] = {
    "answer_from_state": "基于已有状态回答 / Answer from existing state",
    "resume_intake": "简历接收与解析入口 / Resume intake",
    "job_matching": "岗位匹配 / Job matching",
    "screening": "初筛判断 / Screening",
    "interview": "面试计划生成 / Interview planning",
    "supervisor": "总控复核 / Supervisor review",
    "direct_answer": "直接回答 / Direct answer",
}

BUSINESS_AGENT_ROUTES: set[MessageRoute] = {
    "resume_intake",
    "job_matching",
    "screening",
    "interview",
    "supervisor",
}

VALID_ROUTES: set[MessageRoute] = set(ROUTE_LABELS)


class MessageRouterAgent:
    """判断用户消息应该进入哪个业务 Agent，或直接回答。"""

    def __init__(self, llm_client: StructuredLLMClient | None = None) -> None:
        """初始化消息路由器，可选接入 LLM 做语义路由。"""
        self.llm_client = llm_client

    def run(
        self,
        user_message: str,
        conversation_state: Mapping[str, Any] | object | None = None,
    ) -> MessageRouteDecision:
        """返回一条用户消息的路由决策。

        优先使用显式输入信号，其次使用可选 LLM 路由，最后回退到关键词规则。
        """
        input_decision = self._route_from_explicit_inputs(conversation_state)
        if input_decision is not None:
            return input_decision
        if self.llm_client is not None:
            llm_decision = self._try_llm_route(user_message, conversation_state)
            if llm_decision is not None:
                return llm_decision
        return self._rule_route(user_message, conversation_state)

    def _try_llm_route(
        self,
        user_message: str,
        conversation_state: Mapping[str, Any] | object | None,
    ) -> MessageRouteDecision | None:
        """调用 LLM 判断路由；失败时返回 None 让上层继续走规则路由。"""
        try:
            data = self.llm_client.generate_json(
                system_prompt=(
                    "你是 Message Router Agent / 消息路由器。你的任务不是执行业务，而是决定用户消息应该进入哪个路径。"
                    "只返回 JSON object。route 必须是以下之一："
                    "answer_from_state, resume_intake, job_matching, screening, interview, supervisor, direct_answer。"
                    "语义：answer_from_state=基于已有状态回答追问；resume_intake=新简历上传或重新解析；"
                    "job_matching=JD 或匹配条件变化；screening=初筛条件变化；interview=生成或调整面试问题；"
                    "supervisor=最终复核、风险验证或最终建议；direct_answer=通用问题，不进入业务 Agent。"
                    "字段：route, reason, required_nodes, requires_new_input, confidence。"
                ),
                user_payload={
                    "user_message": user_message,
                    "conversation_state_keys": self._state_keys(conversation_state),
                    "available_routes": list(ROUTE_LABELS),
                },
            )
            return self._normalize_decision(data)
        except Exception:
            return None

    def _route_from_explicit_inputs(
        self,
        conversation_state: Mapping[str, Any] | object | None,
    ) -> MessageRouteDecision | None:
        """优先根据显式 state 字段路由，避免自然语言误判。

        例如 resume_input + jd_input 表示完整首轮分析；
        jd_input + candidate_profile 表示基于已有简历重新匹配岗位。
        """
        has_resume_input = self._state_has_text(conversation_state, "resume_input")
        has_jd_input = self._state_has_text(conversation_state, "jd_input")
        has_parsed_resume = self._state_has_value(conversation_state, "candidate_profile")

        if has_resume_input and has_jd_input:
            return self._decision(
                "resume_intake",
                "本轮同时提供了简历和 JD，进入完整招聘分析链路。",
                required_nodes=self._workflow_from("resume_intake"),
                requires_new_input=False,
                confidence=0.95,
            )

        if has_jd_input and has_parsed_resume:
            return self._decision(
                "job_matching",
                "本轮提供了新的 JD，且会话中已有解析后的简历画像，按 JD 更新重新匹配并刷新下游结论。",
                required_nodes=self._workflow_from("jd_extraction"),
                requires_new_input=False,
                confidence=0.93,
            )

        if has_resume_input:
            return self._decision(
                "resume_intake",
                "本轮提供了新的简历输入，进入简历接收与解析链路。",
                required_nodes=self._workflow_from("resume_intake", stop_at="resume_intake"),
                requires_new_input=False,
                confidence=0.92,
            )

        return None

    def _rule_route(
        self,
        user_message: str,
        conversation_state: Mapping[str, Any] | object | None,
    ) -> MessageRouteDecision:
        """在没有显式输入或 LLM 决策时，使用关键词规则路由。"""
        text = user_message.strip().lower()
        has_state = self._has_business_state(conversation_state)

        if not text:
            return self._decision(
                "direct_answer",
                "用户消息为空，无法进入招聘业务 Agent。",
                confidence=0.7,
            )

        if self._contains_any(text, ("上传", "文件", "简历", "resume", "pdf", "docx", "解析", "重新解析")) and self._contains_any(
            text, ("上传", "解析", "导入", "重新", "resume", "pdf", "docx")
        ):
            return self._decision(
                "resume_intake",
                "消息包含简历上传、导入或重新解析意图。",
                required_nodes=self._workflow_from("resume_intake", stop_at="resume_intake"),
                requires_new_input=True,
                confidence=0.88,
            )

        if self._contains_any(text, ("jd", "岗位", "职位", "匹配", "match", "要求", "条件")) and self._contains_any(
            text, ("改", "变", "重新", "匹配", "criteria", "要求", "jd")
        ):
            return self._decision(
                "job_matching",
                "消息涉及 JD、岗位要求或匹配条件变化。",
                required_nodes=self._workflow_from("jd_extraction"),
                requires_new_input=not has_state,
                confidence=0.86,
            )

        if has_state and self._contains_any(text, ("为什么", "原因", "解释", "刚才", "这个", "结果", "分数", "候选人", "他", "她")):
            return self._decision(
                "answer_from_state",
                "消息是基于已有招聘处理结果的追问，不需要重新运行业务 Agent。",
                confidence=0.82,
            )

        if self._contains_any(text, ("初筛", "筛选", "推荐", "不推荐", "screening", "面试推荐")):
            return self._decision(
                "screening",
                "消息要求重新判断初筛结论或推荐状态。",
                required_nodes=self._workflow_from("screening"),
                requires_new_input=not has_state,
                confidence=0.84,
            )

        if self._contains_any(text, ("面试", "问题", "题目", "interview", "question")):
            return self._decision(
                "interview",
                "消息要求生成或调整面试计划和面试问题。",
                required_nodes=self._workflow_from("interview"),
                requires_new_input=not has_state,
                confidence=0.84,
            )

        if self._contains_any(text, ("最终", "复核", "风险", "结论", "建议", "supervisor", "review")) and self._contains_any(
            text, ("最终", "复核", "风险", "结论", "建议", "review")
        ):
            return self._decision(
                "supervisor",
                "消息要求最终复核、风险验证或最终建议。",
                required_nodes=self._workflow_from("supervisor"),
                requires_new_input=not has_state,
                confidence=0.82,
            )

        return self._decision(
            "direct_answer",
            "消息属于通用问答或架构讨论，不需要进入招聘业务 Agent。",
            confidence=0.72,
        )

    def _normalize_decision(self, data: Mapping[str, Any]) -> MessageRouteDecision:
        """校验并归一化 LLM 返回的路由 JSON。"""
        route = str(data.get("route") or "").strip()
        if route not in VALID_ROUTES:
            raise ValueError(f"Invalid route: {route}")
        required_nodes = data.get("required_nodes")
        if not isinstance(required_nodes, list):
            required_nodes = []
        clean_nodes = [str(item).strip() for item in required_nodes if str(item).strip()]
        confidence = self._coerce_confidence(data.get("confidence"))
        return self._decision(
            route,  # type: ignore[arg-type]
            str(data.get("reason") or "LLM 路由决策。").strip(),
            required_nodes=clean_nodes,
            requires_new_input=bool(data.get("requires_new_input", False)),
            confidence=confidence,
        )

    def _decision(
        self,
        route: MessageRoute,
        reason: str,
        required_nodes: list[str] | None = None,
        requires_new_input: bool = False,
        confidence: float = 0.0,
    ) -> MessageRouteDecision:
        """构造完整的 MessageRouteDecision，补齐标签和 Agent 标记。"""
        nodes = required_nodes or ([route] if route in BUSINESS_AGENT_ROUTES else [])
        return MessageRouteDecision(
            route=route,
            route_label=ROUTE_LABELS[route],
            reason=reason,
            required_nodes=nodes,
            requires_agent=route in BUSINESS_AGENT_ROUTES,
            requires_new_input=requires_new_input,
            confidence=confidence,
        )

    def _workflow_from(self, start_at: str, stop_at: str | None = None) -> list[str]:
        """根据起止节点返回标准 LangGraph 节点片段。"""
        if start_at not in WORKFLOW_NODE_ORDER:
            return []
        start_index = WORKFLOW_NODE_ORDER.index(start_at)
        if stop_at is None:
            return WORKFLOW_NODE_ORDER[start_index:]
        stop_index = WORKFLOW_NODE_ORDER.index(stop_at) if stop_at in WORKFLOW_NODE_ORDER else start_index
        return WORKFLOW_NODE_ORDER[start_index : stop_index + 1]

    def _has_business_state(self, conversation_state: Mapping[str, Any] | object | None) -> bool:
        """判断会话中是否已有可复用的业务结果状态。"""
        keys = set(self._state_keys(conversation_state))
        return bool(
            keys.intersection(
                {
                    "resume_document",
                    "candidate_profile",
                    "job_profile",
                    "match_result",
                    "screening_result",
                    "interview_plan",
                    "supervisor_review",
                }
            )
        )

    def _state_keys(self, conversation_state: Mapping[str, Any] | object | None) -> list[str]:
        """读取 dict、dataclass 或普通对象中的非空顶层字段名。"""
        if conversation_state is None:
            return []
        if isinstance(conversation_state, Mapping):
            return [str(key) for key, value in conversation_state.items() if value is not None]
        if is_dataclass(conversation_state):
            return [key for key, value in asdict(conversation_state).items() if value is not None]
        return [key for key, value in vars(conversation_state).items() if value is not None]

    def _state_has_text(self, conversation_state: Mapping[str, Any] | object | None, key: str) -> bool:
        """判断 state 中某个字段是否为非空字符串。"""
        value = self._state_value(conversation_state, key)
        return isinstance(value, str) and bool(value.strip())

    def _state_has_value(self, conversation_state: Mapping[str, Any] | object | None, key: str) -> bool:
        """判断 state 中某个字段是否存在有效值。"""
        value = self._state_value(conversation_state, key)
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, Mapping):
            return bool(value)
        return True

    def _state_value(self, conversation_state: Mapping[str, Any] | object | None, key: str) -> Any:
        """从 dict、dataclass 或普通对象中读取字段值。"""
        if conversation_state is None:
            return None
        if isinstance(conversation_state, Mapping):
            return conversation_state.get(key)
        if is_dataclass(conversation_state):
            return asdict(conversation_state).get(key)
        return getattr(conversation_state, key, None)

    def _contains_any(self, text: str, keywords: tuple[str, ...]) -> bool:
        """判断文本中是否包含任一关键词。"""
        return any(keyword in text for keyword in keywords)

    def _coerce_confidence(self, value: Any) -> float:
        """把任意值转换为 0 到 1 之间的置信度。"""
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, confidence))
