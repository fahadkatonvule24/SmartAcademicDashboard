from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


class JsonFileStore:
    def __init__(self, path: Path, default_factory: Callable[[], Any]):
        self.path = path
        self.default_factory = default_factory
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(self.default_factory())

    def read(self) -> Any:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            data = self.default_factory()
            self.write(data)
            return data

    def write(self, data: Any) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)


class TimetableRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get(self, student_id: str) -> dict[str, Any] | None:
        payload = self.store.read().get(student_id)
        return deepcopy(payload) if payload else None

    def upsert(self, student_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[student_id] = payload
        self.store.write(data)
        return deepcopy(payload)


class StudyPlanRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get(self, student_id: str) -> dict[str, Any] | None:
        payload = self.store.read().get(student_id)
        return deepcopy(payload) if payload else None

    def upsert(self, student_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[student_id] = payload
        self.store.write(data)
        return deepcopy(payload)


class QuizRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get(self, quiz_id: str) -> dict[str, Any] | None:
        payload = self.store.read().get(quiz_id)
        return deepcopy(payload) if payload else None

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[payload["quiz_id"]] = payload
        self.store.write(data)
        return deepcopy(payload)

    def list(
        self,
        *,
        course_code: str | None = None,
        lecturer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        values = list(self.store.read().values())
        if course_code:
            values = [
                value for value in values if value.get("course_code") == course_code.strip().upper()
            ]
        if lecturer_id:
            values = [value for value in values if value.get("lecturer_id") == lecturer_id.strip()]
        values.sort(key=lambda item: item.get("generated_at", ""), reverse=True)
        return deepcopy(values)


class QuizAttemptRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, list)

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data.append(payload)
        self.store.write(data)
        return deepcopy(payload)

    def list(
        self,
        *,
        student_id: str | None = None,
        quiz_id: str | None = None,
    ) -> list[dict[str, Any]]:
        values = self.store.read()
        if student_id:
            values = [value for value in values if value.get("student_id") == student_id.strip()]
        if quiz_id:
            values = [value for value in values if value.get("quiz_id") == quiz_id.strip()]
        values.sort(key=lambda item: item.get("submitted_at", ""), reverse=True)
        return deepcopy(values)


class LectureSessionRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get(self, session_id: str) -> dict[str, Any] | None:
        payload = self.store.read().get(session_id)
        return deepcopy(payload) if payload else None

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[payload["session_id"]] = payload
        self.store.write(data)
        return deepcopy(payload)

    def list(
        self,
        *,
        lecturer_id: str | None = None,
        course_code: str | None = None,
    ) -> list[dict[str, Any]]:
        values = list(self.store.read().values())
        if lecturer_id:
            values = [value for value in values if value.get("lecturer_id") == lecturer_id.strip()]
        if course_code:
            values = [
                value for value in values if value.get("course_code") == course_code.strip().upper()
            ]
        values.sort(
            key=lambda item: (
                int(item.get("lecture_number") or 9999),
                item.get("created_at", ""),
            )
        )
        return deepcopy(values)


class FeedbackRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, list)

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data.append(payload)
        self.store.write(data)
        return deepcopy(payload)

    def list(
        self,
        *,
        lecturer_id: str | None = None,
        student_id: str | None = None,
        course_code: str | None = None,
    ) -> list[dict[str, Any]]:
        values = self.store.read()
        if lecturer_id:
            values = [value for value in values if value.get("lecturer_id") == lecturer_id.strip()]
        if student_id:
            values = [value for value in values if value.get("student_id") == student_id.strip()]
        if course_code:
            values = [
                value for value in values if value.get("course_code") == course_code.strip().upper()
            ]
        values.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return deepcopy(values)
