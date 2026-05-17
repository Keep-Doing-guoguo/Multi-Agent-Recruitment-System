from __future__ import annotations

from dataclasses import asdict

from recruitment_system.llm import StructuredLLMClient
from recruitment_system.models import CandidateProfile, InterviewPlan, InterviewQuestion, JobProfile, MatchResult, ScreeningResult
from recruitment_system.tools.interview_tools import QuestionGenerationTool


class InterviewAgent:
    """Chooses an interview strategy and creates an interview plan."""

    def __init__(
        self,
        question_tool: QuestionGenerationTool | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.question_tool = question_tool or QuestionGenerationTool()
        self.llm_client = llm_client

    def run(
        self,
        candidate: CandidateProfile,
        job: JobProfile,
        match_result: MatchResult,
        screening_result: ScreeningResult,
    ) -> InterviewPlan:
        focus_areas = self._focus_areas(candidate, job, match_result)
        if screening_result.recommendation == "not_recommended":
            strategy = "risk_review_only"
            interview_type = "manual_review"
            decision_reason = "初筛暂不推荐，仅生成风险复核问题"
            questions = []
        elif screening_result.requires_human_review:
            strategy = "risk_based_technical_interview"
            interview_type = "technical_first_round_with_review"
            decision_reason = "候选人具备面试价值，但存在缺口或风险，需要重点验证"
            questions = self.question_tool.generate_focus_questions(focus_areas)
        else:
            strategy = "standard_technical_interview"
            interview_type = "technical_first_round"
            decision_reason = "候选人与岗位匹配度较高，进入标准技术面"
            questions = self.question_tool.generate_focus_questions(focus_areas)

        risk_questions = self.question_tool.generate_risk_questions(screening_result.risk_points)
        rule_plan = InterviewPlan(
            interview_type=interview_type,
            selected_strategy=strategy,
            decision_reason=decision_reason,
            focus_areas=focus_areas,
            questions=questions,
            risk_validation_questions=risk_questions,
            requires_human_review=screening_result.requires_human_review,
            summary=f"{decision_reason}。建议关注：{', '.join(focus_areas[:5]) if focus_areas else '暂无明确重点'}。",
        )
        if self.llm_client is None:
            return rule_plan
        try:
            return self._run_llm(candidate, job, match_result, screening_result, rule_plan)
        except Exception:
            return rule_plan

    def _focus_areas(self, candidate: CandidateProfile, job: JobProfile, match_result: MatchResult) -> list[str]:
        focus = [skill for skill in job.required_skills if skill in candidate.skills]
        focus.extend(requirement.replace("技能缺失：", "") for requirement in match_result.missing_requirements)
        if candidate.projects:
            focus.append("项目经历真实性")
        if candidate.work_experience:
            focus.append("工作经历深度")
        return list(dict.fromkeys(focus))

    def _run_llm(
        self,
        candidate: CandidateProfile,
        job: JobProfile,
        match_result: MatchResult,
        screening_result: ScreeningResult,
        rule_plan: InterviewPlan,
    ) -> InterviewPlan:
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 Interview Agent。请根据候选人画像、岗位要求、匹配结果和初筛建议，选择面试策略并生成面试计划。"
                "只返回 JSON object。字段：interview_type, selected_strategy, decision_reason, focus_areas,"
                "questions, risk_validation_questions, requires_human_review, summary。"
                "questions 和 risk_validation_questions 是对象数组，每项包含 category, question, reason，可选 risk。"
            ),
            user_payload={
                "candidate_profile": asdict(candidate),
                "job_profile": asdict(job),
                "match_result": asdict(match_result),
                "screening_result": asdict(screening_result),
                "rule_plan": asdict(rule_plan),
            },
        )
        return InterviewPlan(
            interview_type=str(data.get("interview_type") or rule_plan.interview_type),
            selected_strategy=str(data.get("selected_strategy") or rule_plan.selected_strategy),
            decision_reason=str(data.get("decision_reason") or rule_plan.decision_reason),
            focus_areas=self._str_list(data.get("focus_areas")) or rule_plan.focus_areas,
            questions=self._questions(data.get("questions")) or rule_plan.questions,
            risk_validation_questions=self._questions(data.get("risk_validation_questions")) or rule_plan.risk_validation_questions,
            requires_human_review=bool(data.get("requires_human_review", rule_plan.requires_human_review)),
            summary=str(data.get("summary") or rule_plan.summary),
        )

    def _str_list(self, value: object) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []

    def _questions(self, value: object) -> list[InterviewQuestion]:
        if not isinstance(value, list):
            return []
        questions: list[InterviewQuestion] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if not question or not reason:
                continue
            risk = item.get("risk")
            questions.append(
                InterviewQuestion(
                    category=str(item.get("category") or "general"),
                    question=question,
                    reason=reason,
                    risk=str(risk).strip() if risk else None,
                )
            )
        return questions
