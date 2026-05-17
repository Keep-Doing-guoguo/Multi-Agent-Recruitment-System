from __future__ import annotations

from dataclasses import asdict

from recruitment_system.llm import StructuredLLMClient
from recruitment_system.models import InterviewPlan, MatchResult, ScreeningResult, SupervisorReview


class SupervisorAgent:
    """Reviews downstream outputs and produces the final recommendation."""

    def __init__(self, llm_client: StructuredLLMClient | None = None) -> None:
        self.llm_client = llm_client

    def run(
        self,
        match_result: MatchResult,
        screening_result: ScreeningResult,
        interview_plan: InterviewPlan,
    ) -> SupervisorReview:
        risks = list(dict.fromkeys(screening_result.risk_points + [q.risk for q in interview_plan.risk_validation_questions if q.risk]))

        if screening_result.recommendation == "recommend_interview":
            final = "manual_review" if screening_result.requires_human_review else "proceed_to_interview"
        elif screening_result.recommendation == "manual_review":
            final = "manual_review"
        else:
            final = "reject"

        human_review_required = final == "manual_review" or screening_result.requires_human_review
        decision_reason = self._decision_reason(final, match_result.match_score, bool(risks))
        rule_review = SupervisorReview(
            final_recommendation=final,  # type: ignore[arg-type]
            decision_reason=decision_reason,
            key_reasons=list(dict.fromkeys(screening_result.reasons + [match_result.summary])),
            risk_points=risks,
            human_review_required=human_review_required,
            summary=decision_reason,
        )
        if self.llm_client is None:
            return rule_review
        try:
            return self._run_llm(match_result, screening_result, interview_plan, rule_review)
        except Exception:
            return rule_review

    def _decision_reason(self, final: str, score: int, has_risk: bool) -> str:
        if final == "proceed_to_interview":
            return f"匹配分 {score}/100，未发现强制复核风险，建议进入面试。"
        if final == "manual_review":
            risk_text = "存在风险点" if has_risk else "需要人工确认"
            return f"匹配分 {score}/100，{risk_text}，建议人工复核后决定。"
        return f"匹配分 {score}/100，初筛暂不推荐。"

    def _run_llm(
        self,
        match_result: MatchResult,
        screening_result: ScreeningResult,
        interview_plan: InterviewPlan,
        rule_review: SupervisorReview,
    ) -> SupervisorReview:
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 Supervisor Agent。请复核前序 Agent 输出，给出最终建议。"
                "只返回 JSON object。字段：final_recommendation, decision_reason, key_reasons,"
                "risk_points, human_review_required, summary。final_recommendation 只能是"
                " proceed_to_interview, manual_review, reject。不能给录用结论。"
            ),
            user_payload={
                "match_result": asdict(match_result),
                "screening_result": asdict(screening_result),
                "interview_plan": asdict(interview_plan),
                "rule_review": asdict(rule_review),
            },
        )
        final = str(data.get("final_recommendation") or rule_review.final_recommendation)
        if final not in {"proceed_to_interview", "manual_review", "reject"}:
            final = rule_review.final_recommendation
        if screening_result.requires_human_review and final == "proceed_to_interview":
            final = "manual_review"
        if screening_result.recommendation == "not_recommended" and final == "proceed_to_interview":
            final = "manual_review"
        human_review_required = bool(data.get("human_review_required", rule_review.human_review_required))
        if final == "manual_review":
            human_review_required = True
        return SupervisorReview(
            final_recommendation=final,  # type: ignore[arg-type]
            decision_reason=str(data.get("decision_reason") or rule_review.decision_reason),
            key_reasons=self._str_list(data.get("key_reasons")) or rule_review.key_reasons,
            risk_points=self._str_list(data.get("risk_points")) or rule_review.risk_points,
            human_review_required=human_review_required,
            summary=str(data.get("summary") or rule_review.summary),
        )

    def _str_list(self, value: object) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
