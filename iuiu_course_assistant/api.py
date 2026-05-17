from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_settings
from .service import CourseAssistantService


class TextResourceRequest(BaseModel):
    lecturer_id: str
    course_code: str
    title: str
    content_text: str
    topic: str | None = None
    week: str | None = None
    semester: str | None = None
    academic_year: str | None = None
    visibility: str = "enrolled"


class ChatRequest(BaseModel):
    course_code: str
    question: str
    student_id: str | None = None
    topic: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=10)
    translate_response: bool = False
    target_language: str | None = None
    nationality: str | None = None
    bilingual: bool = True


settings = load_settings()
service = CourseAssistantService(settings=settings)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static_course_assistant"
app = FastAPI(
    title="IUIU Kampala Campus Course Assistant",
    version="1.0.0",
    description="IUIU Kampala Campus ERP module for academic resource indexing, virtual course support, course answers, and translation.",
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


@app.get("/resources")
def list_resources(course_code: str | None = None) -> list[dict[str, Any]]:
    return service.list_resources(course_code=course_code)


@app.get("/resources/{resource_id}")
def get_resource(resource_id: str) -> dict[str, Any]:
    resource = service.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@app.post("/resources/text")
def add_text_resource(payload: TextResourceRequest) -> dict[str, Any]:
    try:
        return service.add_text_resource(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/resources/upload")
async def upload_resource(
    lecturer_id: str = Form(...),
    course_code: str = Form(...),
    title: str = Form(...),
    topic: str | None = Form(None),
    week: str | None = Form(None),
    semester: str | None = Form(None),
    academic_year: str | None = Form(None),
    visibility: str = Form("enrolled"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        content = await file.read()
        return service.add_uploaded_resource(
            lecturer_id=lecturer_id,
            course_code=course_code,
            title=title,
            filename=file.filename or "upload.txt",
            content=content,
            topic=topic,
            week=week,
            semester=semester,
            academic_year=academic_year,
            visibility=visibility,
            content_type=file.content_type,
        )
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    try:
        return service.ask(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error
