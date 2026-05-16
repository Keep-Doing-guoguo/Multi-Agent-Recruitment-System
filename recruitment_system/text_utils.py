from __future__ import annotations

import re


SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("python",),
    "Java": ("java",),
    "JavaScript": ("javascript", "js"),
    "TypeScript": ("typescript", "ts"),
    "React": ("react",),
    "Vue": ("vue", "vue.js"),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Flask": ("flask",),
    "Spring Boot": ("spring boot", "springboot"),
    "Node.js": ("node.js", "nodejs", "node"),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "Redis": ("redis",),
    "MongoDB": ("mongodb", "mongo"),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "AWS": ("aws",),
    "GCP": ("gcp", "google cloud"),
    "Azure": ("azure",),
    "Linux": ("linux",),
    "Git": ("git",),
    "CI/CD": ("ci/cd", "cicd"),
    "Machine Learning": ("machine learning", "机器学习"),
    "LLM": ("llm", "大模型"),
}

EDUCATION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("doctor", ("博士", "phd", "doctor")),
    ("master", ("硕士", "研究生", "master")),
    ("bachelor", ("本科", "学士", "bachelor")),
    ("associate", ("大专", "专科", "associate")),
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_lines(text: str) -> list[str]:
    return [line.strip(" \t-•*") for line in text.splitlines() if line.strip()]


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    skills: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(re.search(rf"(?<![a-z0-9+#.]){re.escape(alias)}(?![a-z0-9+#.])", lowered) for alias in aliases):
            skills.append(canonical)
    return skills


def extract_years_experience(text: str) -> int | None:
    patterns = (
        r"(\d+)\s*\+?\s*年(?:以上)?[^，。\n；;]{0,12}经验",
        r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?experience",
        r"经验\s*(\d+)\s*\+?\s*年",
    )
    years = [int(match) for pattern in patterns for match in re.findall(pattern, text, flags=re.IGNORECASE)]
    return max(years) if years else None


def extract_education_level(text: str) -> str:
    lowered = text.lower()
    for level, patterns in EDUCATION_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return level
    return "unknown"


def extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    return match.group(0) if match else None


def extract_phone(text: str) -> str | None:
    match = re.search(r"(?:\+?86[- ]?)?1[3-9]\d{9}", text)
    if match:
        return match.group(0)
    match = re.search(r"\+?\d[\d -]{7,}\d", text)
    return match.group(0) if match else None
