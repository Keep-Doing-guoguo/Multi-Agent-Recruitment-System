from __future__ import annotations

from recruitment_system.models import CandidateProfile, MatchResult, ScreeningResult


class ScreeningRuleEngine:
    """Applies first-round screening policy."""

    def evaluate(self, candidate: CandidateProfile, match_result: MatchResult) -> ScreeningResult:
        reasons: list[str] = []
        risks = list(match_result.risk_points)

        if match_result.match_score >= 80:
            recommendation = "recommend_interview"
            confidence = 0.82
            reasons.append("岗位匹配分达到面试推荐阈值")
        elif match_result.match_score >= 60:
            recommendation = "manual_review"
            confidence = 0.68
            reasons.append("岗位匹配分处于可考虑区间，需要人工确认关键缺口")
        else:
            recommendation = "not_recommended"
            confidence = 0.74
            reasons.append("岗位匹配分低于初筛建议阈值")

        if candidate.uncertain_fields:
            risks.append("简历关键信息不完整：" + ", ".join(candidate.uncertain_fields))
        if match_result.missing_requirements:
            reasons.append("存在未满足的岗位要求")
        if not candidate.work_experience and not candidate.projects:
            risks.append("缺少可验证的工作经历或项目经历")

        requires_human_review = (
            recommendation == "manual_review"
            or bool(candidate.uncertain_fields)
            or 55 <= match_result.match_score < 80
            or bool(match_result.missing_requirements)
            or bool(match_result.risk_points)
            or len(risks) >= 2
        )

        return ScreeningResult(
            recommendation=recommendation,  # type: ignore[arg-type]
            confidence=confidence,
            reasons=reasons,
            risk_points=risks,
            requires_human_review=requires_human_review,
            summary=self._summary(recommendation, match_result.match_score, requires_human_review),
        )

    def _summary(self, recommendation: str, score: int, requires_human_review: bool) -> str:
        labels = {
            "recommend_interview": "建议进入面试",
            "manual_review": "建议人工复核",
            "not_recommended": "暂不推荐",
        }
        review = "需要人工复核" if requires_human_review else "无需强制人工复核"
        return f"{labels[recommendation]}，匹配分 {score}/100，{review}。"
