from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .service import IntegratedDashboardService


class ProfileRequest(BaseModel):
    student_id: str
    nationality: str
    preferred_language: str | None = None


class StudentPreferredLanguageRequest(BaseModel):
    student_id: str
    preferred_language: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    username: str


class GlossaryTermRequest(BaseModel):
    source: str
    targets: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class GlossaryRequest(BaseModel):
    terms: list[GlossaryTermRequest]


class TextResourceRequest(BaseModel):
    lecturer_id: str
    course_code: str
    title: str
    content_text: str
    session_id: str | None = None
    topic: str | None = None
    week: str | None = None
    semester: str | None = None
    academic_year: str | None = None
    visibility: str = "enrolled"


class TranslateTextRequest(BaseModel):
    student_id: str
    text: str
    course_code: str | None = None
    source_language: str = "en"
    target_language: str | None = None
    nationality: str | None = None
    content_type: str = "notes"
    bilingual: bool | None = None


class TranslateResourceRequest(BaseModel):
    student_id: str
    resource_id: str
    target_language: str | None = None
    nationality: str | None = None
    bilingual: bool = True


class TimetableRequest(BaseModel):
    student_id: str
    available_hours_per_week: int = Field(default=12, ge=4, le=40)
    preferred_times: list[str] = Field(default_factory=list)


class StudyPlanRequest(BaseModel):
    student_id: str
    study_hours_per_week: int = Field(default=12, ge=4, le=40)


class LectureSessionCreateRequest(BaseModel):
    lecturer_id: str
    course_code: str
    lecture_number: int | None = Field(default=None, ge=1, le=99)
    title: str | None = None
    topic: str | None = None
    status: str = "Delivered"
    date_or_week: str | None = None
    notes_text: str | None = None


class LectureSessionUpdateRequest(BaseModel):
    lecturer_id: str
    lecture_number: int | None = Field(default=None, ge=1, le=99)
    title: str | None = None
    topic: str | None = None
    status: str | None = None
    date_or_week: str | None = None
    notes_text: str | None = None


class QuizGenerateRequest(BaseModel):
    lecturer_id: str
    course_code: str
    topic: str | None = None
    resource_id: str | None = None
    question_count: int = Field(default=3, ge=2)


class QuizAttemptRequest(BaseModel):
    student_id: str
    answers: list[int] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    student_id: str
    course_code: str
    difficulty_area: str
    comment: str
    topic: str | None = None
    resource_id: str | None = None


class ChatRequest(BaseModel):
    course_code: str
    question: str
    student_id: str | None = None
    resource_id: str | None = None
    topic: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=10)
    translate_response: bool = False
    target_language: str | None = None
    nationality: str | None = None
    bilingual: bool = True


