from __future__ import annotations

import re
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from iuiu_course_assistant.config import load_settings as load_course_settings
from iuiu_course_assistant.retrieval import tokenize
from iuiu_course_assistant.service import CourseAssistantService
from iuiu_nlp.config import load_settings as load_translation_settings
from iuiu_nlp.service import TranslationService

from .storage import (
    FeedbackRepository,
    LectureSessionRepository,
    QuizAttemptRepository,
    QuizRepository,
    StudyPlanRepository,
    TimetableRepository,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class SharedTranslationBridge:
    def __init__(self, translation_service: TranslationService):
        self.translation_service = translation_service
        self.available = True

    def translate_answer(
        self,
        *,
        student_id: str,
        course_code: str,
        text: str,
        target_language: str | None = None,
        nationality: str | None = None,
        bilingual: bool = True,
    ) -> dict[str, Any]:
        return self.translation_service.translate(
            student_id=student_id,
            text=text,
            course_code=course_code,
            target_language=target_language,
            nationality=nationality,
            content_type="chat",
            bilingual=bilingual,
        )


class IntegratedDashboardService:
    def __init__(
        self,
        *,
        translation_service: TranslationService | None = None,
        course_service: CourseAssistantService | None = None,
    ):
        translation_settings = load_translation_settings()
        self.translation_service = translation_service or TranslationService(settings=translation_settings)
        self.course_service = course_service or CourseAssistantService(settings=load_course_settings())
        self.course_service.translator = SharedTranslationBridge(self.translation_service)
        self.dashboard_data_dir = self._resolve_dashboard_data_dir()
        self.timetables = TimetableRepository(self.dashboard_data_dir / "timetables.json")
        self.study_plans = StudyPlanRepository(self.dashboard_data_dir / "study_plans.json")
        self.quizzes = QuizRepository(self.dashboard_data_dir / "quizzes.json")
        self.quiz_attempts = QuizAttemptRepository(self.dashboard_data_dir / "quiz_attempts.json")
        self.feedback = FeedbackRepository(self.dashboard_data_dir / "feedback.json")
        self.lecture_sessions = LectureSessionRepository(self.dashboard_data_dir / "lecture_sessions.json")
        self.mock_users = self._build_mock_users()

    def health(self) -> dict[str, Any]:
        translation_health = self.translation_service.health()
        course_health = self.course_service.health()
        return {
            "status": "ok",
            "translation_provider": translation_health["provider"],
            "chat_provider": course_health["provider"],
            "profiles": len(self.translation_service.profiles.store.read()),
            "resources": self.course_service.resources.count(),
            "indexed_chunks": self.course_service.chunks.count(),
            "languages": len(translation_health["supported_languages"]),
        }

    def supported_languages(self) -> list[dict[str, str]]:
        return self.translation_service.supported_languages()

    def authenticate_user(self, *, username: str, password: str) -> dict[str, Any]:
        if not username.strip():
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")

        user = self.mock_users.get(username.strip().casefold())
        if user is None or user["password"] != password:
            raise ValueError("Invalid username or password")

        if user["role"] == "student":
            self._ensure_student_profile(user)
            self._ensure_student_support_assets(user)
            workspace = self.student_workspace(
                student_id=user["student_id"],
                course_code=self._default_course_code(user),
            )
        else:
            workspace = self.lecturer_workspace(
                lecturer_id=user["lecturer_id"],
                course_code=self._default_course_code(user),
            )

        return {
            "message": "Login successful",
            "user": self._public_user(user),
            "workspace": workspace,
        }

    def request_password_reset(self, *, username: str) -> dict[str, str]:
        if not username.strip():
            raise ValueError("username is required")

        user = self.mock_users.get(username.strip().casefold())
        destination = self._mask_email(user.get("email")) if user else "your registered email"
        return {
            "message": "If the account exists, reset instructions have been sent.",
            "destination": destination,
        }

    def admin_overview(self) -> dict[str, Any]:
        profiles = self.translation_service.profiles.store.read()
        glossary = self.translation_service.glossary.store.read()
        cache = self.translation_service.cache.store.read()
        translation_logs = self.translation_service.logs.store.read()
        resources = self.course_service.resources.store.read()
        course_logs = self.course_service.logs.store.read()
        glossary_term_count = sum(len(terms) for terms in glossary.values())
        recent_activity = self._recent_activity(translation_logs=translation_logs, course_logs=course_logs)

        return {
            "profile_count": len(profiles),
            "glossary_course_count": len(glossary),
            "glossary_term_count": glossary_term_count,
            "translation_cache_count": len(cache),
            "translation_log_count": len(translation_logs),
            "resource_count": len(resources),
            "indexed_chunk_count": self.course_service.chunks.count(),
            "course_log_count": len(course_logs),
            "recent_activity": recent_activity,
        }

    def lecturer_workspace(
        self,
        *,
        lecturer_id: str,
        course_code: str | None = None,
    ) -> dict[str, Any]:
        user = self._lookup_user(expected_role="lecturer", lecturer_id=lecturer_id)
        courses = [dict(course) for course in (user or {}).get("courses", [])]
        self._ensure_mock_course_resources(courses=courses)
        course_codes = [course["course_code"] for course in courses]
        selected_course = self._resolve_selected_course(course_code=course_code, course_codes=course_codes)
        all_resources = [
            resource
            for resource in self.course_service.list_resources()
            if resource.get("lecturer_id") == lecturer_id.strip()
        ]
        resources = self._serialize_workspace_resources(
            self._filter_by_course(all_resources, selected_course),
            sort_mode="recent",
        )
        virtual_rooms = self._lecturer_virtual_rooms(courses, all_resources)
        lecture_sessions = self._serialize_lecture_sessions(
            sessions=self.lecture_sessions.list(
                lecturer_id=lecturer_id.strip(),
                course_code=selected_course,
            ),
            resources=self._filter_by_course(all_resources, selected_course),
            lecturer_id=lecturer_id.strip(),
            course_code=selected_course,
            audience="lecturer",
        )
        feedback_payload = self.lecturer_feedback(lecturer_id=lecturer_id, course_code=selected_course)
        quizzes = self._serialize_quizzes(
            quizzes=self.quizzes.list(course_code=selected_course, lecturer_id=lecturer_id),
            student_id=None,
        )

        workspace = {
            "role": "lecturer",
            "lecturer": self._public_user(user) if user else {"lecturer_id": lecturer_id.strip()},
            "selected_course_code": selected_course,
            "selected_course": self._course_summary(courses, selected_course),
            "selected_room": self._room_summary(virtual_rooms, selected_course),
            "courses": courses,
            "today_schedule": list((user or {}).get("today_schedule", [])),
            "announcements": list((user or {}).get("announcements", [])),
            "resources": resources,
            "lecture_sessions": lecture_sessions,
            "next_lecture_number": self._next_lecture_number(selected_course) if selected_course else 1,
            "glossary": self.translation_service.get_glossary(selected_course) if selected_course else [],
            "virtual_rooms": virtual_rooms,
            "quizzes": quizzes,
            "student_feedback": feedback_payload,
            "student_profiles": self.list_profiles()[:8],
        }
        workspace["quick_info_tiles"] = self._lecturer_quick_tiles(
            course_count=len(courses),
            class_count=len(workspace["today_schedule"]),
            resource_count=len(all_resources),
            question_count=feedback_payload["total_count"],
        )
        workspace["service_tiles"] = self._lecturer_service_tiles(
            selected_course=selected_course,
            resource_count=len(resources),
            quiz_count=len(quizzes),
            feedback_count=feedback_payload["total_count"],
            announcement_count=len(workspace["announcements"]),
        )
        return workspace

    def list_profiles(self) -> list[dict[str, Any]]:
        profiles = list(self.translation_service.profiles.store.read().values())
        profiles.sort(key=lambda item: item["student_id"])
        return profiles

    def upsert_profile(
        self,
        *,
        student_id: str,
        nationality: str,
        preferred_language: str | None = None,
    ) -> dict[str, Any]:
        return self.translation_service.upsert_profile(
            student_id=student_id,
            nationality=nationality,
            preferred_language=preferred_language,
        )

    def glossary_overview(self) -> list[dict[str, Any]]:
        glossary = self.translation_service.glossary.store.read()
        overview = []
        for course_code, terms in glossary.items():
            overview.append(
                {
                    "course_code": course_code,
                    "term_count": len(terms),
                    "terms": terms,
                }
            )
        overview.sort(key=lambda item: item["course_code"])
        return overview

    def add_glossary_terms(self, *, course_code: str, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.translation_service.add_glossary_terms(course_code=course_code, terms=terms)

    def get_glossary(self, course_code: str) -> list[dict[str, Any]]:
        return self.translation_service.get_glossary(course_code)

    def list_resources(self, course_code: str | None = None) -> list[dict[str, Any]]:
        return self.course_service.list_resources(course_code=course_code)

    def add_text_resource(self, **payload: Any) -> dict[str, Any]:
        return self.course_service.add_text_resource(**payload)

    def add_uploaded_resource(self, **payload: Any) -> dict[str, Any]:
        return self.course_service.add_uploaded_resource(**payload)

    def list_lecture_sessions(
        self,
        *,
        lecturer_id: str,
        course_code: str,
    ) -> dict[str, Any]:
        user = self._lookup_user(expected_role="lecturer", lecturer_id=lecturer_id)
        if user is None:
            raise ValueError("Lecturer not found")

        courses = [dict(course) for course in user.get("courses", [])]
        self._ensure_mock_course_resources(courses=courses)
        normalized_course = course_code.strip().upper()
        self._validate_lecturer_course_access(lecturer_id=lecturer_id, course_code=normalized_course)
        resources = self.course_service.list_resources(course_code=normalized_course)
        sessions = self.lecture_sessions.list(lecturer_id=lecturer_id.strip(), course_code=normalized_course)
        return {
            "lecturer_id": lecturer_id.strip(),
            "course_code": normalized_course,
            "next_lecture_number": self._next_lecture_number(normalized_course),
            "sessions": self._serialize_lecture_sessions(
                sessions=sessions,
                resources=resources,
                lecturer_id=lecturer_id.strip(),
                course_code=normalized_course,
                audience="lecturer",
            ),
        }

    def create_lecture_session(
        self,
        *,
        lecturer_id: str,
        course_code: str,
        lecture_number: int | None = None,
        title: str | None = None,
        topic: str | None = None,
        status: str = "Delivered",
        date_or_week: str | None = None,
        notes_text: str | None = None,
    ) -> dict[str, Any]:
        user = self._lookup_user(expected_role="lecturer", lecturer_id=lecturer_id)
        if user is None:
            raise ValueError("Lecturer not found")

        normalized_course = course_code.strip().upper()
        self._validate_lecturer_course_access(lecturer_id=lecturer_id, course_code=normalized_course)
        normalized_status = self._normalize_session_status(status)
        normalized_number = (
            int(lecture_number)
            if lecture_number is not None
            else self._next_lecture_number(normalized_course)
        )
        self._validate_unique_lecture_number(
            course_code=normalized_course,
            lecture_number=normalized_number,
            ignore_session_id=None,
        )
        created_at = utc_now_iso()
        payload = {
            "session_id": uuid4().hex[:12],
            "lecturer_id": lecturer_id.strip(),
            "course_code": normalized_course,
            "lecture_number": normalized_number,
            "title": self._default_session_title(normalized_number, topic, title),
            "topic": topic.strip() if topic else None,
            "status": normalized_status,
            "date_or_week": date_or_week.strip() if date_or_week else None,
            "notes_text": notes_text.strip() if notes_text else "",
            "created_at": created_at,
            "updated_at": created_at,
        }
        return self.lecture_sessions.upsert(payload)

    def update_lecture_session(
        self,
        *,
        session_id: str,
        lecturer_id: str,
        lecture_number: int | None = None,
        title: str | None = None,
        topic: str | None = None,
        status: str | None = None,
        date_or_week: str | None = None,
        notes_text: str | None = None,
    ) -> dict[str, Any]:
        session = self.lecture_sessions.get(session_id.strip())
        if session is None:
            raise ValueError("Lecture session not found")
        if session.get("lecturer_id") != lecturer_id.strip():
            raise ValueError("Lecture session does not belong to this lecturer")

        updated = dict(session)
        if lecture_number is not None:
            updated["lecture_number"] = int(lecture_number)
        if topic is not None:
            updated["topic"] = topic.strip() or None
        if status is not None:
            updated["status"] = self._normalize_session_status(status)
        if date_or_week is not None:
            updated["date_or_week"] = date_or_week.strip() or None
        if notes_text is not None:
            updated["notes_text"] = notes_text.strip()
        updated["title"] = self._default_session_title(
            updated["lecture_number"],
            updated.get("topic"),
            title if title is not None else updated.get("title"),
        )
        self._validate_unique_lecture_number(
            course_code=updated["course_code"],
            lecture_number=updated["lecture_number"],
            ignore_session_id=updated["session_id"],
        )
        updated["updated_at"] = utc_now_iso()
        return self.lecture_sessions.upsert(updated)

    def add_session_attachments(
        self,
        *,
        session_id: str,
        lecturer_id: str,
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        session = self.lecture_sessions.get(session_id.strip())
        if session is None:
            raise ValueError("Lecture session not found")
        if session.get("lecturer_id") != lecturer_id.strip():
            raise ValueError("Lecture session does not belong to this lecturer")
        if not files:
            raise ValueError("At least one file is required")

        attachments = []
        for file_payload in files:
            filename = str(file_payload.get("filename") or "").strip()
            content = file_payload.get("content") or b""
            content_type = file_payload.get("content_type")
            if not filename:
                raise ValueError("Each attachment must include a filename")
            title = self._attachment_title_from_filename(filename)
            attachment = self.add_uploaded_resource(
                lecturer_id=lecturer_id.strip(),
                course_code=session["course_code"],
                session_id=session["session_id"],
                title=title,
                filename=filename,
                content=content,
                topic=session.get("topic"),
                week=session.get("date_or_week"),
                semester=self._course_semester(session["course_code"]),
                academic_year=self._academic_year_from_semester(self._course_semester(session["course_code"])),
                visibility="enrolled",
                content_type=content_type,
            )
            attachments.append(attachment)

        session["updated_at"] = utc_now_iso()
        self.lecture_sessions.upsert(session)
        serialized_session = next(
            (
                item
                for item in self._serialize_lecture_sessions(
                    sessions=[session],
                    resources=self.course_service.list_resources(course_code=session["course_code"]),
                    lecturer_id=lecturer_id.strip(),
                    course_code=session["course_code"],
                    audience="lecturer",
                )
                if item["session_id"] == session["session_id"]
            ),
            None,
        )
        return {
            "session": serialized_session or {**session, "attachments": [], "attachment_count": 0},
            "attachments": attachments,
        }

    def student_workspace(self, *, student_id: str, course_code: str | None = None) -> dict[str, Any]:
        user = self._lookup_user(expected_role="student", student_id=student_id)
        if user:
            self._ensure_student_profile(user)
            self._ensure_student_support_assets(user)

        profile = self.translation_service.get_profile(student_id)
        course_cards = [dict(course) for course in (user or {}).get("courses", [])]
        self._ensure_mock_course_resources(courses=course_cards)
        course_codes = [course["course_code"] for course in course_cards]
        selected_course = self._resolve_selected_course(course_code=course_code, course_codes=course_codes)
        all_resources = [
            resource
            for resource in self.course_service.list_resources()
            if not course_codes or resource.get("course_code") in course_codes
        ]
        resources = self._serialize_workspace_resources(
            self._filter_by_course(all_resources, selected_course),
            sort_mode="lecture",
        )
        virtual_rooms = self._student_virtual_rooms(course_cards, all_resources)
        lecture_sessions = self._serialize_lecture_sessions(
            sessions=self.lecture_sessions.list(course_code=selected_course),
            resources=self._filter_by_course(all_resources, selected_course),
            lecturer_id=None,
            course_code=selected_course,
            audience="student",
        )
        quizzes = self.list_student_quizzes(student_id=student_id, course_code=selected_course)["quizzes"]
        timetable = self.timetables.get(student_id)
        study_plan = self.study_plans.get(student_id)
        feedback_history = self.feedback.list(student_id=student_id, course_code=selected_course)

        workspace = {
            "role": "student",
            "student_id": student_id,
            "registration_number": (user or {}).get("registration_number"),
            "profile": profile,
            "erp_profile": dict((user or {}).get("erp_profile", {})),
            "languages": self.translation_service.supported_languages(),
            "selected_course_code": selected_course,
            "selected_course": self._course_summary(course_cards, selected_course),
            "selected_room": self._room_summary(virtual_rooms, selected_course),
            "courses": course_cards,
            "registered_course_units": list((user or {}).get("registered_course_units", [])),
            "resources": resources,
            "lecture_sessions": lecture_sessions,
            "glossary": self.translation_service.get_glossary(selected_course) if selected_course else [],
            "registration": dict((user or {}).get("registration", {})),
            "finance": dict((user or {}).get("finance", {})),
            "clearance_history": list((user or {}).get("clearance_history", [])),
            "today_schedule": list((user or {}).get("today_schedule", [])),
            "results": list((user or {}).get("results", [])),
            "exam_result_rows": list((user or {}).get("exam_result_rows", [])),
            "announcements": list((user or {}).get("announcements", [])),
            "virtual_rooms": virtual_rooms,
            "timetable": timetable,
            "study_plan": study_plan,
            "quizzes": quizzes,
            "feedback_history": feedback_history,
            "translation_summary": {
                "request_count": len(
                    [
                        entry
                        for entry in self.translation_service.logs.store.read()
                        if entry.get("student_id") == student_id.strip()
                    ]
                ),
                "recent_target_language": self._recent_translation_language(student_id),
            },
        }
        workspace["quick_info_tiles"] = self._student_quick_tiles(workspace)
        workspace["service_tiles"] = self._student_service_tiles(workspace)
        return workspace

    def generate_student_timetable(
        self,
        *,
        student_id: str,
        available_hours_per_week: int = 12,
        preferred_times: list[str] | None = None,
    ) -> dict[str, Any]:
        user = self._lookup_user(expected_role="student", student_id=student_id)
        if user is None:
            raise ValueError("Student not found")

        courses = [dict(course) for course in user.get("courses", [])]
        if not courses:
            raise ValueError("No registered courses found for this student")

        hours = max(int(available_hours_per_week), len(courses) * 2)
        slots = preferred_times or ["18:30 - 20:30", "06:30 - 08:30", "15:00 - 17:00"]
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        session_count = min(max(len(courses) + 1, 4), len(days))
        duration = max(round(hours / session_count, 1), 1.0)

        entries = []
        for index in range(session_count):
            course = courses[index % len(courses)]
            entries.append(
                {
                    "day": days[index],
                    "time": slots[index % len(slots)],
                    "course_code": course["course_code"],
                    "title": course["title"],
                    "duration_hours": duration,
                    "focus": self._study_focus_for_course(course["course_code"]),
                }
            )

        payload = {
            "student_id": student_id.strip(),
            "available_hours_per_week": hours,
            "preferred_times": slots,
            "generated_at": utc_now_iso(),
            "entries": entries,
        }
        return self.timetables.upsert(student_id.strip(), payload)

    def generate_study_plan(
        self,
        *,
        student_id: str,
        study_hours_per_week: int = 12,
    ) -> dict[str, Any]:
        user = self._lookup_user(expected_role="student", student_id=student_id)
        if user is None:
            raise ValueError("Student not found")

        recommendations = []
        quizzes = self.quizzes.list()
        attempts = self.quiz_attempts.list(student_id=student_id)
        attempts_by_quiz: dict[str, list[dict[str, Any]]] = {}
        for attempt in attempts:
            attempts_by_quiz.setdefault(attempt["quiz_id"], []).append(attempt)

        for course in user.get("courses", []):
            course_quizzes = [quiz for quiz in quizzes if quiz.get("course_code") == course["course_code"]]
            course_attempts = []
            for quiz in course_quizzes:
                course_attempts.extend(attempts_by_quiz.get(quiz["quiz_id"], []))

            resource_count = len(self.course_service.list_resources(course_code=course["course_code"]))
            if course_attempts:
                average = sum(attempt["percentage"] for attempt in course_attempts) / len(course_attempts)
                priority = "High" if average < 65 else "Medium" if average < 80 else "Steady"
                reason = (
                    f"Average quiz score is {round(average, 1)}% across {len(course_attempts)} attempt(s)."
                )
            elif resource_count == 0:
                average = None
                priority = "High"
                reason = "No lecturer resources are indexed for this course yet."
            else:
                average = None
                priority = "Medium"
                reason = "Resources are available, but no quiz attempt has been recorded yet."

            recommended_hours = 4 if priority == "High" else 3 if priority == "Medium" else 2
            recommendations.append(
                {
                    "course_code": course["course_code"],
                    "title": course["title"],
                    "priority": priority,
                    "recommended_hours": recommended_hours,
                    "reason": reason,
                    "next_action": self._study_focus_for_course(course["course_code"]),
                    "average_quiz_score": round(average, 1) if average is not None else None,
                }
            )

        recommendations.sort(
            key=lambda item: (
                {"High": 0, "Medium": 1, "Steady": 2}.get(item["priority"], 3),
                item["course_code"],
            )
        )
        payload = {
            "student_id": student_id.strip(),
            "study_hours_per_week": max(int(study_hours_per_week), 6),
            "generated_at": utc_now_iso(),
            "recommendations": recommendations,
            "summary": (
                "Prioritise courses with lower quiz performance and revisit indexed resources "
                "before the next study session."
            ),
        }
        return self.study_plans.upsert(student_id.strip(), payload)

    def list_student_quizzes(
        self,
        *,
        student_id: str,
        course_code: str | None = None,
    ) -> dict[str, Any]:
        user = self._lookup_user(expected_role="student", student_id=student_id)
        if user is None:
            raise ValueError("Student not found")

        registered_courses = {course["course_code"] for course in user.get("courses", [])}
        quizzes = self.quizzes.list(course_code=course_code)
        quizzes = [
            quiz for quiz in quizzes if not registered_courses or quiz.get("course_code") in registered_courses
        ]
        return {
            "student_id": student_id.strip(),
            "quizzes": self._serialize_quizzes(quizzes=quizzes, student_id=student_id.strip()),
        }

    def generate_quiz(
        self,
        *,
        lecturer_id: str,
        course_code: str,
        topic: str | None = None,
        resource_id: str | None = None,
        question_count: int = 3,
    ) -> dict[str, Any]:
        if self._lookup_user(expected_role="lecturer", lecturer_id=lecturer_id) is None:
            raise ValueError("Lecturer not found")

        selected_course = course_code.strip().upper()
        resources = self.course_service.list_resources(course_code=selected_course)
        if topic:
            resources = [
                resource
                for resource in resources
                if str(resource.get("topic", "")).casefold() == topic.strip().casefold()
            ]
        if resource_id:
            resources = [
                resource for resource in resources if resource.get("resource_id") == resource_id.strip()
            ]
        if not resources:
            raise ValueError("No indexed resources available for quiz generation")

        chosen_resources = resources[: max(question_count, 1)]
        text_pool = "\n\n".join(
            self._resource_text(resource["resource_id"]) or resource.get("excerpt", "")
            for resource in chosen_resources
        ).strip()
        questions = self._build_quiz_questions(
            text=text_pool,
            resources=chosen_resources,
            question_count=max(min(question_count, 5), 2),
        )
        if not questions:
            raise ValueError("Could not generate quiz questions from the available notes")

        payload = {
            "quiz_id": uuid4().hex[:12],
            "lecturer_id": lecturer_id.strip(),
            "course_code": selected_course,
            "topic": topic.strip() if topic else (chosen_resources[0].get("topic") or "General"),
            "title": f"{selected_course} Practice Quiz",
            "generated_at": utc_now_iso(),
            "source_resource_ids": [resource["resource_id"] for resource in chosen_resources],
            "question_count": len(questions),
            "questions": questions,
        }
        return self.quizzes.upsert(payload)

    def submit_quiz_attempt(
        self,
        *,
        quiz_id: str,
        student_id: str,
        answers: list[int],
    ) -> dict[str, Any]:
        quiz = self.quizzes.get(quiz_id.strip())
        if quiz is None:
            raise ValueError("Quiz not found")
        if self._lookup_user(expected_role="student", student_id=student_id) is None:
            raise ValueError("Student not found")

        normalized_answers = [int(answer) for answer in answers]
        score = 0
        graded_questions = []
        for index, question in enumerate(quiz.get("questions", [])):
            selected = normalized_answers[index] if index < len(normalized_answers) else -1
            correct = selected == question["answer_index"]
            if correct:
                score += 1
            graded_questions.append(
                {
                    "question_id": question["question_id"],
                    "selected_index": selected,
                    "correct_index": question["answer_index"],
                    "correct": correct,
                }
            )

        total = max(len(quiz.get("questions", [])), 1)
        percentage = round((score / total) * 100, 1)
        attempt_payload = {
            "attempt_id": uuid4().hex[:12],
            "quiz_id": quiz_id.strip(),
            "student_id": student_id.strip(),
            "score": score,
            "total_questions": total,
            "percentage": percentage,
            "answers": normalized_answers,
            "graded_questions": graded_questions,
            "submitted_at": utc_now_iso(),
        }
        self.quiz_attempts.append(attempt_payload)
        self.generate_study_plan(student_id=student_id.strip())

        return {
            "quiz": {
                "quiz_id": quiz["quiz_id"],
                "title": quiz["title"],
                "course_code": quiz["course_code"],
            },
            "attempt": attempt_payload,
        }

    def submit_feedback(
        self,
        *,
        student_id: str,
        course_code: str,
        difficulty_area: str,
        comment: str,
        topic: str | None = None,
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        if self._lookup_user(expected_role="student", student_id=student_id) is None:
            raise ValueError("Student not found")
        if not difficulty_area.strip():
            raise ValueError("difficulty_area is required")
        if not comment.strip():
            raise ValueError("comment is required")

        normalized_course = course_code.strip().upper()
        resource = self.course_service.get_resource(resource_id.strip()) if resource_id else None
        lecturer_id = self._lecturer_id_for_course(normalized_course)
        if lecturer_id is None:
            raise ValueError("No lecturer mapping found for this course")

        user = self._lookup_user(expected_role="student", student_id=student_id)
        payload = {
            "feedback_id": uuid4().hex[:12],
            "student_id": student_id.strip(),
            "student_name": (user or {}).get("display_name", student_id.strip()),
            "lecturer_id": lecturer_id,
            "course_code": normalized_course,
            "resource_id": resource_id.strip() if resource_id else None,
            "resource_title": resource.get("title") if resource else None,
            "topic": topic.strip() if topic else (resource.get("topic") if resource else None),
            "difficulty_area": difficulty_area.strip(),
            "comment": comment.strip(),
            "status": "Open",
            "created_at": utc_now_iso(),
        }
        return self.feedback.append(payload)

    def lecturer_feedback(
        self,
        *,
        lecturer_id: str,
        course_code: str | None = None,
    ) -> dict[str, Any]:
        entries = self.feedback.list(lecturer_id=lecturer_id.strip(), course_code=course_code)
        by_topic: dict[str, dict[str, Any]] = {}
        for entry in entries:
            topic_key = entry.get("topic") or entry.get("difficulty_area") or "General"
            summary = by_topic.setdefault(
                topic_key,
                {
                    "topic": topic_key,
                    "count": 0,
                    "course_code": entry.get("course_code"),
                    "latest_comment": entry.get("comment"),
                },
            )
            summary["count"] += 1
            summary["latest_comment"] = entry.get("comment")

        grouped_topics = list(by_topic.values())
        grouped_topics.sort(key=lambda item: (-item["count"], item["topic"]))
        return {
            "lecturer_id": lecturer_id.strip(),
            "total_count": len(entries),
            "open_count": len([entry for entry in entries if entry.get("status") == "Open"]),
            "entries": entries,
            "by_topic": grouped_topics,
        }

    def translate_text(self, **payload: Any) -> dict[str, Any]:
        return self.translation_service.translate(**payload)

    def translate_resource(
        self,
        *,
        student_id: str,
        resource_id: str,
        target_language: str | None = None,
        nationality: str | None = None,
        bilingual: bool = True,
    ) -> dict[str, Any]:
        resource = self.course_service.get_resource(resource_id)
        if resource is None:
            raise ValueError("Resource not found")

        text = self._resource_text(resource_id)
        if not text:
            raise ValueError(
                "This file can be opened, but it cannot be translated because no readable text was indexed."
            )

        translation = self.translation_service.translate(
            student_id=student_id,
            text=text,
            course_code=resource["course_code"],
            target_language=target_language,
            nationality=nationality,
            content_type="notes",
            bilingual=bilingual,
        )
        return {
            "resource": resource,
            "translation": translation,
        }

    def build_resource_pdf(
        self,
        *,
        student_id: str,
        resource_id: str,
        translate: bool = True,
        target_language: str | None = None,
    ) -> dict[str, Any]:
        student = self._lookup_user(expected_role="student", student_id=student_id)
        if student is None:
            raise ValueError("Student not found")

        resource = self.course_service.get_resource(resource_id)
        if resource is None:
            raise ValueError("Resource not found")

        allowed_courses = {course["course_code"] for course in student.get("courses", [])}
        if allowed_courses and resource.get("course_code") not in allowed_courses:
            raise ValueError("Resource is not available for this student")

        source_text = self._resource_text(resource_id)
        if not translate and resource.get("content_type") == "application/pdf":
            stored_path = Path(str(resource.get("stored_path", "")))
            if stored_path.exists():
                return {
                    "filename": resource.get("original_filename") or stored_path.name,
                    "content": stored_path.read_bytes(),
                    "mode": "Original PDF",
                    "language": "Original",
                    "resource": resource,
                    "media_type": "application/pdf",
                }

        if not source_text:
            raise ValueError(
                "This file can be opened in its original form, but no readable text was indexed for translation."
            )

        mode_label = "Original note"
        document_text = source_text
        language_label = "English"
        if translate:
            translation = self.translation_service.translate(
                student_id=student_id,
                text=source_text,
                course_code=resource["course_code"],
                target_language=target_language,
                nationality=student.get("nationality"),
                content_type="notes",
                bilingual=False,
            )
            document_text = translation["translated_text"]
            language_label = translation["target_language"]["name"]
            mode_label = f"Translated for {language_label}"

        metadata_lines = [
            f"Course: {resource.get('course_code', '-')}",
            f"Title: {resource.get('title', 'Lecture note')}",
            f"Topic: {resource.get('topic') or 'General'}",
            f"Mode: {mode_label}",
            f"Student: {student.get('display_name', student_id)}",
        ]
        pdf_bytes = self._render_pdf_document(
            title=f"{resource.get('title', 'Lecture note')} PDF",
            metadata_lines=metadata_lines,
            body_text=document_text,
        )
        file_stem = re.sub(r"[^a-z0-9]+", "-", resource.get("title", "lecture-note").casefold()).strip("-")
        variant = "translated" if translate else "original"
        return {
            "filename": f"{resource.get('course_code', 'course').lower()}-{file_stem or 'lecture-note'}-{variant}.pdf",
            "content": pdf_bytes,
            "mode": mode_label,
            "language": language_label,
            "resource": resource,
            "media_type": "application/pdf",
        }

    def chat(self, **payload: Any) -> dict[str, Any]:
        return self.course_service.ask(**payload)

    def _resolve_dashboard_data_dir(self) -> Path:
        translation_dir = self.translation_service.settings.data_dir
        return translation_dir / "dashboard"

    def _build_mock_users(self) -> dict[str, dict[str, Any]]:
        return {
            "lecturer": {
                "username": "lecturer",
                "password": "demo123",
                "role": "lecturer",
                "lecturer_id": "L001",
                "display_name": "Dr. Amina Ssentamu",
                "title": "Lecturer, Information Systems",
                "email": "lecturer@iuiu.ac.ug",
                "school": "Faculty of Science and Technology",
                "campus": "Kampala Campus",
                "office": "ICT Block 2.14",
                "courses": [
                    {
                        "course_code": "CSC101",
                        "title": "Enterprise Systems",
                        "room": "Lab B2",
                        "day": "Monday",
                        "time": "09:00 - 11:00",
                        "enrolled": 84,
                        "semester": "Semester II 2025/2026",
                        "year_of_study": "Year 3",
                    },
                    {
                        "course_code": "BIT220",
                        "title": "Database Design",
                        "room": "ICT 4",
                        "day": "Wednesday",
                        "time": "11:00 - 13:00",
                        "enrolled": 62,
                        "semester": "Semester II 2025/2026",
                        "year_of_study": "Year 2",
                    },
                ],
                "today_schedule": [
                    {
                        "time": "09:00",
                        "course_code": "CSC101",
                        "title": "Enterprise Systems lecture",
                        "location": "Lab B2",
                    },
                    {
                        "time": "14:00",
                        "course_code": "CSC101",
                        "title": "Department consultation hour",
                        "location": "Office ICT Block 2.14",
                    },
                ],
                "announcements": [
                    "Upload week 5 notes before the Friday evening student revision window.",
                    "Finalize CAT marks for CSC101 before Monday 08:00.",
                ],
            },
            "student": {
                "username": "student",
                "password": "demo123",
                "role": "student",
                "student_id": "S001",
                "registration_number": "223-000000-00000",
                "display_name": "DEMO STUDENT",
                "email": "student@iuiu.ac.ug",
                "program": "Bachelor of Information Technology",
                "campus": "Kampala Campus",
                "nationality": "Ugandan",
                "preferred_language": "sw",
                "year_of_study": "Year 3",
                "erp_profile": {
                    "registration_number": "223-000000-00000",
                    "name": "DEMO STUDENT",
                    "gender": "MALE",
                    "nationality": "UGANDAN",
                    "birth_date": "01 January, 2000",
                    "session": "DAY",
                    "marital_status": "SINGLE",
                    "arabic_name": "",
                    "religion": "MUSLIM",
                    "entry_method": "DIRECT",
                    "entry_year": "2023",
                    "phone": "256700000000",
                    "email": "student.demo@example.com",
                    "hall": "-",
                    "home_district": "-",
                    "intake": "AUGUST",
                },
                "registered_course_units": [
                    {
                        "course_code": "BIT 3202",
                        "title": "BUSINESS INTELLIGENCE AND DATA WAREHOUSING",
                        "class": "BIT YR 3 [DAY]",
                        "hours_per_week": 4,
                        "lecturer": "MR.WAHAB ISMAEL",
                        "credit_units": "4.0",
                    },
                    {
                        "course_code": "BIT 3115",
                        "title": "DATA AND INFORMATION SECURITY",
                        "class": "BIT YR 3 [DAY]",
                        "hours_per_week": 4,
                        "lecturer": "DR. NALUKWAGO FADHILLA",
                        "credit_units": "4.0",
                    },
                    {
                        "course_code": "BIT 3104",
                        "title": "IT ETHICS AND PROFESSIONALISM",
                        "class": "BIT YR 3 [DAY],BSC.CSC YR",
                        "hours_per_week": 3,
                        "lecturer": "MS. NASSANGA",
                        "credit_units": "3.0",
                    },
                    {
                        "course_code": "IQR 1101",
                        "title": "QURAN RECITATION",
                        "class": "BIT YR 3 [DAY]",
                        "hours_per_week": 0,
                        "lecturer": "USTADH",
                        "credit_units": "0.0",
                    },
                    {
                        "course_code": "BIT 3102",
                        "title": "SYSTEMS AND NETWORK ADMINISTRATION",
                        "class": "BIT YR 3 [DAY]",
                        "hours_per_week": 4,
                        "lecturer": "MR. SSEKAMWA",
                        "credit_units": "4.0",
                    },
                    {
                        "course_code": "BIT 3209",
                        "title": "TECHNOPRENEURSHIP AND E-COMMERCE",
                        "class": "BIT YR 3 [DAY]",
                        "hours_per_week": 4,
                        "lecturer": "MS. NAMULI",
                        "credit_units": "4.0",
                    },
                ],
                "clearance_history": [
                    {
                        "academic_year": "2025/2026",
                        "year": "3",
                        "semester": "2",
                        "reg_status": "REGISTERED",
                        "retakes": "-",
                        "status": "CARD PRINTED",
                        "cleared_by": "SSUBRA",
                        "date_cleared": "16 April, 2026",
                    },
                    {
                        "academic_year": "2025/2026",
                        "year": "3",
                        "semester": "1",
                        "reg_status": "REGISTERED",
                        "retakes": "-",
                        "status": "CARD PRINTED",
                        "cleared_by": "SSUBRA",
                        "date_cleared": "21 November, 2025",
                    },
                    {
                        "academic_year": "2024/2025",
                        "year": "2",
                        "semester": "2",
                        "reg_status": "REGISTERED LATE",
                        "retakes": "-",
                        "status": "CARD PRINTED",
                        "cleared_by": "NJOWERIA",
                        "date_cleared": "17 April, 2025",
                    },
                    {
                        "academic_year": "2024/2025",
                        "year": "2",
                        "semester": "1",
                        "reg_status": "REGISTERED LATE",
                        "retakes": "-",
                        "status": "CARD PRINTED",
                        "cleared_by": "NJOWERIA",
                        "date_cleared": "28 November, 2024",
                    },
                    {
                        "academic_year": "2023/2024",
                        "year": "1",
                        "semester": "2",
                        "reg_status": "REGISTERED LATE",
                        "retakes": "-",
                        "status": "CARD PRINTED",
                        "cleared_by": "SSALI",
                        "date_cleared": "25 February, 2024",
                    },
                    {
                        "academic_year": "2023/2024",
                        "year": "1",
                        "semester": "1",
                        "reg_status": "REGISTERED",
                        "retakes": "-",
                        "status": "CARD PRINTED",
                        "cleared_by": "SSUBRA",
                        "date_cleared": "30 November, 2023",
                    },
                ],
                "exam_result_rows": [
                    {
                        "code": "AOF 1101",
                        "course": "INTRODUCTORY ARABIC",
                        "credit_units": "0.0",
                        "mark": "77",
                        "grade": "B+",
                        "grade_point": "4.5",
                        "comment": "-",
                    },
                    {
                        "code": "CSC 1203",
                        "course": "STRUCTURED PROGRAMMING",
                        "credit_units": "4.0",
                        "mark": "80",
                        "grade": "A",
                        "grade_point": "5.0",
                        "comment": "-",
                    },
                    {
                        "code": "CSC 1215",
                        "course": "COMPUTER CARE AND MAINTENANCE",
                        "credit_units": "4.0",
                        "mark": "87",
                        "grade": "A",
                        "grade_point": "5.0",
                        "comment": "-",
                    },
                    {
                        "code": "CSN 1201",
                        "course": "INTRODUCTION TO COMPUTER NETWORKS (CCNA 1)",
                        "credit_units": "4.0",
                        "mark": "88",
                        "grade": "A",
                        "grade_point": "5.0",
                        "comment": "-",
                    },
                    {
                        "code": "FOS 1108",
                        "course": "ISLAM AND SCIENCE",
                        "credit_units": "3.0",
                        "mark": "76",
                        "grade": "B+",
                        "grade_point": "4.5",
                        "comment": "-",
                    },
                    {
                        "code": "ITM 1202",
                        "course": "STATISTICS FOR INFORMATION TECHNOLOGY",
                        "credit_units": "4.0",
                        "mark": "71",
                        "grade": "B",
                        "grade_point": "4.0",
                        "comment": "-",
                    },
                    {
                        "code": "MCS 1201",
                        "course": "PRINCIPLES OF MANAGEMENT",
                        "credit_units": "3.0",
                        "mark": "51",
                        "grade": "D",
                        "grade_point": "2.0",
                        "comment": "-",
                    },
                ],
                "courses": [
                    {
                        "course_code": "CSC101",
                        "title": "Enterprise Systems",
                        "lecturer": "Dr. Amina Ssentamu",
                        "attendance": "92%",
                        "semester": "Semester II 2025/2026",
                        "year_of_study": "Year 3",
                    },
                    {
                        "course_code": "BIT220",
                        "title": "Database Design",
                        "lecturer": "Dr. Amina Ssentamu",
                        "attendance": "88%",
                        "semester": "Semester II 2025/2026",
                        "year_of_study": "Year 3",
                    },
                    {
                        "course_code": "BIS210",
                        "title": "Systems Analysis",
                        "lecturer": "Mr. Haruna Idi",
                        "attendance": "94%",
                        "semester": "Semester II 2025/2026",
                        "year_of_study": "Year 3",
                    },
                ],
                "registration": {
                    "semester": "Semester II 2025/2026",
                    "status": "Registered",
                    "clearance": "Finance pending",
                },
                "finance": {
                    "tuition_balance": "UGX 420,000",
                    "library_status": "Clear",
                    "hostel_status": "Optional",
                },
                "today_schedule": [
                    {
                        "time": "09:00",
                        "course_code": "CSC101",
                        "title": "Enterprise Systems",
                        "location": "Lab B2",
                    },
                    {
                        "time": "13:30",
                        "course_code": "BIS210",
                        "title": "Systems Analysis tutorial",
                        "location": "Tutorial Room 5",
                    },
                ],
                "results": [
                    {"course_code": "CSC101", "assessment": "CAT 1", "score": "28 / 30"},
                    {"course_code": "BIT220", "assessment": "Assignment", "score": "17 / 20"},
                    {"course_code": "BIS210", "assessment": "Quiz", "score": "9 / 10"},
                ],
                "announcements": [
                    "Course registration remains open until Friday 17:00.",
                    "ERP notes for CSC101 are available for translation in your workspace.",
                ],
            },
        }

    def _public_user(self, user: dict[str, Any] | None) -> dict[str, Any]:
        if user is None:
            return {}
        public_user = {key: value for key, value in user.items() if key != "password"}
        public_user["course_codes"] = [
            course["course_code"] for course in public_user.get("courses", [])
        ]
        public_user["default_course_code"] = self._default_course_code(public_user)
        return public_user

    def _default_course_code(self, user: dict[str, Any]) -> str | None:
        courses = user.get("courses", [])
        if not courses:
            return None
        return courses[0]["course_code"]

    def _lookup_user(
        self,
        *,
        expected_role: str,
        lecturer_id: str | None = None,
        student_id: str | None = None,
    ) -> dict[str, Any] | None:
        for user in self.mock_users.values():
            if user.get("role") != expected_role:
                continue
            if lecturer_id and user.get("lecturer_id") == lecturer_id.strip():
                return user
            if student_id and user.get("student_id") == student_id.strip():
                return user
        return None

    def _ensure_student_profile(self, user: dict[str, Any]) -> None:
        student_id = user["student_id"]
        if self.translation_service.get_profile(student_id) is not None:
            return
        self.translation_service.upsert_profile(
            student_id=student_id,
            nationality=user["nationality"],
            preferred_language=user.get("preferred_language"),
        )

    def _ensure_student_support_assets(self, user: dict[str, Any]) -> None:
        student_id = user["student_id"]
        if self.timetables.get(student_id) is None:
            self.generate_student_timetable(student_id=student_id)
        if self.study_plans.get(student_id) is None:
            self.generate_study_plan(student_id=student_id)

    def _ensure_mock_course_resources(self, *, courses: list[dict[str, Any]]) -> None:
        if not courses:
            return

        all_resources = self.course_service.list_resources()
        existing_titles_by_course: dict[str, set[str]] = {}
        resources_by_session: dict[str, list[dict[str, Any]]] = {}
        for resource in all_resources:
            course_code = str(resource.get("course_code", "")).strip().upper()
            if course_code:
                existing_titles_by_course.setdefault(course_code, set()).add(
                    str(resource.get("title", "")).strip().casefold()
                )
            session_id = str(resource.get("session_id") or "").strip()
            if session_id:
                resources_by_session.setdefault(session_id, []).append(resource)

        existing_sessions = self.lecture_sessions.list()
        sessions_by_course: dict[str, list[dict[str, Any]]] = {}
        for session in existing_sessions:
            sessions_by_course.setdefault(session["course_code"], []).append(session)

        for course in courses:
            course_code = str(course.get("course_code", "")).strip().upper()
            if not course_code:
                continue

            course_title = str(course.get("title") or course_code)
            lecturer_id = self._course_lecturer_id(course_code) or f"MOCK-{course_code}"
            known_titles = existing_titles_by_course.setdefault(course_code, set())
            known_sessions = sessions_by_course.setdefault(course_code, [])
            for template in self._mock_course_resource_templates(
                course_code=course_code,
                course_title=course_title,
                semester=course.get("semester"),
                year_of_study=course.get("year_of_study"),
            ):
                lecture_number = self._extract_template_lecture_number(template["title"])
                session = next(
                    (
                        existing
                        for existing in known_sessions
                        if existing.get("lecture_number") == lecture_number
                    ),
                    None,
                )
                if session is None:
                    session = {
                        "session_id": uuid4().hex[:12],
                        "lecturer_id": lecturer_id,
                        "course_code": course_code,
                        "lecture_number": lecture_number,
                        "title": template["title"],
                        "topic": template["topic"],
                        "status": "Delivered",
                        "date_or_week": template["week"],
                        "notes_text": template["content_text"],
                        "created_at": utc_now_iso(),
                        "updated_at": utc_now_iso(),
                    }
                    self.lecture_sessions.upsert(session)
                    known_sessions.append(session)

                if resources_by_session.get(session["session_id"]):
                    continue

                resource = self.add_text_resource(
                    lecturer_id=lecturer_id,
                    course_code=course_code,
                    session_id=session["session_id"],
                    title=template["title"],
                    topic=template["topic"],
                    week=template["week"],
                    semester=course.get("semester"),
                    academic_year=self._academic_year_from_semester(course.get("semester")),
                    visibility="enrolled",
                    content_text=template["content_text"],
                )
                resources_by_session.setdefault(session["session_id"], []).append(resource)
                known_titles.add(template["title"].casefold())

    def _validate_lecturer_course_access(self, *, lecturer_id: str, course_code: str) -> None:
        user = self._lookup_user(expected_role="lecturer", lecturer_id=lecturer_id)
        if user is None:
            raise ValueError("Lecturer not found")
        normalized_course = course_code.strip().upper()
        if not any(course.get("course_code") == normalized_course for course in user.get("courses", [])):
            raise ValueError("This room is not assigned to the lecturer")

    def _normalize_session_status(self, status: str | None) -> str:
        normalized = str(status or "Delivered").strip().casefold()
        mapping = {
            "delivered": "Delivered",
            "missed": "Missed",
            "make-up": "Make-up",
            "makeup": "Make-up",
        }
        if normalized not in mapping:
            raise ValueError("status must be Delivered, Missed, or Make-up")
        return mapping[normalized]

    def _next_lecture_number(self, course_code: str | None) -> int:
        if not course_code:
            return 1
        normalized_course = course_code.strip().upper()
        existing_numbers = [
            int(session.get("lecture_number"))
            for session in self.lecture_sessions.list(course_code=normalized_course)
            if session.get("lecture_number")
        ]
        if not existing_numbers:
            existing_numbers = [
                number
                for number in (
                    self._lecture_number(resource)
                    for resource in self.course_service.list_resources(course_code=normalized_course)
                )
                if number is not None
            ]
        return (max(existing_numbers) + 1) if existing_numbers else 1

    def _validate_unique_lecture_number(
        self,
        *,
        course_code: str,
        lecture_number: int,
        ignore_session_id: str | None,
    ) -> None:
        for session in self.lecture_sessions.list(course_code=course_code):
            if ignore_session_id and session["session_id"] == ignore_session_id:
                continue
            if int(session.get("lecture_number") or 0) == int(lecture_number):
                raise ValueError("A lecture session with that lecture number already exists for this course")

    def _default_session_title(
        self,
        lecture_number: int,
        topic: str | None,
        override_title: str | None,
    ) -> str:
        if override_title and override_title.strip():
            return override_title.strip()
        if topic and topic.strip():
            return f"Lecture {lecture_number} - {topic.strip()}"
        return f"Lecture {lecture_number}"

    def _extract_template_lecture_number(self, title: str) -> int:
        match = re.search(r"lecture\s+(\d+)", title, flags=re.IGNORECASE)
        return int(match.group(1)) if match else 1

    def _course_semester(self, course_code: str) -> str | None:
        normalized = course_code.strip().upper()
        for user in self.mock_users.values():
            for course in user.get("courses", []):
                if course.get("course_code") == normalized:
                    return course.get("semester")
        return None

    def _attachment_title_from_filename(self, filename: str) -> str:
        stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
        return stem.title() if stem else "Lecture Attachment"

    def _resolve_selected_course(
        self,
        *,
        course_code: str | None,
        course_codes: list[str],
    ) -> str | None:
        if course_code and course_code.strip():
            return course_code.strip().upper()
        return course_codes[0] if course_codes else None

    def _resource_text(self, resource_id: str) -> str:
        chunks = [
            chunk
            for chunk in self.course_service.chunks.store.read()
            if chunk.get("resource_id") == resource_id
        ]
        chunks.sort(key=lambda item: item.get("position", 0))
        return "\n\n".join(chunk.get("text", "") for chunk in chunks).strip()

    def _recent_activity(
        self,
        *,
        translation_logs: list[dict[str, Any]],
        course_logs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        combined = [
            {**entry, "source": "translation"} for entry in translation_logs
        ] + [{**entry, "source": "course"} for entry in course_logs]
        combined.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return combined[:10]

    def _mask_email(self, email: str | None) -> str:
        if not email or "@" not in email:
            return "your registered email"
        local, domain = email.split("@", maxsplit=1)
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = f"{local[:2]}{'*' * (len(local) - 2)}"
        return f"{masked_local}@{domain}"

    def _recent_translation_language(self, student_id: str) -> str | None:
        logs = [
            entry
            for entry in self.translation_service.logs.store.read()
            if entry.get("student_id") == student_id.strip()
        ]
        logs.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return logs[0].get("target_language") if logs else None

    def _filter_by_course(
        self,
        resources: list[dict[str, Any]],
        course_code: str | None,
    ) -> list[dict[str, Any]]:
        if not course_code:
            return list(resources)
        return [
            resource for resource in resources if resource.get("course_code") == course_code.strip().upper()
        ]

    def _serialize_workspace_resources(
        self,
        resources: list[dict[str, Any]],
        *,
        sort_mode: str = "recent",
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for resource in resources:
            lecture_number = self._lecture_number(resource)
            item = dict(resource)
            item["lecture_number"] = lecture_number
            item["material_label"] = f"Lecture {lecture_number}" if lecture_number else item.get("title")
            item["pdf_available"] = True
            item["translation_available"] = bool(item.get("indexed"))
            item["original_pdf_available"] = item.get("content_type") == "application/pdf"
            serialized.append(item)
        if sort_mode == "lecture":
            serialized.sort(
                key=lambda item: (
                    item.get("lecture_number") if item.get("lecture_number") is not None else 999,
                    str(item.get("title", "")).casefold(),
                    str(item.get("created_at", "")),
                )
            )
        else:
            serialized.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return serialized

    def _serialize_lecture_sessions(
        self,
        *,
        sessions: list[dict[str, Any]],
        resources: list[dict[str, Any]],
        lecturer_id: str | None,
        course_code: str | None,
        audience: str,
    ) -> list[dict[str, Any]]:
        filtered_resources = [
            resource
            for resource in resources
            if (not lecturer_id or resource.get("lecturer_id") == lecturer_id)
            and (not course_code or resource.get("course_code") == course_code)
        ]
        serialized_resources = self._serialize_workspace_resources(filtered_resources, sort_mode="recent")
        resources_by_session: dict[str, list[dict[str, Any]]] = {}
        legacy_resources: list[dict[str, Any]] = []
        for resource in serialized_resources:
            session_id = str(resource.get("session_id") or "").strip()
            if session_id:
                resources_by_session.setdefault(session_id, []).append(resource)
            else:
                legacy_resources.append(resource)

        serialized_sessions: list[dict[str, Any]] = []
        for session in sessions:
            attachments = resources_by_session.pop(session["session_id"], [])
            serialized_sessions.append(
                {
                    **session,
                    "attachments": attachments,
                    "attachment_count": len(attachments),
                    "indexed_attachment_count": len(
                        [attachment for attachment in attachments if attachment.get("indexed")]
                    ),
                    "latest_attachment_title": attachments[0]["title"] if attachments else None,
                    "has_notes": bool(str(session.get("notes_text") or "").strip()),
                    "audience": audience,
                }
            )

        for resource in legacy_resources:
            serialized_sessions.append(
                {
                    "session_id": f"legacy-{resource['resource_id']}",
                    "lecturer_id": resource.get("lecturer_id"),
                    "course_code": resource.get("course_code"),
                    "lecture_number": resource.get("lecture_number"),
                    "title": resource.get("material_label") or resource.get("title"),
                    "topic": resource.get("topic"),
                    "status": "Delivered",
                    "date_or_week": resource.get("week"),
                    "notes_text": "",
                    "created_at": resource.get("created_at"),
                    "updated_at": resource.get("created_at"),
                    "attachments": [resource],
                    "attachment_count": 1,
                    "indexed_attachment_count": 1 if resource.get("indexed") else 0,
                    "latest_attachment_title": resource.get("title"),
                    "has_notes": False,
                    "audience": audience,
                }
            )

        for session_id, attachments in resources_by_session.items():
            first_attachment = attachments[0]
            serialized_sessions.append(
                {
                    "session_id": session_id,
                    "lecturer_id": first_attachment.get("lecturer_id"),
                    "course_code": first_attachment.get("course_code"),
                    "lecture_number": first_attachment.get("lecture_number"),
                    "title": first_attachment.get("material_label") or first_attachment.get("title"),
                    "topic": first_attachment.get("topic"),
                    "status": "Delivered",
                    "date_or_week": first_attachment.get("week"),
                    "notes_text": "",
                    "created_at": first_attachment.get("created_at"),
                    "updated_at": first_attachment.get("created_at"),
                    "attachments": attachments,
                    "attachment_count": len(attachments),
                    "indexed_attachment_count": len(
                        [attachment for attachment in attachments if attachment.get("indexed")]
                    ),
                    "latest_attachment_title": attachments[0]["title"],
                    "has_notes": False,
                    "audience": audience,
                }
            )

        serialized_sessions.sort(
            key=lambda item: (
                item.get("lecture_number") if item.get("lecture_number") is not None else 999,
                str(item.get("title", "")).casefold(),
                str(item.get("created_at", "")),
            )
        )
        return serialized_sessions

    def _student_virtual_rooms(
        self,
        courses: list[dict[str, Any]],
        resources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rooms = []
        for course in courses:
            course_resources = [
                resource for resource in resources if resource.get("course_code") == course["course_code"]
            ]
            rooms.append(
                {
                    "room_id": f"{course['course_code'].casefold()}-room",
                    "course_code": course["course_code"],
                    "title": course["title"],
                    "lecturer": course.get("lecturer"),
                    "year_of_study": course.get("year_of_study"),
                    "semester": course.get("semester"),
                    "resource_count": len(course_resources),
                    "latest_resource": course_resources[0]["title"] if course_resources else None,
                }
            )
        return rooms

    def _course_summary(
        self,
        courses: list[dict[str, Any]],
        course_code: str | None,
    ) -> dict[str, Any] | None:
        if not course_code:
            return None
        return next(
            (dict(course) for course in courses if course.get("course_code") == course_code),
            None,
        )

    def _room_summary(
        self,
        rooms: list[dict[str, Any]],
        course_code: str | None,
    ) -> dict[str, Any] | None:
        if not course_code:
            return None
        return next(
            (dict(room) for room in rooms if room.get("course_code") == course_code),
            None,
        )

    def _course_lecturer_id(self, course_code: str) -> str | None:
        expected = course_code.strip().upper()
        for user in self.mock_users.values():
            if user.get("role") != "lecturer":
                continue
            for course in user.get("courses", []):
                if course.get("course_code") == expected:
                    return user.get("lecturer_id")
        return None

    def _mock_course_resource_templates(
        self,
        *,
        course_code: str,
        course_title: str,
        semester: str | None,
        year_of_study: str | None,
    ) -> list[dict[str, str]]:
        course_templates = {
            "CSC101": [
                (
                    "Lecture 1",
                    "ERP foundations",
                    (
                        f"{course_code} {course_title} lecture one introduces enterprise resource planning. "
                        "It explains how registration, finance, and teaching workflows stay connected in one system. "
                        "Students should identify the major modules and the data each module shares."
                    ),
                ),
                (
                    "Lecture 2",
                    "Workflow integration",
                    (
                        f"{course_code} {course_title} lecture two focuses on workflow mapping. "
                        "The note compares student registration, lecturer uploads, assessment records, and announcements. "
                        "Learners should follow each workflow from data entry to reporting."
                    ),
                ),
                (
                    "Lecture 3",
                    "Reports and decision support",
                    (
                        f"{course_code} {course_title} lecture three covers dashboards, reports, and service support. "
                        "It shows how indexed lecture notes improve quiz preparation and course guidance. "
                        "Students should summarize how academic support data is presented to end users."
                    ),
                ),
            ],
            "BIT220": [
                (
                    "Lecture 1",
                    "Database modelling",
                    (
                        f"{course_code} {course_title} lecture one introduces entities, attributes, and relationships. "
                        "It uses university records such as students, courses, fees, and results as examples. "
                        "Students should practice separating transactional data from reference data."
                    ),
                ),
                (
                    "Lecture 2",
                    "Normalization",
                    (
                        f"{course_code} {course_title} lecture two explains first, second, and third normal form. "
                        "The examples use registration tables and lecturer resource indexes. "
                        "Learners should identify duplicated fields and redesign them into cleaner structures."
                    ),
                ),
                (
                    "Lecture 3",
                    "Query design",
                    (
                        f"{course_code} {course_title} lecture three demonstrates queries for results, announcements, and timetable views. "
                        "It also links database design to search and retrieval support in course systems. "
                        "Students should write sample queries that answer common academic questions."
                    ),
                ),
            ],
            "BIS210": [
                (
                    "Lecture 1",
                    "Systems overview",
                    (
                        f"{course_code} {course_title} lecture one introduces systems analysis in an academic portal setting. "
                        "It reviews actors, goals, inputs, and outputs for students, lecturers, and administrators. "
                        "Students should identify the core business processes supported by the portal."
                    ),
                ),
                (
                    "Lecture 2",
                    "Requirements and use cases",
                    (
                        f"{course_code} {course_title} lecture two captures requirements through interviews, observations, and use cases. "
                        "The lecture note models login, resource access, translation support, and lecturer feedback. "
                        "Learners should turn user goals into clear functional requirements."
                    ),
                ),
                (
                    "Lecture 3",
                    "Process modelling",
                    (
                        f"{course_code} {course_title} lecture three focuses on process flows, exceptions, and user journeys. "
                        "It explains how a student opens a course unit, reads lecture PDFs, and asks for course support. "
                        "Students should diagram the flow from course selection to resource review."
                    ),
                ),
            ],
        }
        selected_templates = course_templates.get(course_code) or [
            (
                "Lecture 1",
                "Course introduction",
                (
                    f"{course_code} {course_title} lecture one introduces the course scope, lecturer expectations, "
                    "and the main learning outcomes for the semester."
                ),
            ),
            (
                "Lecture 2",
                "Core concepts",
                (
                    f"{course_code} {course_title} lecture two summarizes the core concepts and examples that "
                    "students should review before tutorials and quizzes."
                ),
            ),
            (
                "Lecture 3",
                "Applied practice",
                (
                    f"{course_code} {course_title} lecture three connects theory to applied exercises, "
                    "revision prompts, and follow-up discussion points."
                ),
            ),
        ]
        prefix = " ".join(part for part in [year_of_study, semester] if part)
        templates: list[dict[str, str]] = []
        for index, (title, topic, body) in enumerate(selected_templates, start=1):
            content_text = body if not prefix else f"{prefix}. {body}"
            templates.append(
                {
                    "title": title,
                    "topic": topic,
                    "week": f"Week {index}",
                    "content_text": content_text,
                }
            )
        return templates

    def _academic_year_from_semester(self, semester: str | None) -> str | None:
        if not semester:
            return None
        match = re.search(r"(\d{4}/\d{4})", semester)
        return match.group(1) if match else None

    def _lecture_number(self, resource: dict[str, Any]) -> int | None:
        title_match = re.search(r"lecture\s+(\d+)", str(resource.get("title", "")), flags=re.IGNORECASE)
        if title_match:
            return int(title_match.group(1))
        week_match = re.search(r"(\d+)", str(resource.get("week", "")))
        if week_match:
            return int(week_match.group(1))
        return None

    def _render_pdf_document(
        self,
        *,
        title: str,
        metadata_lines: list[str],
        body_text: str,
    ) -> bytes:
        header_lines = [title, *metadata_lines, ""]
        wrapped_lines: list[str] = []
        for line in header_lines + self._wrap_pdf_lines(body_text):
            wrapped_lines.append(self._sanitize_pdf_text(line))
        pages = [
            wrapped_lines[index : index + 44]
            for index in range(0, max(len(wrapped_lines), 1), 44)
        ] or [["No content available."]]

        objects: list[bytes] = []
        page_object_numbers: list[int] = []
        for page_index, page_lines in enumerate(pages):
            page_number = 3 + page_index * 2
            content_number = page_number + 1
            page_object_numbers.append(page_number)
            stream_lines = [
                "BT",
                "/F1 12 Tf",
                "50 760 Td",
                "15 TL",
            ]
            for line in page_lines:
                stream_lines.append(f"({self._pdf_escape(line)}) Tj")
                stream_lines.append("T*")
            stream_lines.append("ET")
            stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
            objects.append(
                (
                    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> "
                    f"/Contents {content_number} 0 R >>"
                ).encode("ascii")
            )
            objects.append(
                f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
                + stream
                + b"\nendstream"
            )

        kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
        document_objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Count {len(page_object_numbers)} /Kids [{kids}] >>".encode("ascii"),
            *objects,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]

        pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        offsets = [0]
        for index, payload in enumerate(document_objects, start=1):
            offsets.append(len(pdf))
            pdf += f"{index} 0 obj\n".encode("ascii") + payload + b"\nendobj\n"
        xref_position = len(pdf)
        pdf += f"xref\n0 {len(document_objects) + 1}\n".encode("ascii")
        pdf += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            pdf += f"{offset:010d} 00000 n \n".encode("ascii")
        pdf += (
            f"trailer\n<< /Size {len(document_objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF"
        ).encode("ascii")
        return pdf

    def _wrap_pdf_lines(self, text: str) -> list[str]:
        lines: list[str] = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                lines.append("")
                continue
            lines.extend(
                textwrap.wrap(
                    stripped,
                    width=92,
                    break_long_words=False,
                    replace_whitespace=False,
                )
            )
        return lines or ["No content available."]

    def _sanitize_pdf_text(self, value: str) -> str:
        return value.encode("latin-1", errors="replace").decode("latin-1")

    def _pdf_escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _lecturer_virtual_rooms(
        self,
        courses: list[dict[str, Any]],
        resources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rooms = []
        for course in courses:
            course_resources = [
                resource for resource in resources if resource.get("course_code") == course["course_code"]
            ]
            rooms.append(
                {
                    "room_id": f"{course['course_code'].casefold()}-room",
                    "course_code": course["course_code"],
                    "title": course["title"],
                    "year_of_study": course.get("year_of_study"),
                    "semester": course.get("semester"),
                    "resource_count": len(course_resources),
                    "room": course.get("room"),
                    "enrolled": course.get("enrolled"),
                    "latest_resource": course_resources[0]["title"] if course_resources else None,
                }
            )
        return rooms

    def _student_quick_tiles(self, workspace: dict[str, Any]) -> list[dict[str, str]]:
        results = workspace.get("results", [])
        timetable = workspace.get("timetable") or {}
        return [
            {
                "module": "profile",
                "label": "My Profile",
                "subtitle": workspace.get("profile", {}).get("student_id", "Student account"),
                "value": (workspace.get("profile") or {}).get("preferred_language") or "Auto",
                "icon_text": "PR",
            },
            {
                "module": "results",
                "label": "My Results",
                "subtitle": f"{len(results)} assessment records",
                "value": results[0]["score"] if results else "No scores",
                "icon_text": "RS",
            },
            {
                "module": "fees_info",
                "label": "Fees Info",
                "subtitle": workspace.get("registration", {}).get("clearance", "Clearance"),
                "value": workspace.get("finance", {}).get("tuition_balance", "UGX 0"),
                "icon_text": "FI",
            },
            {
                "module": "my_timetable",
                "label": "My Timetable",
                "subtitle": f"{len(timetable.get('entries', []))} study sessions",
                "value": "Ready" if timetable.get("entries") else "Generate",
                "icon_text": "TT",
            },
        ]

    def _student_service_tiles(self, workspace: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {
                "module": "e_learning_centre",
                "label": "Virtual Lecturer Rooms",
                "subtitle": f"{len(workspace.get('virtual_rooms', []))} lecturer room(s)",
                "description": "Course rooms, notes, and guided study resources.",
                "icon_text": "EL",
            },
            {
                "module": "study_planner",
                "label": "Study Planner",
                "subtitle": f"{len((workspace.get('study_plan') or {}).get('recommendations', []))} recommendation(s)",
                "description": "Adaptive weekly focus suggestions.",
                "icon_text": "SP",
            },
            {
                "module": "quiz_centre",
                "label": "Quiz Centre",
                "subtitle": f"{len(workspace.get('quizzes', []))} available quiz set(s)",
                "description": "Practice quizzes prepared from lecturer notes.",
                "icon_text": "QZ",
            },
            {
                "module": "my_registration",
                "label": "My Registration",
                "subtitle": workspace.get("registration", {}).get("status", "Pending"),
                "description": "Semester registration and clearance details.",
                "icon_text": "RG",
            },
            {
                "module": "announcements",
                "label": "Announcements",
                "subtitle": f"{len(workspace.get('announcements', []))} update(s)",
                "description": "General course and portal notices.",
                "icon_text": "AN",
            },
            {
                "module": "library",
                "label": "E-Resources / Library",
                "subtitle": f"{len(workspace.get('resources', []))} indexed material(s)",
                "description": "Lecturer uploads, references, and revision notes.",
                "icon_text": "LB",
            },
            {
                "module": "feedback_to_lecturer",
                "label": "Feedback to Lecturer",
                "subtitle": f"{len(workspace.get('feedback_history', []))} submitted note(s)",
                "description": "Structured questions on difficult topics.",
                "icon_text": "FB",
            },
        ]

    def _lecturer_quick_tiles(
        self,
        *,
        course_count: int,
        class_count: int,
        resource_count: int,
        question_count: int,
    ) -> list[dict[str, str]]:
        return [
            {
                "module": "my_courses",
                "label": "My Courses",
                "subtitle": "Allocated course units",
                "value": f"{course_count} active",
                "icon_text": "CR",
            },
            {
                "module": "todays_classes",
                "label": "Today's Classes",
                "subtitle": "Teaching schedule",
                "value": f"{class_count} session(s)",
                "icon_text": "CL",
            },
            {
                "module": "uploaded_resources",
                "label": "Uploaded Resources",
                "subtitle": "Indexed learning materials",
                "value": f"{resource_count} file(s)",
                "icon_text": "UP",
            },
            {
                "module": "student_questions",
                "label": "Student Questions",
                "subtitle": "Open structured notes",
                "value": f"{question_count} item(s)",
                "icon_text": "SQ",
            },
        ]

    def _lecturer_service_tiles(
        self,
        *,
        selected_course: str | None,
        resource_count: int,
        quiz_count: int,
        feedback_count: int,
        announcement_count: int,
    ) -> list[dict[str, str]]:
        course_label = selected_course or "Current course"
        return [
            {
                "module": "virtual_lecturer_rooms",
                "label": "Virtual Lecturer Rooms",
                "subtitle": course_label,
                "description": "Rooms grouped by year, semester, and course unit.",
                "icon_text": "VR",
            },
            {
                "module": "upload_resources",
                "label": "Upload Resources",
                "subtitle": f"{resource_count} indexed item(s)",
                "description": "Publish lecture notes, slides, and handouts.",
                "icon_text": "UR",
            },
            {
                "module": "quiz_generator",
                "label": "Quiz Generator",
                "subtitle": f"{quiz_count} quiz set(s)",
                "description": "Build practice questions from uploaded notes.",
                "icon_text": "QG",
            },
            {
                "module": "quiz_review",
                "label": "Quiz Review",
                "subtitle": f"{quiz_count} quiz set(s)",
                "description": "Review prepared quizzes and student attempts.",
                "icon_text": "QR",
            },
            {
                "module": "announcements",
                "label": "Announcements",
                "subtitle": f"{announcement_count} notice(s)",
                "description": "Current course and lecturer announcements.",
                "icon_text": "AN",
            },
            {
                "module": "student_feedback",
                "label": "Student Feedback",
                "subtitle": f"{feedback_count} submitted note(s)",
                "description": "Aggregate difficult topics by course and resource.",
                "icon_text": "SF",
            },
        ]

    def _lecturer_id_for_course(self, course_code: str) -> str | None:
        normalized = course_code.strip().upper()
        for user in self.mock_users.values():
            if user.get("role") != "lecturer":
                continue
            if any(course.get("course_code") == normalized for course in user.get("courses", [])):
                return user.get("lecturer_id")
        resources = self.course_service.list_resources(course_code=normalized)
        return resources[0].get("lecturer_id") if resources else None

    def _study_focus_for_course(self, course_code: str) -> str:
        resources = self.course_service.list_resources(course_code=course_code)
        if resources and resources[0].get("topic"):
            return f"Review {resources[0]['topic']} and its supporting lecturer notes."
        return f"Revise the latest concepts in {course_code} and prepare one practice question."

    def _serialize_quizzes(
        self,
        *,
        quizzes: list[dict[str, Any]],
        student_id: str | None,
    ) -> list[dict[str, Any]]:
        attempts = self.quiz_attempts.list(student_id=student_id) if student_id else self.quiz_attempts.list()
        attempts_by_quiz: dict[str, list[dict[str, Any]]] = {}
        for attempt in attempts:
            attempts_by_quiz.setdefault(attempt["quiz_id"], []).append(attempt)

        serialized = []
        for quiz in quizzes:
            quiz_attempts = attempts_by_quiz.get(quiz["quiz_id"], [])
            quiz_attempts.sort(key=lambda item: item.get("submitted_at", ""), reverse=True)
            latest_by_student: dict[str, dict[str, Any]] = {}
            for attempt in quiz_attempts:
                latest_by_student.setdefault(attempt["student_id"], attempt)
            participant_results = []
            for attempt in latest_by_student.values():
                passed = attempt["percentage"] >= 50.0
                participant_results.append(
                    {
                        "student_id": attempt["student_id"],
                        "student_name": self._student_name(attempt["student_id"]),
                        "percentage": attempt["percentage"],
                        "score": attempt["score"],
                        "total_questions": attempt["total_questions"],
                        "submitted_at": attempt["submitted_at"],
                        "status": "Passed" if passed else "Failed",
                        "passed": passed,
                    }
                )
            participant_results.sort(
                key=lambda item: (not item["passed"], -float(item["percentage"]), item["student_name"])
            )
            serialized.append(
                {
                    **quiz,
                    "attempt_count": len(quiz_attempts),
                    "latest_attempt": quiz_attempts[0] if quiz_attempts else None,
                    "best_score": (
                        max(attempt["percentage"] for attempt in quiz_attempts) if quiz_attempts else None
                    ),
                    "participant_count": len(participant_results),
                    "pass_mark": 50.0,
                    "pass_count": len([result for result in participant_results if result["passed"]]),
                    "fail_count": len([result for result in participant_results if not result["passed"]]),
                    "average_score": (
                        round(
                            sum(result["percentage"] for result in participant_results)
                            / len(participant_results),
                            1,
                        )
                        if participant_results
                        else None
                    ),
                    "participant_results": participant_results,
                }
            )
        return serialized

    def _student_name(self, student_id: str) -> str:
        user = self._lookup_user(expected_role="student", student_id=student_id)
        return (user or {}).get("display_name", student_id)

    def _build_quiz_questions(
        self,
        *,
        text: str,
        resources: list[dict[str, Any]],
        question_count: int,
    ) -> list[dict[str, Any]]:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
            if sentence.strip()
        ]
        if not sentences:
            return []

        course_token_pool = [
            token for token in sorted(tokenize(text)) if len(token) >= 4
        ]
        fallback_terms = ["workflow", "dashboard", "planner", "resources", "revision", "concept"]
        questions = []

        for index, sentence in enumerate(sentences[: question_count * 2]):
            answer = self._answer_token(sentence)
            if answer is None:
                continue
            prompt = re.sub(
                re.escape(answer),
                "_____",
                sentence,
                count=1,
                flags=re.IGNORECASE,
            )
            distractors = [
                token.title()
                for token in course_token_pool
                if token.casefold() != answer.casefold()
            ]
            for term in fallback_terms:
                if term.casefold() != answer.casefold():
                    distractors.append(term.title())
            options = []
            for term in distractors:
                if term not in options:
                    options.append(term)
                if len(options) == 3:
                    break
            insert_index = index % 4
            answer_display = answer.title()
            options.insert(insert_index, answer_display)
            options = options[:4]
            if answer_display not in options:
                options[-1] = answer_display
            resource = resources[index % len(resources)]
            questions.append(
                {
                    "question_id": f"q{len(questions) + 1}",
                    "prompt": f"Complete the missing key term from the lecturer note: {prompt}",
                    "options": options,
                    "answer_index": options.index(answer_display),
                    "resource_id": resource["resource_id"],
                    "resource_title": resource["title"],
                    "topic": resource.get("topic"),
                    "source_excerpt": sentence,
                }
            )
            if len(questions) == question_count:
                break

        return questions

    def _answer_token(self, sentence: str) -> str | None:
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]+", sentence)
        candidates = [
            word for word in words if len(word) >= 4 and word.casefold() in tokenize(sentence)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda value: (-len(value), words.index(value)))
        return candidates[0]
