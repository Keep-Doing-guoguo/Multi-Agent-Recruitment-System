from recruitment_system.models import CandidateProfile
from recruitment_system.llm import StructuredLLMClient
from recruitment_system.tools.resume_tools import ResumeFieldExtractorTool


class ResumeParsingAgent:
    """Extracts a structured candidate profile from resume text."""

    def __init__(
        self,
        field_extractor: ResumeFieldExtractorTool | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.field_extractor = field_extractor or ResumeFieldExtractorTool()
        self.llm_client = llm_client

    def run(self, resume_text: str) -> CandidateProfile:
        if self.llm_client is not None:
            try:
                return self._run_llm(resume_text)
            except Exception:
                pass
        return self.field_extractor.extract(resume_text)

    def _run_llm(self, resume_text: str) -> CandidateProfile:
        data = self.llm_client.generate_json(
            system_prompt=(
                "你是 Resume Parsing Agent。请从简历文本中抽取结构化候选人画像。"
                "只返回 JSON object，不要返回 Markdown。字段必须包括："
                "name,email,phone,skills,years_experience,education_level,projects,work_experience,uncertain_fields。"
                "education_level 只能是 unknown, associate, bachelor, master, doctor。"
            ),
            user_payload={"resume_text": resume_text},
        )
        profile = CandidateProfile(
            name=self._optional_str(data.get("name")),
            email=self._optional_str(data.get("email")),
            phone=self._optional_str(data.get("phone")),
            skills=self._str_list(data.get("skills")),
            years_experience=self._optional_int(data.get("years_experience")),
            education_level=self._education(data.get("education_level")),  # type: ignore[arg-type]
            projects=self._str_list(data.get("projects")),
            work_experience=self._str_list(data.get("work_experience")),
            uncertain_fields=self._str_list(data.get("uncertain_fields")),
        )
        if not profile.skills and "skills" not in profile.uncertain_fields:
            profile.uncertain_fields.append("skills")
        if profile.years_experience is None and "years_experience" not in profile.uncertain_fields:
            profile.uncertain_fields.append("years_experience")
        if profile.education_level == "unknown" and "education_level" not in profile.uncertain_fields:
            profile.uncertain_fields.append("education_level")
        return profile

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _str_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _optional_int(self, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value)))
        except ValueError:
            return None

    def _education(self, value: object) -> str:
        text = str(value or "unknown").strip()
        return text if text in {"unknown", "associate", "bachelor", "master", "doctor"} else "unknown"
