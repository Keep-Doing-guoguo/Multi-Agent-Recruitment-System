from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4


EducationLevel = Literal["unknown", "associate", "bachelor", "master", "doctor"]
DocumentPurpose = Literal["resume", "jd"]


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
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
