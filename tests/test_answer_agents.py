import unittest

from recruitment_system.agents.direct_answer_agent import DirectAnswerAgent
from recruitment_system.agents.state_answer_agent import StateAnswerAgent


class AnswerAgentsTest(unittest.TestCase):
    def test_state_answer_explains_match_and_risks(self) -> None:
        agent = StateAnswerAgent()

        answer = agent.run(
            "为什么这个候选人需要人工复核？",
            {
                "match_result": {
                    "match_score": 62,
                    "missing_requirements": ["技能缺失：Kubernetes"],
                    "risk_points": ["年限不足"],
                },
                "screening_result": {
                    "summary": "候选人有基础匹配度，但存在关键缺口。",
                    "risk_points": ["缺少 Kubernetes 经验"],
                },
            },
        )

        self.assertIn("关键缺口", answer)
        self.assertIn("62", answer)
        self.assertIn("Kubernetes", answer)

    def test_direct_answer_handles_router_question(self) -> None:
        agent = DirectAnswerAgent()

        answer = agent.run("message router 是做什么的？")

        self.assertIn("MessageRouterAgent", answer)
        self.assertIn("路径", answer)


if __name__ == "__main__":
    unittest.main()
