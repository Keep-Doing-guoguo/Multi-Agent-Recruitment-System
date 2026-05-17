from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4


EducationLevel = Literal["unknown", "associate", "bachelor", "master", "doctor"]
DocumentPurpose = Literal["resume", "jd"]
ScreeningRecommendation = Literal["recommend_interview", "manual_review", "not_recommended"]
FinalRecommendation = Literal["proceed_to_interview", "manual_review", "reject"]


@dataclass
class DocumentExtractionResult:
    source: str
    purpose: DocumentPurpose
    file_type: str = "text"
    extracted_text: str = ""
    confidence: float = 1.0
    layout_blocks: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class CandidateProfile:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = field(default_factory=list)
    years_experience: int | None = None
    education_level: EducationLevel = "unknown"
    projects: list[str] = field(default_factory=list)
    work_experience: list[str] = field(default_factory=list)
    uncertain_fields: list[str] = field(default_factory=list)


@dataclass
class JobProfile:
    title: str | None = None
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    min_years_experience: int | None = None
    education_level: EducationLevel = "unknown"
    responsibilities: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    match_score: int
    matched_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ScreeningResult:
    recommendation: ScreeningRecommendation
    confidence: float
    reasons: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    requires_human_review: bool = False
    summary: str = ""


@dataclass
class InterviewQuestion:
    category: str
    question: str
    reason: str
    risk: str | None = None


@dataclass
class InterviewPlan:
    interview_type: str
    selected_strategy: str
    decision_reason: str
    focus_areas: list[str] = field(default_factory=list)
    questions: list[InterviewQuestion] = field(default_factory=list)
    risk_validation_questions: list[InterviewQuestion] = field(default_factory=list)
    requires_human_review: bool = False
    summary: str = ""


@dataclass
class SupervisorReview:
    final_recommendation: FinalRecommendation
    decision_reason: str
    key_reasons: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    human_review_required: bool = False
    summary: str = ""


@dataclass
class WorkflowState:
    resume_input: str
    jd_input: str
    resume_text: str = ""
    jd_text: str = ""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid4()))
    resume_document: DocumentExtractionResult | None = None
    jd_document: DocumentExtractionResult | None = None
    candidate_profile: CandidateProfile | None = None
    job_profile: JobProfile | None = None
    match_result: MatchResult | None = None
    screening_result: ScreeningResult | None = None
    interview_plan: InterviewPlan | None = None
    supervisor_review: SupervisorReview | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