service = IntegratedDashboardService()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static_dashboard"
app = FastAPI(
    title="IUIU Kampala Campus ERP System",
    version="1.0.0",
    description="IUIU Kampala Campus academic ERP portal for lecturers, students, resources, translation, quizzes, feedback, and course support.",
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


@app.post("/auth/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    try:
        return service.authenticate_user(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest) -> dict[str, str]:
    try:
        return service.request_password_reset(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/admin/overview")
def admin_overview() -> dict[str, Any]:
    return service.admin_overview()


@app.get("/lecturer/{lecturer_id}")
def lecturer_workspace(lecturer_id: str, course_code: str | None = None) -> dict[str, Any]:
    return service.lecturer_workspace(lecturer_id=lecturer_id, course_code=course_code)


@app.get("/lecturer/{lecturer_id}/rooms/{course_code}/sessions")
def list_lecture_sessions(lecturer_id: str, course_code: str) -> dict[str, Any]:
    try:
        return service.list_lecture_sessions(lecturer_id=lecturer_id, course_code=course_code)
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/lecturer/{lecturer_id}/rooms/{course_code}/sessions")
def create_lecture_session(
    lecturer_id: str,
    course_code: str,
    payload: LectureSessionCreateRequest,
) -> dict[str, Any]:
    try:
        body = payload.model_dump()
        body["lecturer_id"] = lecturer_id
        body["course_code"] = course_code
        return service.create_lecture_session(**body)
    except ValueError as error:
        raise bad_request(error) from error


@app.patch("/lecturer/sessions/{session_id}")
def update_lecture_session(session_id: str, payload: LectureSessionUpdateRequest) -> dict[str, Any]:
    try:
        return service.update_lecture_session(session_id=session_id, **payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/lecturer/sessions/{session_id}/attachments")
async def add_session_attachments(
    session_id: str,
    lecturer_id: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    try:
        prepared_files = []
        for file in files:
            prepared_files.append(
                {
                    "filename": file.filename or "upload.bin",
                    "content": await file.read(),
                    "content_type": file.content_type,
                }
            )
        return service.add_session_attachments(
            session_id=session_id,
            lecturer_id=lecturer_id,
            files=prepared_files,
        )
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/admin/profiles")
def list_profiles() -> list[dict[str, Any]]:
    return service.list_profiles()


@app.post("/admin/profiles")
def upsert_profile(payload: ProfileRequest) -> dict[str, Any]:
    try:
        return service.upsert_profile(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/student/profile/language")
def update_student_preferred_language(payload: StudentPreferredLanguageRequest) -> dict[str, Any]:
    try:
        return service.update_student_preferred_language(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/admin/glossary")
def glossary_overview() -> list[dict[str, Any]]:
    return service.glossary_overview()


@app.get("/admin/glossary/{course_code}")
def get_glossary(course_code: str) -> list[dict[str, Any]]:
    return service.get_glossary(course_code)


@app.post("/admin/glossary/{course_code}")
def add_glossary(course_code: str, payload: GlossaryRequest) -> list[dict[str, Any]]:
    try:
        return service.add_glossary_terms(
            course_code=course_code,
            terms=[term.model_dump() for term in payload.terms],
        )
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/admin/resources")
def list_resources(course_code: str | None = None) -> list[dict[str, Any]]:
    return service.list_resources(course_code=course_code)


@app.post("/admin/resources/text")
def add_text_resource(payload: TextResourceRequest) -> dict[str, Any]:
    try:
        return service.add_text_resource(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/admin/resources/upload")
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


@app.get("/student/{student_id}")
def student_workspace(student_id: str, course_code: str | None = None) -> dict[str, Any]:
    return service.student_workspace(student_id=student_id, course_code=course_code)


@app.post("/student/timetables/generate")
def generate_timetable(payload: TimetableRequest) -> dict[str, Any]:
    try:
        return service.generate_student_timetable(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/student/study-plans/generate")
def generate_study_plan(payload: StudyPlanRequest) -> dict[str, Any]:
    try:
        return service.generate_study_plan(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/student/{student_id}/quizzes")
def list_student_quizzes(student_id: str, course_code: str | None = None) -> dict[str, Any]:
    try:
        return service.list_student_quizzes(student_id=student_id, course_code=course_code)
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/student/translate")
def translate_text(payload: TranslateTextRequest) -> dict[str, Any]:
    try:
        return service.translate_text(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/student/resources/translate")
def translate_resource(payload: TranslateResourceRequest) -> dict[str, Any]:
    try:
        return service.translate_resource(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/student/resources/{resource_id}/pdf")
def open_student_resource_pdf(
    resource_id: str,
    student_id: str,
    translate: bool = True,
    target_language: str | None = None,
) -> Response:
    try:
        result = service.build_resource_pdf(
            student_id=student_id,
            resource_id=resource_id,
            translate=translate,
            target_language=target_language,
        )
        return Response(
            content=result["content"],
            media_type=result.get("media_type", "application/pdf"),
            headers={
                "Content-Disposition": f'inline; filename="{result["filename"]}"',
                "Cache-Control": "no-store",
            },
        )
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/student/quizzes/{quiz_id}/attempt")
def attempt_quiz(quiz_id: str, payload: QuizAttemptRequest) -> dict[str, Any]:
    try:
        return service.submit_quiz_attempt(quiz_id=quiz_id, **payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/student/feedback")
def submit_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    try:
        return service.submit_feedback(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.post("/lecturer/quizzes/generate")
def generate_quiz(payload: QuizGenerateRequest) -> dict[str, Any]:
    try:
        return service.generate_quiz(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error


@app.get("/lecturer/{lecturer_id}/feedback")
def lecturer_feedback(lecturer_id: str, course_code: str | None = None) -> dict[str, Any]:
    return service.lecturer_feedback(lecturer_id=lecturer_id, course_code=course_code)


@app.post("/student/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    try:
        return service.chat(**payload.model_dump())
    except ValueError as error:
        raise bad_request(error) from error
