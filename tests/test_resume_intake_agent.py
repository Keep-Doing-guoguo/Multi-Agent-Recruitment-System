import unittest

from recruitment_system.agents.resume_intake_agent import ResumeIntakeAgent
from recruitment_system.tools.document_extraction import DocumentExtractionTool


class ResumeIntakeAgentTest(unittest.TestCase):
    def test_agent_decides_extraction_method_from_source_type(self) -> None:
        agent = ResumeIntakeAgent(document_tool=DocumentExtractionTool())

        self.assertEqual(agent._choose_extraction_method("inline_text", "简历内容"), "inline_text")
        self.assertEqual(agent._choose_extraction_method("txt", "resume.txt"), "text")
        self.assertEqual(agent._choose_extraction_method("pdf", "resume.pdf"), "pdf")
        self.assertEqual(agent._choose_extraction_method("docx", "resume.docx"), "docx")
        self.assertEqual(agent._choose_extraction_method("png", "https://example.com/resume.png"), "multimodal")


if __name__ == "__main__":
    unittest.main()
