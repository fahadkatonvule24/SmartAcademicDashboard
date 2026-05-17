from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_settings
from .service import TranslationService


class ProfileRequest(BaseModel):
    student_id: str
    nationality: str
    preferred_language: str | None = None


class GlossaryTermRequest(BaseModel):
    source: str
    targets: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class GlossaryRequest(BaseModel):
    terms: list[GlossaryTermRequest]


class TranslationRequest(BaseModel):
    student_id: str
    text: str
    course_code: str | None = None
    source_language: str = "en"
    target_language: str | None = None
    nationality: str | None = None
    content_type: str = "notes"
    bilingual: bool | None = None


settings = load_settings()
service = TranslationService(settings=settings)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(
    title="IUIU Kampala Campus NLP Translation Service",
    version="1.0.0",
    description="IUIU Kampala Campus ERP translation module for student mother-tongue support, glossary protection, bilingual output, and translation caching.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health() -> dict[str, Any]:
    return service.health()


@app.get("/languages")
def languages() -> list[dict[str, str]]:
    return service.supported_languages()


@app.post("/profiles")
def upsert_profile(payload: ProfileRequest) -> dict[str, Any]:
    try:
        return service.upsert_profile(
            student_id=payload.student_id,
            nationality=payload.nationality,
            preferred_language=payload.preferred_language,
        )
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/profiles/{student_id}")
def get_profile(student_id: str) -> dict[str, Any]:
    profile = service.get_profile(student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.post("/glossary/{course_code}")
def add_glossary(course_code: str, payload: GlossaryRequest) -> list[dict[str, Any]]:
    try:
        return service.add_glossary_terms(
            course_code=course_code,
            terms=[term.model_dump() for term in payload.terms],
        )
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/glossary/{course_code}")
def get_glossary(course_code: str) -> list[dict[str, Any]]:
    return service.get_glossary(course_code)


@app.post("/translate")
def translate(payload: TranslationRequest) -> dict[str, Any]:
    try:
        return service.translate(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error
