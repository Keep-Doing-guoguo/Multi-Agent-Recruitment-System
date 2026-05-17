from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.agents.resume_parsing import ResumeParsingAgent
from recruitment_system.agents.resume_intake import ResumeIntakeAgent
from recruitment_system.config import LLMConfig
from recruitment_system.llm import ArkMultimodalExtractor


class ResumeParsingService:
    """Runs the upload-file resume parsing use case."""

    def __init__(
        self,
        document_agent: DocumentExtractionAgent | None = None,
        resume_agent: ResumeParsingAgent | None = None,
    ) -> None:
        self.document_agent = document_agent or self._default_document_agent()
        self.resume_agent = resume_agent or ResumeParsingAgent()
        self.resume_intake_agent = ResumeIntakeAgent(
            document_agent=self.document_agent,
            resume_agent=self.resume_agent,
        )

    def parse_uploaded_file(self, filename: str, content: bytes) -> dict:
        suffix = Path(filename).suffix or ".txt"
        with NamedTemporaryFile(delete=True, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            document, candidate, intake_message = self.resume_intake_agent.run(temp_file.name)

        if document.errors:
            return {
                "success": False,
                "message": "简历文件解析失败",
                "errors": document.errors,
                "document": asdict(document),
            }

        if intake_message:
            return {
                "success": False,
                "message": intake_message,
                "document": asdict(document),
            }

        if candidate is None:
            return {
                "success": False,
                "message": "简历解析未生成候选人画像",
                "document": asdict(document),
            }

        return {
            "success": True,
            "message": "简历解析成功",
            "data": {
                "candidate_profile": asdict(candidate),
                "document": asdict(document),
            },
        }

    def _default_document_agent(self) -> DocumentExtractionAgent:
        config = LLMConfig.from_env()
        if config.api_key:
            return DocumentExtractionAgent(multimodal_extractor=ArkMultimodalExtractor(config=config))
        return DocumentExtractionAgent()
