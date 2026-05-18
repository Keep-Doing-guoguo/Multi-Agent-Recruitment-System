from __future__ import annotations

from typing import Any

from recruitment_system.llm import StructuredLLMClient


class StateAnswerAgent:
    """基于已持久化的招聘 workflow 状态回答追问。"""

    def __init__(self, llm_client: StructuredLLMClient | None = None) -> None:
        """初始化状态回答 Agent，可选接入 LLM。"""
        self.llm_client = llm_client

    def run(self, question: str, state: dict[str, Any]) -> str:
        """使用已有候选人、匹配、初筛和复核状态回答用户问题。"""
        if self.llm_client is not None:
            try:
                answer = self._run_llm(question, state)
                if answer:
                    return answer
            except Exception:
                pass
        return self._rule_answer(question, state)

    def _run_llm(self, question: str, state: dict[str, Any]) -> str:
        """调用 LLM 生成严格基于现有 state 的回答。"""
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 State Answer Agent。请只基于已有招聘 workflow state 回答用户追问。"
                "不要编造 state 中不存在的信息。只返回 JSON object，字段：answer。"
            ),
            user_payload={
                "question": question,
                "state": self._compact_state(state),
            },
        )
        return str(data.get("answer") or "").strip()

    def _rule_answer(self, question: str, state: dict[str, Any]) -> str:
        """从持久化结果中拼装规则版回答。"""
        text = question.lower()
        candidate = state.get("candidate_profile") if isinstance(state.get("candidate_profile"), dict) else {}
        match_result = state.get("match_result") if isinstance(state.get("match_result"), dict) else {}
        screening = state.get("screening_result") if isinstance(state.get("screening_result"), dict) else {}
        supervisor = state.get("supervisor_review") if isinstance(state.get("supervisor_review"), dict) else {}
        interview = state.get("interview_plan") if isinstance(state.get("interview_plan"), dict) else {}

        if any(keyword in text for keyword in ("为什么", "原因", "不推荐", "推荐", "人工复核", "风险")):
            parts = []
            if supervisor.get("summary"):
                parts.append(str(supervisor["summary"]))
            elif screening.get("summary"):
                parts.append(str(screening["summary"]))
            if match_result.get("match_score") is not None:
                parts.append(f"当前匹配分为 {match_result['match_score']}。")
            missing = match_result.get("missing_requirements") or []
            if missing:
                parts.append("主要缺口：" + "；".join(str(item) for item in missing[:5]) + "。")
            risks = supervisor.get("risk_points") or screening.get("risk_points") or match_result.get("risk_points") or []
            if risks:
                parts.append("风险点：" + "；".join(str(item) for item in risks[:5]) + "。")
            if parts:
                return "\n".join(parts)

        if any(keyword in text for keyword in ("分数", "匹配", "match")) and match_result:
            score = match_result.get("match_score", "未知")
            summary = match_result.get("summary") or ""
            return f"当前岗位匹配分是 {score}。{summary}".strip()

        if any(keyword in text for keyword in ("面试", "问题", "interview")) and interview:
            questions = interview.get("questions") or []
            focus = interview.get("focus_areas") or []
            answer = interview.get("summary") or "当前已有面试计划。"
            if focus:
                answer += "\n重点关注：" + "、".join(str(item) for item in focus[:5]) + "。"
            if questions:
                answer += "\n示例问题：" + "；".join(str(item.get("question", "")) for item in questions[:3] if isinstance(item, dict)) + "。"
            return answer

        if candidate:
            name = candidate.get("name") or "该候选人"
            skills = candidate.get("skills") or []
            return f"当前会话已有{name}的候选人画像。技能包括：{', '.join(str(skill) for skill in skills[:8]) or '暂无明确技能'}。"

        return "当前会话状态里没有足够的招聘处理结果，无法基于已有状态回答。"

    def _compact_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """只保留状态问答需要的业务结果字段。"""
        keys = [
            "candidate_profile",
            "job_profile",
            "match_result",
            "screening_result",
            "interview_plan",
            "supervisor_review",
        ]
        return {key: state[key] for key in keys if key in state}
