from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urlparse

from recruitment_system.models import DocumentExtractionResult, DocumentPurpose
from recruitment_system.tools.document_tools import DocxParserTool, PdfParserTool, TextParserTool


ExtractionMethod = Literal["inline_text", "text", "pdf", "docx", "multimodal", "unsupported"]


@runtime_checkable
class MultimodalExtractor(Protocol):
    """多模态文档理解适配器协议。

    具体实现可以接 Ark、多模态大模型、OCR 或第三方文档解析服务。
    调用方只关心输入的本地路径或远程 URL，以及文档用途；实现方负责返回统一的
    DocumentExtractionResult，隐藏 provider 的请求格式和错误细节。

    契约：
    - 支持本地图片、文档路径，或 HTTP(S) 远程 URL。
    - provider/API 失败时不向上抛异常，而是把错误写入 result.errors。
    - extracted_text 必须是后续 Agent 可继续解析的纯文本。
    - 提取失败或空结果时 confidence 应为 0.0。
    - 保留 source、purpose、file_type、warnings、errors，方便 tracing 和排查。
    """

    def extract(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """从本地文件路径或远程 URL 中提取标准化文本。"""
        ...


class DocumentExtractionTool:
    """把用户输入的文本、文件路径或 URL 转换成 Agent 可消费的标准文本。"""

    TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
    PDF_EXTENSIONS = {".pdf"}
    DOCX_EXTENSIONS = {".docx"}

    def __init__(self, multimodal_extractor: MultimodalExtractor | None = None) -> None:
        """初始化文档提取工具，可选接入多模态解析器作为兜底能力。"""
        self.multimodal_extractor = multimodal_extractor
        self.text_parser = TextParserTool()
        self.pdf_parser = PdfParserTool()
        self.docx_parser = DocxParserTool()

    def run(self, source: str, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """自动选择默认解析方式并执行文档提取。"""
        method = self.choose_default_method(source)
        return self.extract(source, purpose, method)

    def choose_default_method(self, source: str) -> ExtractionMethod:
        """根据输入形态和文件后缀选择默认解析方式。"""
        if not source.strip():
            return "unsupported"

        if self._looks_like_inline_text(source):
            return "inline_text"

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
        # 未内置支持的文件类型，如果配置了多模态解析器，就交给模型或外部服务处理。
        if self.multimodal_extractor is not None:
            return "multimodal"
        return "unsupported"

    def extract(self, source: str, purpose: DocumentPurpose, method: ExtractionMethod) -> DocumentExtractionResult:
        """按指定解析方式执行提取，并返回统一结果对象。"""
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
        """把非文件路径的普通字符串直接当作内联文本返回。"""
        return DocumentExtractionResult(
            source="inline_text",
            purpose=purpose,
            file_type="text",
            extracted_text=source,
            confidence=1.0,
        )

    def extract_multimodal(self, source: str | Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """调用多模态解析器处理 URL、图片或非内置支持的文档类型。"""
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
        """为无法解析的文件类型构造标准错误结果。"""
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
        """解析 txt、markdown、csv、json 等文本类文件。"""
        return self.text_parser.parse(path, purpose)

    def _is_url(self, source: str) -> bool:
        """判断输入是否为 HTTP(S) URL。"""
        parsed = urlparse(source)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _looks_like_inline_text(self, source: str) -> bool:
        """判断输入是否明显是正文文本，避免把长文本误当作文件路径。"""
        if "\n" in source or "\r" in source:
            return True
        return len(source) > 240

    def _file_type_from_source(self, source: str) -> str:
        """从 URL 或路径字符串中推断文件类型。"""
        suffix = Path(urlparse(source).path).suffix.lower()
        return suffix.lstrip(".") or "url"

    def extract_pdf(self, path: Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """解析 PDF；本地解析失败或无文本层时，使用多模态解析器兜底。"""
        result = self.pdf_parser.parse(path, purpose)
        if (result.errors or not result.extracted_text) and self.multimodal_extractor is not None:
            # 保留本地 PDF 解析器的错误和警告，方便判断是否发生了 fallback。
            fallback = self.multimodal_extractor.extract(path, purpose)
            if result.errors:
                fallback.warnings.extend(result.errors)
            if result.warnings:
                fallback.warnings.extend(result.warnings)
            return fallback
        return result

    def extract_docx(self, path: Path, purpose: DocumentPurpose) -> DocumentExtractionResult:
        """解析 DOCX；本地解析失败时，使用多模态解析器兜底。"""
        result = self.docx_parser.parse(path, purpose)
        if result.errors and self.multimodal_extractor is not None:
            if self.multimodal_extractor is not None:
                fallback = self.multimodal_extractor.extract(path, purpose)
                fallback.warnings.extend(result.errors)
                return fallback
        return result


DocumentExtractionAgent = DocumentExtractionTool
