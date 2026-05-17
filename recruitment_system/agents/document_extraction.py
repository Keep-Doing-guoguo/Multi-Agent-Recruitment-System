from recruitment_system.tools.document_extraction import DocumentExtractionTool, MultimodalExtractor

# Backward-compatible alias. New code should import DocumentExtractionTool from
# recruitment_system.tools.document_extraction.
DocumentExtractionAgent = DocumentExtractionTool

__all__ = ["DocumentExtractionAgent", "DocumentExtractionTool", "MultimodalExtractor"]
