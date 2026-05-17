from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urlparse

from recruitment_system.models import DocumentExtractionResult, DocumentPurpose
from recruitment_system.tools.document_tools import DocxParserTool, PdfParserTool, TextParserTool


ExtractionMethod = Literal["inline_text", "text", "pdf", "docx", "multimodal", "unsupported"]


@runtime_checkable
class MultimodalExtractor(Protocol):
    """Adapter contract for model-backed document understanding.

    Implementations should hide provider-specific details such as Ark,
    OCR, or another multimodal API. The caller gives a local file path or
    remote URL plus the document purpose, and the adapter returns a normalized
    DocumentExtractionResult.

    Contract:
    - Accepts local image/document paths or remote HTTP(S) URLs.
    - Does not raise for provider/API failures; return errors on the result.
    - Sets extracted_text to plain text suitable for downstream parsing.
    - Sets confidence to 0.0 when extraction fails or returns empty text.
    - Preserves source, purpose, file_type, warnings, and errors for tracing.
    """

    def extract(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """Extract normalized text from a local file path or remote URL."""
        ...


class DocumentExtractionTool:
    """Converts raw file/text input into standardized text for agents."""

    TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
    PDF_EXTENSIONS = {".pdf"}
    DOCX_EXTENSIONS = {".docx"}

    def __init__(self, multimodal_extractor: MultimodalExtractor | None = None) -> None:
        self.multimodal_extractor = multimodal_extractor
        self.text_parser = TextParserTool()
        self.pdf_parser = PdfParserTool()
        self.docx_parser = DocxParserTool()

    def run(self, source: str, purpose: DocumentPurpose) -> DocumentExtractionResult:
        method = self.choose_default_method(source)
        return self.extract(source, purpose, method)

    def choose_default_method(self, source: str) -> ExtractionMethod:
        if not source.strip():
            return "unsupported"

        if self._is_url(source):
            return "multimodal"

        path = Path(source)
        if not path.exists() or not path.is_file():
            return "inline_text"

        suffix = path.suffix.lower()
        if suffix in self.TEXT_EXTENSIONS:
            return "text"
        if suffix in self.PDF_EXTENSIONS:
            return "pdf"
        if suffix in self.DOCX_EXTENSIONS:
            return "docx"
        if self.multimodal_extractor is not None:
            return "multimodal"
        return "unsupported"

    def extract(self, source: str, purpose: DocumentPurpose, method: ExtractionMethod) -> DocumentExtractionResult:
        if not source.strip():
            return DocumentExtractionResult(
                source=source,
                purpose=purpose,
                confidence=0.0,
                errors=[f"{purpose}_input is required"],
            )

        if method == "inline_text":
            return self.extract_inline_text(source, purpose)
        if method == "multimodal":
            return self.extract_multimodal(source, purpose)

        path = Path(source)
        if method == "text":
            return self.extract_text_file(path, purpose)
        if method == "pdf":
            return self.extract_pdf(path, purpose)
        if method == "docx":
            return self.extract_docx(path, purpose)
        return self.unsupported(source, purpose)

    def extract_inline_text(self, source: str, purpose: DocumentPurpose) -> DocumentExtractionResult:
        return DocumentExtractionResult(
            source="inline_text",
            purpose=purpose,
            file_type="text",
            extracted_text=source,
            confidence=1.0,
        )

    def extract_multimodal(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        if self.multimodal_extractor is not None:
            return self.multimodal_extractor.extract(source, purpose)
        source_text = str(source)
        if self._is_url(source_text):
            return DocumentExtractionResult(
                source=source_text,
                purpose=purpose,
                file_type=self._file_type_from_source(source_text),
                confidence=0.0,
                warnings=["需要配置多模态提取器后才能解析 URL 文件"],
                errors=["multimodal_extractor_required"],
            )
        return DocumentExtractionResult(
            source=source_text,
            purpose=purpose,
            file_type=Path(source_text).suffix.lower().lstrip(".") or "unknown",
            confidence=0.0,
            warnings=["需要配置多模态提取器后才能解析该文件类型"],
            errors=["multimodal_extractor_required"],
        )

    def unsupported(self, source: str, purpose: DocumentPurpose) -> DocumentExtractionResult:
        suffix = Path(source).suffix.lower()
        return DocumentExtractionResult(
            source=source,
            purpose=purpose,
            file_type=suffix.lstrip(".") or "unknown",
            confidence=0.0,
            warnings=["需要配置多模态提取器后才能解析该文件类型"],
            errors=[f"unsupported_file_type: {suffix or 'unknown'}"],
        )

    def extract_text_file(self, path: Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        return self.text_parser.parse(path, purpose)

    def _is_url(self, source: str) -> bool:
        parsed = urlparse(source)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _file_type_from_source(self, source: str) -> str:
        suffix = Path(urlparse(source).path).suffix.lower()
        return suffix.lstrip(".") or "url"

    def extract_pdf(self, path: Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        result = self.pdf_parser.parse(path, purpose)
        if (result.errors or not result.extracted_text) and self.multimodal_extractor is not None:
            fallback = self.multimodal_extractor.extract(path, purpose)
            if result.errors:
                fallback.warnings.extend(result.errors)
            if result.warnings:
                fallback.warnings.extend(result.warnings)
            return fallback
        return result

    def extract_docx(self, path: Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        result = self.docx_parser.parse(path, purpose)
        if result.errors and self.multimodal_extractor is not None:
            if self.multimodal_extractor is not None:
                fallback = self.multimodal_extractor.extract(path, purpose)
                fallback.warnings.extend(result.errors)
                return fallback
        return result


DocumentExtractionAgent = DocumentExtractionTool
