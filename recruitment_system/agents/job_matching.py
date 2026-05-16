from __future__ import annotations

from recruitment_system.models import CandidateProfile, JobProfile, MatchResult
from recruitment_system.text_utils import extract_education_level, extract_skills, extract_years_experience, split_lines


EDUCATION_RANK = {
    "unknown": 0,
    "associate": 1,
    "bachelor": 2,
    "master": 3,
    "doctor": 4,
}


class JobMatchingAgent:
    """Parses a JD and compares it with a structured candidate profile."""

    def run(self, candidate: CandidateProfile, jd_text: str) -> tuple[JobProfile, MatchResult]:
        job = self._parse_job(jd_text)
        result = self._match(candidate, job)
        return job, result

    def _parse_job(self, jd_text: str) -> JobProfile:
        lines = split_lines(jd_text)
        required_skills = extract_skills(jd_text)
        min_years = extract_years_experience(jd_text)
        education = extract_education_level(jd_text)
        title = self._extract_title(lines)

        return JobProfile(
            title=title,
            required_skills=required_skills,
            min_years_experience=min_years,
            education_level=education,  # type: ignore[arg-type]
            responsibilities=lines[:8],
        )

    def _extract_title(self, lines: list[str]) -> str | None:
        for line in lines[:5]:
            if any(keyword in line for keyword in ("岗位", "职位", "Job", "Role", "Title")):
                return line.split(":", 1)[-1].split("：", 1)[-1].strip()
        return lines[0] if lines else None

    def _match(self, candidate: CandidateProfile, job: JobProfile) -> MatchResult:
        matched_skills = [skill for skill in job.required_skills if skill in candidate.skills]
        missing_skills = [skill for skill in job.required_skills if skill not in candidate.skills]

        score_parts: list[float] = []
        risk_points: list[str] = []

        if job.required_skills:
            skill_score = len(matched_skills) / len(job.required_skills)
            score_parts.append(skill_score * 70)
        else:
            risk_points.append("JD 未提取到明确技能要求")
            score_parts.append(35)

        if job.min_years_experience is not None:
            if candidate.years_experience is None:
                risk_points.append("候选人工作年限不明确")
                score_parts.append(5)
            elif candidate.years_experience >= job.min_years_experience:
                score_parts.append(20)
            else:
                risk_points.append(f"工作年限不足：要求 {job.min_years_experience} 年，候选人约 {candidate.years_experience} 年")
                score_parts.append(max(0, candidate.years_experience / job.min_years_experience) * 20)
        else:
            score_parts.append(10)

        if job.education_level != "unknown":
            candidate_rank = EDUCATION_RANK[candidate.education_level]
            job_rank = EDUCATION_RANK[job.education_level]
            if candidate_rank >= job_rank:
                score_parts.append(10)
            else:
                risk_points.append("学历要求未明确满足")
                score_parts.append(0)

        if missing_skills:
            risk_points.append("缺少关键技能：" + ", ".join(missing_skills))

        score = min(100, round(sum(score_parts)))
        matched_requirements = [f"技能匹配：{skill}" for skill in matched_skills]
        missing_requirements = [f"技能缺失：{skill}" for skill in missing_skills]
        summary = self._build_summary(score, matched_skills, missing_skills, risk_points)
        return MatchResult(
            match_score=score,
            matched_requirements=matched_requirements,
            missing_requirements=missing_requirements,
            risk_points=risk_points,
            summary=summary,
        )

    def _build_summary(
        self,
        score: int,
        matched_skills: list[str],
        missing_skills: list[str],
        risk_points: list[str],
    ) -> str:
        if score >= 80:
            level = "高度匹配"
        elif score >= 60:
            level = "基本匹配"
        elif score >= 40:
            level = "部分匹配"
        else:
            level = "匹配度较低"

        matched = "、".join(matched_skills) if matched_skills else "暂无明确命中技能"
        missing = "、".join(missing_skills) if missing_skills else "暂无明显技能缺口"
        risk = "；".join(risk_points) if risk_points else "暂无明显风险"
        return f"{level}（{score}/100）。命中：{matched}。缺口：{missing}。风险：{risk}。"
