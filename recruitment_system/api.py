from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile

from recruitment_system.services.resume_service import ResumeParsingService


app = FastAPI(title="Multi-Agent Recruitment System API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/resume/parse")
async def parse_resume(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空")

    service = ResumeParsingService()
    return service.parse_uploaded_file(file.filename or "resume.txt", content)
