from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.llm import ArkMultimodalExtractor, ArkStructuredLLMClient
from recruitment_system.workflow import RecruitmentWorkflow


def dataclass_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Run document extraction, resume parsing, and JD matching workflow.")
    parser.add_argument("--resume", required=True, help="Resume text or path to a resume file.")
    parser.add_argument("--jd", required=True, help="JD text or path to a JD file.")
    parser.add_argument("--multimodal", action="store_true", help="Use Ark multimodal extraction for images or URLs.")
    parser.add_argument("--llm", action="store_true", help="Use Ark LLM reasoning inside supported agents.")
    args = parser.parse_args()

    document_agent = None
    if args.multimodal:
        document_agent = DocumentExtractionAgent(multimodal_extractor=ArkMultimodalExtractor())
    llm_client = ArkStructuredLLMClient() if args.llm else None

    state = RecruitmentWorkflow(document_agent=document_agent, llm_client=llm_client).run(
        resume_input=args.resume,
        jd_input=args.jd,
    )
    print(json.dumps(dataclass_to_dict(state), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
