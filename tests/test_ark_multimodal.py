import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from recruitment_system.config import LLMConfig
from recruitment_system.llm import ArkMultimodalExtractor


class FakeArkResponsesClient:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None
        self.uploaded_file_path: Path | None = None
        self.uploaded_purpose: str | None = None

    def create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = payload
        return {"output_text": "王五\n本科，4 年 Python 开发经验\n技能: Python, FastAPI"}

    def upload_file(self, file_path: str | Path, purpose: str = "user_data") -> dict[str, Any]:
        self.uploaded_file_path = Path(file_path)
        self.uploaded_purpose = purpose
        return {"id": "file-test-123"}


def test_config() -> LLMConfig:
    return LLMConfig(
        provider="volcengine_ark",
        api_key="test-key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        responses_path="/responses",
        files_path="/files",
        model="doubao-seed-2-0-lite-260428",
        multimodal_model="doubao-seed-2-0-lite-260428",
        temperature=0.2,
        max_tokens=4096,
        timeout_seconds=60,
        max_retries=0,
    )


class ArkMultimodalExtractorTest(unittest.TestCase):
    def test_extract_from_image_url_builds_ark_responses_payload(self) -> None:
        client = FakeArkResponsesClient()
        extractor = ArkMultimodalExtractor(client=client, config=test_config())  # type: ignore[arg-type]

        result = extractor.extract(
            "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png",
            "resume",
        )

        self.assertEqual(result.extracted_text, "王五\n本科，4 年 Python 开发经验\n技能: Python, FastAPI")
        self.assertEqual(result.file_type, "png")
        self.assertEqual(result.confidence, 0.8)
        assert client.payload is not None
        self.assertEqual(client.payload["model"], "doubao-seed-2-0-lite-260428")
        content = client.payload["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_image")
        self.assertEqual(
            content[0]["image_url"],
            "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png",
        )
        self.assertEqual(content[1]["type"], "input_text")
        self.assertIn("简历", content[1]["text"])

    def test_extract_from_local_image_uses_data_url(self) -> None:
        client = FakeArkResponsesClient()
        extractor = ArkMultimodalExtractor(client=client, config=test_config())  # type: ignore[arg-type]

        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "resume.png"
            image_path.write_bytes(b"fake-image-bytes")
            result = extractor.extract(image_path, "resume")

        self.assertFalse(result.errors)
        assert client.payload is not None
        image_url = client.payload["input"][0]["content"][0]["image_url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_extract_from_local_pdf_uploads_file_and_uses_input_file(self) -> None:
        client = FakeArkResponsesClient()
        extractor = ArkMultimodalExtractor(client=client, config=test_config())  # type: ignore[arg-type]

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "resume.pdf"
            file_path.write_bytes(b"%PDF-1.4 fake-pdf")
            result = extractor.extract(file_path, "resume")

        self.assertFalse(result.errors)
        self.assertEqual(result.file_type, "pdf")
        self.assertEqual(client.uploaded_file_path, file_path)
        self.assertEqual(client.uploaded_purpose, "user_data")
        assert client.payload is not None
        content = client.payload["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_file", "file_id": "file-test-123"})
        self.assertEqual(content[1]["type"], "input_text")
        self.assertIn("简历文件", content[1]["text"])

    def test_extract_from_remote_pdf_uses_file_url(self) -> None:
        client = FakeArkResponsesClient()
        extractor = ArkMultimodalExtractor(client=client, config=test_config())  # type: ignore[arg-type]

        result = extractor.extract("https://example.com/resume.pdf", "resume")

        self.assertFalse(result.errors)
        assert client.payload is not None
        content = client.payload["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_file", "file_url": "https://example.com/resume.pdf"})


if __name__ == "__main__":
    unittest.main()
