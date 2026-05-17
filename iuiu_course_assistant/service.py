from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import Settings
from .extractors import extract_text_from_upload
from .providers import AnswerProvider, build_provider
from .retrieval import best_snippet, chunk_text, rank_chunks, tokenize
from .storage import AuditLogRepository, ChunkRepository, ResourceRepository
from .translation_bridge import LocalTranslationBridge


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def slugify(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or fallback


class CourseAssistantService:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: AnswerProvider | None = None,
        translator: Any | None = None,
    ):
        self.settings = settings
        self.provider = provider or build_provider(settings.answer_provider)
        self.translator = translator if translator is not None else LocalTranslationBridge(
            enabled=settings.translation_enabled
        )
        self.resources = ResourceRepository(settings.data_dir / "resources.json")
        self.chunks = ChunkRepository(settings.data_dir / "resource_chunks.json")
        self.logs = AuditLogRepository(settings.data_dir / "course_assistant_logs.json")
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "provider": self.provider.name,
            "translation_bridge": bool(getattr(self.translator, "available", False)),
            "resource_count": self.resources.count(),
            "indexed_chunk_count": self.chunks.count(),
            "log_count": self.logs.count(),
        }

    def add_text_resource(
        self,
        *,
        lecturer_id: str,
        course_code: str,
        title: str,
        content_text: str,
        session_id: str | None = None,
        topic: str | None = None,
        week: str | None = None,
        semester: str | None = None,
        academic_year: str | None = None,
        visibility: str = "enrolled",
    ) -> dict[str, Any]:
        if not lecturer_id.strip():
            raise ValueError("lecturer_id is required")
        if not course_code.strip():
            raise ValueError("course_code is required")
        if not title.strip():
            raise ValueError("title is required")
        if not content_text.strip():
            raise ValueError("content_text is required")

        resource_id = self._new_resource_id()
        safe_title = slugify(title, fallback="resource")
        stored_name = f"{resource_id}-{safe_title}.txt"
        stored_path = self.settings.upload_dir / stored_name
        stored_path.write_text(content_text.strip(), encoding="utf-8")

        return self._store_resource(
            resource_id=resource_id,
            lecturer_id=lecturer_id,
            course_code=course_code,
            title=title,
            session_id=session_id,
            topic=topic,
            week=week,
            semester=semester,
            academic_year=academic_year,
            visibility=visibility,
            source_type="text",
            content_type="text/plain",
            original_filename=stored_name,
            stored_path=stored_path,
            extracted_text=content_text,
        )

    def add_uploaded_resource(
        self,
        *,
        lecturer_id: str,
        course_code: str,
        title: str,
        filename: str,
        content: bytes,
        session_id: str | None = None,
        topic: str | None = None,
        week: str | None = None,
        semester: str | None = None,
        academic_year: str | None = None,
        visibility: str = "enrolled",
        content_type: str | None = None,
    ) -> dict[str, Any]:
        if not filename.strip():
            raise ValueError("filename is required")
        if not content:
            raise ValueError("Uploaded file is empty")

        resource_id = self._new_resource_id()
        safe_name = slugify(Path(filename).stem, fallback="resource")
        suffix = Path(filename).suffix or ".bin"
        stored_name = f"{resource_id}-{safe_name}{suffix}"
        stored_path = self.settings.upload_dir / stored_name
        stored_path.write_bytes(content)
        extracted_text = extract_text_from_upload(filename, content)
        indexed = bool(extracted_text.strip())
        index_error = None
        if not indexed and suffix.lower() == ".pdf":
            index_error = "No readable text could be extracted from the PDF."

        return self._store_resource(
            resource_id=resource_id,
            lecturer_id=lecturer_id,
            course_code=course_code,
            title=title,
            session_id=session_id,
            topic=topic,
            week=week,
            semester=semester,
            academic_year=academic_year,
            visibility=visibility,
            source_type="upload",
            content_type=content_type or "application/octet-stream",
            original_filename=filename,
            stored_path=stored_path,
            extracted_text=extracted_text,
            allow_empty_text=True,
            index_error=index_error,
        )

    def list_resources(self, course_code: str | None = None) -> list[dict[str, Any]]:
        return self.resources.list(course_code=course_code)

    def get_resource(self, resource_id: str) -> dict[str, Any] | None:
        return self.resources.get(resource_id)

    def ask(
        self,
        *,
        course_code: str,
        question: str,
        student_id: str | None = None,
        resource_id: str | None = None,
        topic: str | None = None,
        top_k: int | None = None,
        translate_response: bool = False,
        target_language: str | None = None,
        nationality: str | None = None,
        bilingual: bool = True,
    ) -> dict[str, Any]:
        if not course_code.strip():
            raise ValueError("course_code is required")
        if not question.strip():
            raise ValueError("question is required")

        effective_top_k = top_k or self.settings.default_top_k
        available_chunks = self.chunks.list(course_code=course_code, topic=topic)
        if resource_id:
            available_chunks = [
                chunk for chunk in available_chunks if chunk.get("resource_id") == resource_id.strip()
            ]
        ranked_chunks = rank_chunks(
            question=question,
            chunks=available_chunks,
            top_k=effective_top_k,
        )
        answer_result = self.provider.answer(
            question=question,
            course_code=course_code,
            retrieved_chunks=ranked_chunks,
        )

        response = {
            "course_code": course_code.strip().upper(),
            "question": question.strip(),
            "resource_id": resource_id.strip() if resource_id else None,
            "topic": topic.strip() if topic else None,
            "provider": self.provider.name,
            "answer_text": answer_result.text,
            "citations": answer_result.citations,
            "matches": [
                {
                    "resource_id": chunk["resource_id"],
                    "chunk_id": chunk["chunk_id"],
                    "title": chunk["title"],
                    "topic": chunk.get("topic"),
                    "score": chunk["score"],
                    "snippet": best_snippet(chunk.get("text", ""), question),
                }
                for chunk in ranked_chunks
            ],
            "answered_at": utc_now_iso(),
        }

        if translate_response:
            if not student_id:
                raise ValueError("student_id is required when translate_response is enabled")
            if getattr(self.translator, "available", False):
                try:
                    response["translation"] = self.translator.translate_answer(
                        student_id=student_id,
                        course_code=course_code.strip().upper(),
                        text=answer_result.text,
                        target_language=target_language,
                        nationality=nationality,
                        bilingual=bilingual,
                    )
                except Exception as error:
                    response["translation_error"] = str(error)
            else:
                response["translation_error"] = "Translation bridge is unavailable"

        self.logs.append(
            {
                "event": "chat_answered",
                "course_code": course_code.strip().upper(),
                "student_id": student_id,
                "resource_id": resource_id.strip() if resource_id else None,
                "topic": topic.strip() if topic else None,
                "translate_response": translate_response,
                "match_count": len(ranked_chunks),
                "timestamp": utc_now_iso(),
            }
        )
        return response

    def _store_resource(
        self,
        *,
        resource_id: str,
        lecturer_id: str,
        course_code: str,
        title: str,
        session_id: str | None,
        topic: str | None,
        week: str | None,
        semester: str | None,
        academic_year: str | None,
        visibility: str,
        source_type: str,
        content_type: str,
        original_filename: str,
        stored_path: Path,
        extracted_text: str,
        allow_empty_text: bool = False,
        index_error: str | None = None,
    ) -> dict[str, Any]:
        if not lecturer_id.strip():
            raise ValueError("lecturer_id is required")
        if not course_code.strip():
            raise ValueError("course_code is required")
        if not title.strip():
            raise ValueError("title is required")

        normalized_text = extracted_text.strip()
        if not normalized_text and not allow_empty_text:
            raise ValueError("No indexable text was found in the supplied resource")

        version = self._next_version(course_code=course_code, title=title)
        chunks = (
            self._build_chunks(
                resource_id=resource_id,
                course_code=course_code,
                title=title,
                topic=topic,
                text=normalized_text,
            )
            if normalized_text
            else []
        )
        created_at = utc_now_iso()
        payload = {
            "resource_id": resource_id,
            "course_code": course_code.strip().upper(),
            "title": title.strip(),
            "session_id": session_id.strip() if session_id else None,
            "topic": topic.strip() if topic else None,
            "week": week.strip() if week else None,
            "semester": semester.strip() if semester else None,
            "academic_year": academic_year.strip() if academic_year else None,
            "visibility": visibility.strip() or "enrolled",
            "lecturer_id": lecturer_id.strip(),
            "source_type": source_type,
            "content_type": content_type,
            "original_filename": original_filename,
            "stored_path": str(stored_path),
            "version": version,
            "chunk_count": len(chunks),
            "excerpt": normalized_text[:240] if normalized_text else "Stored for viewing. No readable text was indexed.",
            "created_at": created_at,
            "indexed": bool(normalized_text),
            "indexed_at": created_at if normalized_text else None,
            "index_error": index_error,
        }

        self.resources.upsert(payload)
        self.chunks.replace_for_resource(resource_id, chunks)
        self.logs.append(
            {
                "event": "resource_indexed" if normalized_text else "resource_uploaded_unindexed",
                "resource_id": resource_id,
                "course_code": payload["course_code"],
                "title": payload["title"],
                "chunk_count": len(chunks),
                "index_error": index_error,
                "timestamp": created_at,
            }
        )
        return payload

    def _build_chunks(
        self,
        *,
        resource_id: str,
        course_code: str,
        title: str,
        topic: str | None,
        text: str,
    ) -> list[dict[str, Any]]:
        text_chunks = chunk_text(
            text,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
        built_chunks: list[dict[str, Any]] = []
        for position, value in enumerate(text_chunks, start=1):
            built_chunks.append(
                {
                    "chunk_id": f"{resource_id}-c{position}",
                    "resource_id": resource_id,
                    "course_code": course_code.strip().upper(),
                    "title": title.strip(),
                    "topic": topic.strip() if topic else None,
                    "position": position,
                    "text": value,
                    "terms": sorted(tokenize(value)),
                }
            )
        return built_chunks

    def _next_version(self, *, course_code: str, title: str) -> int:
        existing_resources = self.resources.list(course_code=course_code)
        matching = [
            resource
            for resource in existing_resources
            if resource.get("title", "").casefold() == title.strip().casefold()
        ]
        return len(matching) + 1

    def _new_resource_id(self) -> str:
        return uuid4().hex[:12]
