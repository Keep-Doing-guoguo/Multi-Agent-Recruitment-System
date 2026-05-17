import unittest
from typing import Any

from recruitment_system.agents.message_router_agent import MessageRouterAgent


class FakeRouterLLMClient:
    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if "Message Router Agent" not in system_prompt:
            raise AssertionError(f"Unexpected prompt: {system_prompt}")
        return {
            "route": "interview",
            "reason": "用户要求生成面试问题。",
            "required_nodes": ["interview", "supervisor"],
            "requires_new_input": False,
            "confidence": 0.91,
        }


class MessageRouterAgentTest(unittest.TestCase):
    def test_routes_resume_and_jd_inputs_to_full_recruitment_flow(self) -> None:
        router = MessageRouterAgent()

        decision = router.run(
            "请分析这个候选人是否匹配岗位",
            conversation_state={
                "resume_input": "张三\n本科，5 年 Python 后端开发经验",
                "jd_input": "职位: Python 后端工程师\n要求 Python, FastAPI",
            },
        )

        self.assertEqual(decision.route, "resume_intake")
        self.assertEqual(
            decision.required_nodes,
            ["resume_intake", "resume_parsing", "jd_extraction", "job_matching", "screening", "interview", "supervisor"],
        )
        self.assertTrue(decision.requires_agent)
        self.assertFalse(decision.requires_new_input)

    def test_routes_new_jd_input_with_candidate_to_matching_flow(self) -> None:
        router = MessageRouterAgent()

        decision = router.run(
            "更新一下岗位要求",
            conversation_state={
                "candidate_profile": {"skills": ["Python", "FastAPI"]},
                "jd_input": "职位: Python 后端工程师\n要求 Python, Redis",
            },
        )

        self.assertEqual(decision.route, "job_matching")
        self.assertEqual(decision.required_nodes, ["jd_extraction", "job_matching", "screening", "interview", "supervisor"])
        self.assertFalse(decision.requires_new_input)

    def test_routes_resume_upload_to_resume_intake(self) -> None:
        router = MessageRouterAgent()

        decision = router.run("我上传了一份 PDF 简历，请重新解析")

        self.assertEqual(decision.route, "resume_intake")
        self.assertTrue(decision.requires_agent)
        self.assertTrue(decision.requires_new_input)
        self.assertEqual(decision.required_nodes, ["resume_intake"])

    def test_routes_follow_up_question_to_answer_from_state(self) -> None:
        router = MessageRouterAgent()

        decision = router.run(
            "这个候选人为什么不推荐？",
            conversation_state={"screening_result": {"recommendation": "not_recommended"}},
        )

        self.assertEqual(decision.route, "answer_from_state")
        self.assertFalse(decision.requires_agent)
        self.assertFalse(decision.required_nodes)

    def test_routes_jd_change_to_job_matching(self) -> None:
        router = MessageRouterAgent()

        decision = router.run(
            "JD 改成需要 Kubernetes 经验，请重新匹配",
            conversation_state={"candidate_profile": {"skills": ["Python"]}},
        )

        self.assertEqual(decision.route, "job_matching")
        self.assertTrue(decision.requires_agent)
        self.assertIn("job_matching", decision.required_nodes)
        self.assertFalse(decision.requires_new_input)

    def test_routes_general_question_to_direct_answer(self) -> None:
        router = MessageRouterAgent()

        decision = router.run("agent 和 router 的区别是什么？")

        self.assertEqual(decision.route, "direct_answer")
        self.assertFalse(decision.requires_agent)

    def test_uses_llm_route_when_client_is_provided(self) -> None:
        router = MessageRouterAgent(llm_client=FakeRouterLLMClient())  # type: ignore[arg-type]

        decision = router.run("帮我生成面试问题", conversation_state={"match_result": {"match_score": 80}})

        self.assertEqual(decision.route, "interview")
        self.assertTrue(decision.requires_agent)
        self.assertEqual(decision.required_nodes, ["interview", "supervisor"])
        self.assertEqual(decision.confidence, 0.91)


if __name__ == "__main__":
    unittest.main()
