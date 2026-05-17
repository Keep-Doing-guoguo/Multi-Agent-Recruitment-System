import unittest

from recruitment_system.agents.interview import InterviewAgent
from recruitment_system.agents.supervisor import SupervisorAgent
from recruitment_system.models import CandidateProfile, JobProfile, MatchResult, ScreeningResult


class InterviewAndSupervisorTest(unittest.TestCase):
    def test_interview_agent_uses_risk_strategy_when_review_required(self) -> None:
        candidate = CandidateProfile(skills=["Python", "FastAPI"], projects=["招聘系统"])
        job = JobProfile(required_skills=["Python", "FastAPI", "Kubernetes"])
        match = MatchResult(
            match_score=82,
            matched_requirements=["技能匹配：Python"],
            missing_requirements=["技能缺失：Kubernetes"],
            risk_points=["缺少关键技能：Kubernetes"],
        )
        screening = ScreeningResult(
            recommendation="recommend_interview",
            confidence=0.82,
            risk_points=["缺少关键技能：Kubernetes"],
            requires_human_review=True,
        )

        plan = InterviewAgent().run(candidate, job, match, screening)

        self.assertEqual(plan.selected_strategy, "risk_based_technical_interview")
        self.assertTrue(plan.requires_human_review)
        self.assertTrue(plan.risk_validation_questions)

    def test_supervisor_promotes_review_when_screening_requires_review(self) -> None:
        match = MatchResult(match_score=82, summary="高度匹配")
        screening = ScreeningResult(
            recommendation="recommend_interview",
            confidence=0.82,
            reasons=["岗位匹配分达到面试推荐阈值"],
            risk_points=["缺少关键技能：Kubernetes"],
            requires_human_review=True,
        )
        plan = InterviewAgent().run(
            CandidateProfile(skills=["Python"]),
            JobProfile(required_skills=["Python", "Kubernetes"]),
            match,
            screening,
        )

        review = SupervisorAgent().run(match, screening, plan)

        self.assertEqual(review.final_recommendation, "manual_review")
        self.assertTrue(review.human_review_required)
        self.assertTrue(review.risk_points)


if __name__ == "__main__":
    unittest.main()
