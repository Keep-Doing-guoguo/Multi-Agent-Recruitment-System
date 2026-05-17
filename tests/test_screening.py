import unittest

from recruitment_system.agents.screening_agent import ScreeningAgent
from recruitment_system.models import CandidateProfile, JobProfile, MatchResult


class ScreeningAgentTest(unittest.TestCase):
    def test_recommends_interview_for_high_match(self) -> None:
        result = ScreeningAgent().run(
            CandidateProfile(skills=["Python"], years_experience=5, education_level="bachelor"),
            JobProfile(title="Python 后端工程师"),
            MatchResult(match_score=86, matched_requirements=["技能匹配：Python"]),
        )

        self.assertEqual(result.recommendation, "recommend_interview")
        self.assertFalse(result.requires_human_review)
        self.assertIn("建议进入面试", result.summary)

    def test_requires_manual_review_for_mid_match(self) -> None:
        result = ScreeningAgent().run(
            CandidateProfile(skills=["Python"], uncertain_fields=["education_level"]),
            JobProfile(title="Python 后端工程师"),
            MatchResult(match_score=68, missing_requirements=["技能缺失：Kubernetes"]),
        )

        self.assertEqual(result.recommendation, "manual_review")
        self.assertTrue(result.requires_human_review)
        self.assertTrue(result.risk_points)

    def test_not_recommended_for_low_match(self) -> None:
        result = ScreeningAgent().run(
            CandidateProfile(skills=["Excel"]),
            JobProfile(title="Python 后端工程师"),
            MatchResult(match_score=35, risk_points=["缺少关键技能：Python"]),
        )

        self.assertEqual(result.recommendation, "not_recommended")
        self.assertTrue(result.requires_human_review)


if __name__ == "__main__":
    unittest.main()
