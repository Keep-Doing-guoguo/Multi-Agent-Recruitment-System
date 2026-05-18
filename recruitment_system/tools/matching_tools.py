from __future__ import annotations

from recruitment_system.llm.base import StructuredLLMClient
from recruitment_system.models import CandidateProfile, JobProfile, MatchResult
from recruitment_system.text_utils import extract_education_level, extract_skills, extract_years_experience, split_lines


EDUCATION_RANK = {
    "unknown": 0,
    "associate": 1,
    "bachelor": 2,
    "master": 3,
    "doctor": 4,
}


class JDParserTool:
    """把标准化 JD 文本解析为岗位画像。"""

    def __init__(self, llm_client: StructuredLLMClient | None = None) -> None:
        """初始化 JD 解析工具，可选接入 LLM 做结构化抽取。"""
        self.llm_client = llm_client

    def parse(self, jd_text: str) -> JobProfile:
        """抽取岗位名称、技能要求、年限、学历和职责摘要。"""
        if self.llm_client is not None:
            try:
                return self._parse_with_llm(jd_text)
            except Exception:
                pass
        return self._parse_with_rules(jd_text)

    def _parse_with_rules(self, jd_text: str) -> JobProfile:
        """使用规则工具解析 JD，作为默认实现和 LLM 失败兜底。"""
        lines = split_lines(jd_text)
        return JobProfile(
            title=self._extract_title(lines),
            required_skills=extract_skills(jd_text),
            min_years_experience=extract_years_experience(jd_text),
            education_level=extract_education_level(jd_text),  # type: ignore[arg-type]
            responsibilities=lines[:8],
        )

    def _parse_with_llm(self, jd_text: str) -> JobProfile:
        """调用 LLM 从 JD 文本中抽取结构化岗位画像。"""
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 JD Parser Tool。请从岗位 JD 中抽取结构化岗位画像。"
                "只返回 JSON object，不要返回 Markdown。字段必须包括："
                "title, required_skills, preferred_skills, min_years_experience, education_level, responsibilities。"
                "education_level 只能是 unknown, associate, bachelor, master, doctor。"
            ),
            user_payload={"jd_text": jd_text},
        )
        return JobProfile(
            title=self._optional_str(data.get("title")),
            required_skills=self._str_list(data.get("required_skills")),
            preferred_skills=self._str_list(data.get("preferred_skills")),
            min_years_experience=self._optional_int(data.get("min_years_experience")),
            education_level=self._education(data.get("education_level")),  # type: ignore[arg-type]
            responsibilities=self._str_list(data.get("responsibilities")),
        )

    def _extract_title(self, lines: list[str]) -> str | None:
        """从 JD 前几行中提取岗位标题。"""
        for line in lines[:5]:
            if any(keyword in line for keyword in ("岗位", "职位", "Job", "Role", "Title")):
                return line.split(":", 1)[-1].split("：", 1)[-1].strip()
        return lines[0] if lines else None

    def _optional_str(self, value: object) -> str | None:
        """把可选字段转换为去空格字符串，空值返回 None。"""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _str_list(self, value: object) -> list[str]:
        """把模型返回值转换为字符串列表。"""
        return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []

    def _optional_int(self, value: object) -> int | None:
        """把可选数字字段转换为 int，无法转换时返回 None。"""
        if value is None or value == "":
            return None
        try:
            return int(float(str(value)))
        except ValueError:
            return None

    def _education(self, value: object) -> str:
        """校验并归一化学历枚举值。"""
        text = str(value or "unknown").strip()
        return text if text in {"unknown", "associate", "bachelor", "master", "doctor"} else "unknown"


class MatchScoringTool:
    """计算候选人与岗位的匹配分，并输出可解释风险点。"""

    def score(self, candidate: CandidateProfile, job: JobProfile) -> MatchResult:
        """按照技能、年限和学历维度计算匹配结果。"""
        matched_skills = [skill for skill in job.required_skills if skill in candidate.skills]
        missing_skills = [skill for skill in job.required_skills if skill not in candidate.skills]

        score_parts: list[float] = []
        risk_points: list[str] = []

        if job.required_skills:
            score_parts.append((len(matched_skills) / len(job.required_skills)) * 70)
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
            if EDUCATION_RANK[candidate.education_level] >= EDUCATION_RANK[job.education_level]:
                score_parts.append(10)
            else:
                risk_points.append("学历要求未明确满足")
                score_parts.append(0)

        if missing_skills:
            risk_points.append("缺少关键技能：" + ", ".join(missing_skills))

        score = min(100, round(sum(score_parts)))
        return MatchResult(
            match_score=score,
            matched_requirements=[f"技能匹配：{skill}" for skill in matched_skills],
            missing_requirements=[f"技能缺失：{skill}" for skill in missing_skills],
            risk_points=risk_points,
            summary=self._build_summary(score, matched_skills, missing_skills, risk_points),
        )

    def _build_summary(self, score: int, matched_skills: list[str], missing_skills: list[str], risk_points: list[str]) -> str:
        """根据评分、命中项、缺失项和风险点生成中文摘要。"""
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
