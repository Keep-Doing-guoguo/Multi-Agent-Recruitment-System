import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from recruitment_system.config import LLMConfig
from recruitment_system.llm import ArkMultimodalExtractor


class FakeArkResponsesClient:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = payload
        return {"output_text": "王五\n本科，4 年 Python 开发经验\n技能: Python, FastAPI"}


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

    def test_extract_returns_error_result_for_unsupported_local_file(self) -> None:
        client = FakeArkResponsesClient()
        extractor = ArkMultimodalExtractor(client=client, config=test_config())  # type: ignore[arg-type]

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "resume.docx"
            file_path.write_bytes(b"fake-docx")
            result = extractor.extract(file_path, "resume")

        self.assertEqual(result.confidence, 0.0)
        self.assertTrue(result.errors)
        self.assertIn("unsupported_multimodal_file_type", result.errors[0])


if __name__ == "__main__":
    unittest.main()
