from __future__ import annotations

from dataclasses import asdict

from recruitment_system.llm import StructuredLLMClient
from recruitment_system.models import CandidateProfile, MatchResult
from recruitment_system.tools.matching_tools import JDParserTool, MatchScoringTool


class JobMatchingAgent:
    """Parses a JD and compares it with a structured candidate profile."""

    def __init__(
        self,
        jd_parser: JDParserTool | None = None,
        scoring_tool: MatchScoringTool | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.jd_parser = jd_parser or JDParserTool()
        self.scoring_tool = scoring_tool or MatchScoringTool()
        self.llm_client = llm_client

    def run(self, candidate: CandidateProfile, jd_text: str):
        job = self.jd_parser.parse(jd_text)
        result: MatchResult = self.scoring_tool.score(candidate, job)
        if self.llm_client is not None:
            result = self._add_llm_explanation(candidate, jd_text, result)
        return job, result

    def _add_llm_explanation(self, candidate: CandidateProfile, jd_text: str, rule_result: MatchResult) -> MatchResult:
        try:
            data = self.llm_client.generate_json(
                system_prompt=(
                    "你是 Job Matching Agent。规则引擎已经给出 match_score、命中项和缺失项。"
                    "请只补充更清晰的 summary 和 risk_points，不要改变 match_score。"
                    "只返回 JSON object，字段：summary, risk_points。"
                ),
                user_payload={
                    "candidate_profile": asdict(candidate),
                    "jd_text": jd_text,
                    "rule_match_result": asdict(rule_result),
                },
            )
            summary = str(data.get("summary") or rule_result.summary).strip()
            risks = data.get("risk_points")
            if isinstance(risks, list):
                risk_points = [str(item).strip() for item in risks if str(item).strip()]
            else:
                risk_points = rule_result.risk_points
            return MatchResult(
                match_score=rule_result.match_score,
                matched_requirements=rule_result.matched_requirements,
                missing_requirements=rule_result.missing_requirements,
                risk_points=risk_points or rule_result.risk_points,
                summary=summary or rule_result.summary,
            )
        except Exception:
            return rule_result
