from __future__ import annotations

import re

from recruitment_system.models import CandidateProfile
from recruitment_system.text_utils import (
    extract_education_level,
    extract_email,
    extract_phone,
    extract_skills,
    extract_years_experience,
    split_lines,
)


class ResumeFieldExtractorTool:
    """从标准化简历文本中抽取候选人结构化字段。"""

    def extract(self, resume_text: str) -> CandidateProfile:
        """抽取姓名、联系方式、技能、年限、学历、项目和工作经历。"""
        lines = split_lines(resume_text)
        profile = CandidateProfile(
            name=self._extract_name(lines),
            email=extract_email(resume_text),
            phone=extract_phone(resume_text),
            skills=extract_skills(resume_text),
            years_experience=extract_years_experience(resume_text),
            education_level=extract_education_level(resume_text),  # type: ignore[arg-type]
            projects=self._extract_section_items(lines, ("项目", "projects")),
            work_experience=self._extract_section_items(lines, ("工作经历", "工作经验", "experience")),
        )

        if not profile.skills:
            profile.uncertain_fields.append("skills")
        if profile.years_experience is None:
            profile.uncertain_fields.append("years_experience")
        if profile.education_level == "unknown":
            profile.uncertain_fields.append("education_level")
        return profile

    def _extract_name(self, lines: list[str]) -> str | None:
        """从简历前几行中抽取姓名。"""
        for line in lines[:5]:
            match = re.search(r"(?:姓名|Name)[:：]\s*([A-Za-z\u4e00-\u9fff .-]{2,40})", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        if lines and 2 <= len(lines[0]) <= 40 and not any(char in lines[0] for char in "@:："):
            return lines[0]
        return None

    def _extract_section_items(self, lines: list[str], headers: tuple[str, ...]) -> list[str]:
        """根据章节标题抽取项目经历或工作经历条目。"""
        items: list[str] = []
        collecting = False
        for line in lines:
            lowered = line.lower()
            if any(header.lower() in lowered for header in headers):
                collecting = True
                continue
            if collecting and re.search(r"(教育|技能|项目|证书|自我评价|education|skills|projects|certifications)", lowered):
                break
            if collecting:
                items.append(line)
            if len(items) >= 5:
                break
        return items
