import unittest
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

from recruitment_system.api import app


class ResumeApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_parse_resume_upload_returns_candidate_profile(self) -> None:
        response = self.client.post(
            "/api/resume/parse",
            files={
                "file": (
                    "resume.txt",
                    "赵六\n本科，5 年 Python 后端开发经验\n技能: Python, FastAPI, PostgreSQL\n工作经历:\n负责 API 开发",
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], "简历解析成功")
        self.assertEqual(body["data"]["candidate_profile"]["name"], "赵六")
        self.assertIn("Python", body["data"]["candidate_profile"]["skills"])

    def test_parse_resume_upload_returns_message_for_non_resume(self) -> None:
        response = self.client.post(
            "/api/resume/parse",
            files={
                "file": (
                    "note.txt",
                    "今天下午三点开会，讨论办公室采购和团建预算。",
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIn("不像一份简历", body["message"])

    def test_parse_resume_upload_rejects_empty_file(self) -> None:
        response = self.client.post(
            "/api/resume/parse",
            files={"file": ("empty.txt", "", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)

    def test_parse_resume_upload_accepts_docx_file(self) -> None:
        doc = Document()
        doc.add_paragraph("钱七")
        doc.add_paragraph("本科，4 年 Java 和 Spring Boot 后端开发经验")
        doc.add_paragraph("技能: Java, Spring Boot, MySQL, Redis")
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        response = self.client.post(
            "/api/resume/parse",
            files={
                "file": (
                    "resume.docx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["document"]["file_type"], "docx")
        self.assertEqual(body["data"]["candidate_profile"]["name"], "钱七")


if __name__ == "__main__":
    unittest.main()
