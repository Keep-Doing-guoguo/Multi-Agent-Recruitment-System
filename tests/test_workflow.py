import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.models import DocumentExtractionResult, DocumentPurpose
from recruitment_system.workflow import RecruitmentWorkflow


class FakeMultimodalExtractor:
    def extract(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        source_path = Path(str(source))
        return DocumentExtractionResult(
            source=str(source),
            purpose=purpose,
            file_type=source_path.suffix.lstrip(".") or "url",
            extracted_text="王五\n本科，4 年 Python 和 FastAPI 开发经验\n技能: Python, FastAPI, PostgreSQL",
            confidence=0.88,
            layout_blocks=["page_1"],
        )


class RecruitmentWorkflowTest(unittest.TestCase):
    def test_minimal_workflow_returns_candidate_and_match_result(self) -> None:
        resume = """
        李四
        硕士，6 年后端开发经验
        技能: Python, FastAPI, PostgreSQL, Redis, Docker
        """
        jd = """
        职位: 后端工程师
        5 年以上后端经验
        要求 Python, FastAPI, PostgreSQL, Redis, Kubernetes
        本科及以上学历
        """

        state = RecruitmentWorkflow().run(resume_input=resume, jd_input=jd)

        self.assertFalse(state.errors)
        self.assertIsNotNone(state.candidate_profile)
        self.assertIsNotNone(state.job_profile)
        self.assertIsNotNone(state.match_result)
        self.assertIsNotNone(state.screening_result)
        self.assertIsNotNone(state.interview_plan)
        self.assertIsNotNone(state.supervisor_review)
        assert state.candidate_profile is not None
        assert state.match_result is not None
        assert state.screening_result is not None
        assert state.interview_plan is not None
        assert state.supervisor_review is not None
        self.assertEqual(state.candidate_profile.name, "李四")
        self.assertIn("Python", state.candidate_profile.skills)
        self.assertGreaterEqual(state.match_result.match_score, 70)
        self.assertIn("技能缺失：Kubernetes", state.match_result.missing_requirements)
        self.assertIn(state.screening_result.recommendation, {"recommend_interview", "manual_review"})
        self.assertTrue(state.interview_plan.focus_areas)
        self.assertIn(state.supervisor_review.final_recommendation, {"proceed_to_interview", "manual_review", "reject"})

    def test_workflow_validates_required_inputs(self) -> None:
        state = RecruitmentWorkflow().run("", "职位: Python 工程师")

        self.assertEqual(state.errors, ["resume_input is required"])

    def test_workflow_can_use_multimodal_extractor_for_pdf_resume(self) -> None:
        with TemporaryDirectory() as temp_dir:
            resume_path = Path(temp_dir) / "resume.pdf"
            resume_path.write_bytes(b"%PDF-1.4 placeholder")
            document_agent = DocumentExtractionAgent(multimodal_extractor=FakeMultimodalExtractor())
            workflow = RecruitmentWorkflow(document_agent=document_agent)

            state = workflow.run(str(resume_path), "职位: Python 后端工程师\n3 年以上经验\n要求 Python, FastAPI")

        self.assertFalse(state.errors)
        self.assertIsNotNone(state.resume_document)
        self.assertIsNotNone(state.candidate_profile)
        assert state.resume_document is not None
        assert state.candidate_profile is not None
        self.assertEqual(state.resume_document.file_type, "pdf")
        self.assertEqual(state.resume_document.confidence, 0.88)
        self.assertEqual(state.candidate_profile.name, "王五")

    def test_workflow_can_use_multimodal_extractor_for_image_url(self) -> None:
        document_agent = DocumentExtractionAgent(multimodal_extractor=FakeMultimodalExtractor())
        workflow = RecruitmentWorkflow(document_agent=document_agent)

        state = workflow.run(
            "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png",
            "职位: Python 后端工程师\n3 年以上经验\n要求 Python, FastAPI",
        )

        self.assertFalse(state.errors)
        self.assertIsNotNone(state.resume_document)
        assert state.resume_document is not None
        self.assertEqual(state.resume_document.file_type, "png")


if __name__ == "__main__":
    unittest.main()
