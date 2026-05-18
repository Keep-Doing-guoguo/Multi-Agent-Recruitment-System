from __future__ import annotations

from dataclasses import asdict

from recruitment_system.llm import StructuredLLMClient
from recruitment_system.models import CandidateProfile, JobProfile, MatchResult, ScreeningResult
from recruitment_system.tools.screening_rules import ScreeningRuleEngine


class ScreeningAgent:
    """根据候选人画像和匹配结果生成初筛建议。"""

    def __init__(
        self,
        rule_engine: ScreeningRuleEngine | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        """初始化初筛 Agent，可注入规则引擎和结构化 LLM 客户端。"""
        self.rule_engine = rule_engine or ScreeningRuleEngine()
        self.llm_client = llm_client

    def run(
        self,
        candidate: CandidateProfile,
        job: JobProfile,
        match_result: MatchResult,
    ) -> ScreeningResult:
        """执行初筛判断；规则结果作为 guardrail，LLM 失败时回退规则结果。"""
        _ = job
        rule_result = self.rule_engine.evaluate(candidate, match_result)
        if self.llm_client is None:
            return rule_result
        try:
            return self._run_llm(candidate, job, match_result, rule_result)
        except Exception:
            return rule_result

    def _run_llm(
        self,
        candidate: CandidateProfile,
        job: JobProfile,
        match_result: MatchResult,
        rule_result: ScreeningResult,
    ) -> ScreeningResult:
        """调用 LLM 生成初筛建议，并用规则结果约束高风险输出。"""
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 Screening Agent。请基于候选人、岗位和匹配结果给出初筛建议。"
                "只返回 JSON object。字段：recommendation, confidence, reasons, risk_points,"
                "requires_human_review, summary。recommendation 只能是 recommend_interview,"
                "manual_review, not_recommended。不能给录用结论。"
            ),
            user_payload={
                "candidate_profile": asdict(candidate),
                "job_profile": asdict(job),
                "match_result": asdict(match_result),
                "rule_guardrail": asdict(rule_result),
            },
        )
        recommendation = str(data.get("recommendation") or rule_result.recommendation)
        if recommendation not in {"recommend_interview", "manual_review", "not_recommended"}:
            recommendation = rule_result.recommendation
        if match_result.match_score < 60 and recommendation == "recommend_interview":
            recommendation = "manual_review"

        risk_points = self._list(data.get("risk_points")) or rule_result.risk_points
        requires_review = bool(data.get("requires_human_review", rule_result.requires_human_review))
        if match_result.missing_requirements or match_result.risk_points:
            requires_review = True
        return ScreeningResult(
            recommendation=recommendation,  # type: ignore[arg-type]
            confidence=self._confidence(data.get("confidence"), rule_result.confidence),
            reasons=self._list(data.get("reasons")) or rule_result.reasons,
            risk_points=risk_points,
            requires_human_review=requires_review,
            summary=str(data.get("summary") or rule_result.summary),
        )

    def _list(self, value: object) -> list[str]:
        """把模型返回值转换为字符串列表。"""
        return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []

    def _confidence(self, value: object, fallback: float) -> float:
        """把置信度归一化到 0 到 1 之间，非法值使用 fallback。"""
        try:
            confidence = float(str(value))
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, confidence))
