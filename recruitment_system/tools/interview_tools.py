from __future__ import annotations

from recruitment_system.models import InterviewQuestion


class QuestionGenerationTool:
    """Creates deterministic interview questions from focus areas and risks."""

    def generate_focus_questions(self, focus_areas: list[str]) -> list[InterviewQuestion]:
        questions: list[InterviewQuestion] = []
        for area in focus_areas[:5]:
            questions.append(
                InterviewQuestion(
                    category="technical",
                    question=f"请结合一个实际项目，说明你在 {area} 方面的具体职责、技术选择和结果。",
                    reason=f"验证候选人在 {area} 上的真实深度",
                )
            )
        return questions

    def generate_risk_questions(self, risk_points: list[str]) -> list[InterviewQuestion]:
        return [
            InterviewQuestion(
                category="risk_validation",
                question=f"关于“{risk}”，请说明你的实际经验、替代方案或学习计划。",
                reason="验证简历或岗位匹配中的风险点",
                risk=risk,
            )
            for risk in risk_points[:5]
        ]
