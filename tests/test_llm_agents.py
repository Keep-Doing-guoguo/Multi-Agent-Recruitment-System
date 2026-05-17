import unittest
from typing import Any

from recruitment_system.workflow import RecruitmentWorkflow


class FakeStructuredLLMClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(system_prompt)
        if "Resume Parsing Agent" in system_prompt:
            return {
                "name": "LLM候选人",
                "email": "llm@example.com",
                "phone": "13800138000",
                "skills": ["Python", "FastAPI"],
                "years_experience": 5,
                "education_level": "bachelor",
                "projects": ["招聘系统"],
                "work_experience": ["后端开发"],
                "uncertain_fields": [],
            }
        if "Job Matching Agent" in system_prompt:
            return {
                "summary": "LLM 解释：候选人核心技能匹配，但需要验证 Kubernetes。",
                "risk_points": ["LLM 风险：Kubernetes 未明确"],
            }
        if "Screening Agent" in system_prompt:
            return {
                "recommendation": "recommend_interview",
                "confidence": 0.88,
                "reasons": ["LLM 判断核心能力匹配"],
                "risk_points": ["LLM 风险：Kubernetes 未明确"],
                "requires_human_review": True,
                "summary": "LLM 建议进入面试但需要人工复核。",
            }
        if "Interview Agent" in system_prompt:
            return {
                "interview_type": "technical_first_round_with_review",
                "selected_strategy": "llm_risk_based_interview",
                "decision_reason": "LLM 根据风险选择重点验证策略",
                "focus_areas": ["Python", "FastAPI", "Kubernetes"],
                "questions": [
                    {
                        "category": "technical",
                        "question": "请说明 FastAPI 项目中的接口设计。",
                        "reason": "验证核心技能深度",
                    }
                ],
                "risk_validation_questions": [
                    {
                        "category": "risk_validation",
                        "question": "请说明 Kubernetes 相关经验。",
                        "reason": "验证风险点",
                        "risk": "Kubernetes 未明确",
                    }
                ],
                "requires_human_review": True,
                "summary": "LLM 面试计划。",
            }
        if "Supervisor Agent" in system_prompt:
            return {
                "final_recommendation": "manual_review",
                "decision_reason": "LLM 复核认为需要人工确认风险。",
                "key_reasons": ["核心技能匹配", "Kubernetes 风险"],
                "risk_points": ["Kubernetes 未明确"],
                "human_review_required": True,
                "summary": "LLM 最终建议人工复核。",
            }
        raise AssertionError(f"Unexpected prompt: {system_prompt}")


class LLMAgentsTest(unittest.TestCase):
    def test_workflow_uses_llm_outputs_when_client_is_provided(self) -> None:
        llm = FakeStructuredLLMClient()
        workflow = RecruitmentWorkflow(llm_client=llm)  # type: ignore[arg-type]

        state = workflow.run(
            "这是一份简历：Python 后端工程师，本科，5 年经验。",
            "职位: Python 后端工程师\n要求 Python, FastAPI, Kubernetes",
        )

        self.assertFalse(state.errors)
        self.assertEqual(state.candidate_profile.name, "LLM候选人")  # type: ignore[union-attr]
        self.assertIn("LLM 解释", state.match_result.summary)  # type: ignore[union-attr]
        self.assertEqual(state.screening_result.confidence, 0.88)  # type: ignore[union-attr]
        self.assertEqual(state.interview_plan.selected_strategy, "llm_risk_based_interview")  # type: ignore[union-attr]
        self.assertEqual(state.supervisor_review.summary, "LLM 最终建议人工复核。")  # type: ignore[union-attr]
        self.assertEqual(len(llm.calls), 5)


if __name__ == "__main__":
    unittest.main()
