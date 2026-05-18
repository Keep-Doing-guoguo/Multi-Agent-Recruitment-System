from __future__ import annotations

from typing import Any

from recruitment_system.llm import StructuredLLMClient


class DirectAnswerAgent:
    """回答不需要进入招聘业务 workflow 的通用问题。"""

    def __init__(self, llm_client: StructuredLLMClient | None = None) -> None:
        """初始化直接回答 Agent，可选接入 LLM。"""
        self.llm_client = llm_client

    def run(self, question: str, state: dict[str, Any] | None = None) -> str:
        """回答无需业务路由的问题，LLM 不可用时使用规则回答。"""
        if self.llm_client is not None:
            try:
                answer = self._run_llm(question, state or {})
                if answer:
                    return answer
            except Exception:
                pass
        return self._rule_answer(question)

    def _run_llm(self, question: str, state: dict[str, Any]) -> str:
        """使用配置的 LLM 生成简洁直接的回答。"""
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 Direct Answer Agent。请回答不需要进入招聘业务 workflow 的通用问题。"
                "回答要简洁、直接。只返回 JSON object，字段：answer。"
            ),
            user_payload={"question": question, "state_keys": list(state.keys())},
        )
        return str(data.get("answer") or "").strip()

    def _rule_answer(self, question: str) -> str:
        """对常见架构类问题返回确定性回答。"""
        text = question.lower()
        if "router" in text or "路由" in text:
            return (
                "MessageRouterAgent 负责判断用户消息应该进入哪个路径；"
                "它不直接处理招聘业务，只决定是基于已有状态回答、进入某个业务节点，还是直接回答。"
            )
        if "agent" in text and ("workflow" in text or "graph" in text or "区别" in text):
            return (
                "Agent 负责一个局部任务的判断和执行；Graph/Workflow 负责节点之间的流转。"
                "在这个项目里，Router 决定入口，LangGraph 决定流程，业务 Agent 处理各自节点。"
            )
        if "langgraph" in text:
            return (
                "LangGraph 在这里负责招聘 workflow 编排，包括从指定节点进入、条件边判断、"
                "节点执行顺序和 run_events 追踪。"
            )
        return "这是一个通用问题，不需要进入招聘业务 Agent。当前规则版 DirectAnswerAgent 只能回答基础架构说明。"
