from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import iuiu_dashboard.api as dashboard_api
from iuiu_course_assistant.config import Settings as CourseSettings
from iuiu_course_assistant.service import CourseAssistantService
from iuiu_dashboard.service import IntegratedDashboardService
from iuiu_nlp.config import Settings as TranslationSettings
from iuiu_nlp.providers import DemoTranslationProvider
from iuiu_nlp.service import TranslationService


def build_dashboard_service(temp_root: Path) -> IntegratedDashboardService:
    translation_service = TranslationService(
        settings=TranslationSettings(
            data_dir=temp_root / "translation",
            provider="demo",
            default_source_language="en",
            fallback_language="en",
            default_bilingual=True,
        ),
        provider=DemoTranslationProvider(),
    )
    course_service = CourseAssistantService(
        settings=CourseSettings(
            data_dir=temp_root / "course_assistant",
            upload_dir=temp_root / "course_assistant" / "uploads",
            answer_provider="demo",
            chunk_size=220,
            chunk_overlap=40,
            default_top_k=3,
            translation_enabled=False,
        )
    )
    return IntegratedDashboardService(
        translation_service=translation_service,
        course_service=course_service,
    )


def build_mock_pdf(
    service: IntegratedDashboardService,
    *,
    title: str,
    body_text: str,
) -> bytes:
    return service._render_pdf_document(
        title=title,
        metadata_lines=["Generated test lecture PDF"],
        body_text=body_text,
    )


class DashboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = build_dashboard_service(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_admin_overview_aggregates_system_counts(self) -> None:
        self.service.upsert_profile(
            student_id="S001",
            nationality="Kenya",
            preferred_language=None,
        )
        self.service.add_glossary_terms(
            course_code="CSC101",
            terms=[{"source": "quiz", "targets": {"sw": "jaribio"}}],
        )
        self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Week 3 ERP Notes",
            topic="ERP workflow",
            content_text="Students review indexed notes before quizzes in the ERP workflow.",
        )

        overview = self.service.admin_overview()
        self.assertEqual(overview["profile_count"], 1)
        self.assertEqual(overview["glossary_term_count"], 1)
        self.assertEqual(overview["resource_count"], 1)
        self.assertGreaterEqual(overview["indexed_chunk_count"], 1)

    def test_authenticate_user_returns_role_specific_workspace(self) -> None:
        lecturer_login = self.service.authenticate_user(username="lecturer", password="demo123")
        student_login = self.service.authenticate_user(username="student", password="demo123")
        registration_login = self.service.authenticate_user(username="223-000000-00000", password="demo123")

        self.assertEqual(lecturer_login["user"]["role"], "lecturer")
        self.assertEqual(lecturer_login["workspace"]["role"], "lecturer")
        self.assertEqual(lecturer_login["workspace"]["selected_course_code"], "CSC101")
        self.assertTrue(lecturer_login["workspace"]["quick_info_tiles"])
        self.assertTrue(lecturer_login["workspace"]["service_tiles"])
        self.assertGreaterEqual(lecturer_login["workspace"]["virtual_rooms"][0]["enrolled"], 1)
        self.assertTrue(lecturer_login["workspace"]["virtual_rooms"][0]["room"])

        self.assertEqual(student_login["user"]["role"], "student")
        self.assertEqual(student_login["workspace"]["role"], "student")
        self.assertEqual(student_login["workspace"]["profile"]["student_id"], "S001")
        self.assertEqual(student_login["workspace"]["registration"]["status"], "Registered")
        self.assertTrue(student_login["workspace"]["quick_info_tiles"])
        self.assertTrue(student_login["workspace"]["service_tiles"])
        self.assertGreaterEqual(len(student_login["workspace"]["resources"]), 3)
        self.assertEqual(registration_login["workspace"]["profile"]["student_id"], "S001")

    def test_student_workspace_seeds_clickable_course_resources(self) -> None:
        workspace = self.service.student_workspace(student_id="S001", course_code="BIS210")

        self.assertEqual(workspace["selected_course"]["course_code"], "BIS210")
        self.assertEqual(workspace["selected_room"]["course_code"], "BIS210")
        self.assertEqual([resource["title"] for resource in workspace["resources"][:3]], ["Lecture 1", "Lecture 2", "Lecture 3"])
        self.assertTrue(all(resource["pdf_available"] for resource in workspace["resources"][:3]))
        self.assertEqual(workspace["lecture_sessions"][0]["title"], "Lecture 1")

    def test_student_can_update_preferred_language(self) -> None:
        profile = self.service.update_student_preferred_language(
            student_id="S001",
            preferred_language="French",
        )
        workspace = self.service.student_workspace(student_id="S001", course_code="CSC101")

        self.assertEqual(profile["preferred_language"], "fr")
        self.assertEqual(workspace["profile"]["preferred_language"], "fr")

    def test_missed_lecture_session_can_be_created_without_files(self) -> None:
        lecturer_workspace = self.service.lecturer_workspace(lecturer_id="L001", course_code="CSC101")
        session = self.service.create_lecture_session(
            lecturer_id="L001",
            course_code="CSC101",
            status="Missed",
            notes_text="The lecture was missed because of a faculty meeting. Review the notes before the make-up class.",
        )
        student_workspace = self.service.student_workspace(student_id="S001", course_code="CSC101")
        student_session = next(
            item for item in student_workspace["lecture_sessions"] if item["session_id"] == session["session_id"]
        )

        self.assertEqual(session["lecture_number"], lecturer_workspace["next_lecture_number"])
        self.assertEqual(student_session["status"], "Missed")
        self.assertEqual(student_session["attachment_count"], 0)
        self.assertIn("faculty meeting", student_session["notes_text"])

    def test_lecture_session_groups_multiple_pdf_attachments(self) -> None:
        self.service.lecturer_workspace(lecturer_id="L001", course_code="CSC101")
        session = self.service.create_lecture_session(
            lecturer_id="L001",
            course_code="CSC101",
            topic="Workflow clinic",
            notes_text="Attach the lecture deck and the supplementary reading to one session.",
        )
        readable_pdf = build_mock_pdf(
            self.service,
            title="Workflow Clinic",
            body_text="ERP workflows connect registration, finance, classes, and quiz preparation.",
        )
        unreadable_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

        attachment_payload = self.service.add_session_attachments(
            session_id=session["session_id"],
            lecturer_id="L001",
            files=[
                {
                    "filename": "workflow-clinic.pdf",
                    "content": readable_pdf,
                    "content_type": "application/pdf",
                },
                {
                    "filename": "workflow-scan.pdf",
                    "content": unreadable_pdf,
                    "content_type": "application/pdf",
                },
            ],
        )
        student_workspace = self.service.student_workspace(student_id="S001", course_code="CSC101")
        student_session = next(
            item for item in student_workspace["lecture_sessions"] if item["session_id"] == session["session_id"]
        )

        self.assertEqual(attachment_payload["session"]["attachment_count"], 2)
        self.assertEqual(
            sum(1 for attachment in attachment_payload["session"]["attachments"] if attachment["indexed"]),
            1,
        )
        self.assertEqual(
            sum(1 for attachment in attachment_payload["session"]["attachments"] if not attachment["indexed"]),
            1,
        )
        self.assertEqual(student_session["attachment_count"], 2)
        self.assertEqual(len(student_session["attachments"]), 2)

    def test_student_support_modules_generate_timetable_and_study_plan(self) -> None:
        timetable = self.service.generate_student_timetable(
            student_id="S001",
            available_hours_per_week=14,
            preferred_times=["19:00 - 21:00", "06:00 - 08:00"],
        )
        study_plan = self.service.generate_study_plan(student_id="S001", study_hours_per_week=14)

        self.assertEqual(timetable["student_id"], "S001")
        self.assertGreaterEqual(len(timetable["entries"]), 4)
        self.assertEqual(study_plan["student_id"], "S001")
        self.assertEqual(study_plan["study_hours_per_week"], 14)
        self.assertEqual(
            sum(recommendation["recommended_hours"] for recommendation in study_plan["recommendations"]),
            14,
        )
        self.assertGreaterEqual(len(study_plan["recommendations"]), 1)

    def test_study_plan_rebalances_course_hours_when_weekly_hours_change(self) -> None:
        fourteen_hour_plan = self.service.generate_study_plan(student_id="S001", study_hours_per_week=14)
        seven_hour_plan = self.service.generate_study_plan(student_id="S001", study_hours_per_week=7)

        fourteen_hour_allocations = [
            recommendation["recommended_hours"]
            for recommendation in fourteen_hour_plan["recommendations"]
        ]
        seven_hour_allocations = [
            recommendation["recommended_hours"]
            for recommendation in seven_hour_plan["recommendations"]
        ]

        self.assertEqual(sum(fourteen_hour_allocations), 14)
        self.assertEqual(sum(seven_hour_allocations), 7)
        self.assertNotEqual(fourteen_hour_allocations, seven_hour_allocations)

    def test_quiz_generation_attempt_and_feedback_are_linked(self) -> None:
        self.service.upsert_profile(student_id="S001", nationality="Kenya")
        resource = self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Week 3 ERP Notes",
            topic="ERP workflow",
            content_text=(
                "ERP integrates registration and finance workflows. "
                "Students review indexed notes before quizzes."
            ),
        )

        quiz = self.service.generate_quiz(
            lecturer_id="L001",
            course_code="CSC101",
            resource_id=resource["resource_id"],
            question_count=3,
        )
        attempt = self.service.submit_quiz_attempt(
            quiz_id=quiz["quiz_id"],
            student_id="S001",
            answers=[question["answer_index"] for question in quiz["questions"]],
        )
        feedback = self.service.submit_feedback(
            student_id="S001",
            course_code="CSC101",
            resource_id=resource["resource_id"],
            difficulty_area="ERP workflow",
            comment="Please explain the workflow mapping again.",
        )
        lecturer_feedback = self.service.lecturer_feedback(lecturer_id="L001", course_code="CSC101")
        lecturer_workspace = self.service.lecturer_workspace(lecturer_id="L001", course_code="CSC101")
        quiz_summary = lecturer_workspace["quizzes"][0]

        self.assertEqual(attempt["attempt"]["percentage"], 100.0)
        self.assertEqual(feedback["course_code"], "CSC101")
        self.assertEqual(lecturer_feedback["total_count"], 1)
        self.assertEqual(quiz_summary["pass_count"], 1)
        self.assertEqual(quiz_summary["fail_count"], 0)
        self.assertEqual(quiz_summary["participant_count"], 1)

    def test_student_can_translate_indexed_resource_and_chat(self) -> None:
        self.service.upsert_profile(student_id="S001", nationality="Kenya")
        resource = self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Week 3 ERP Notes",
            topic="ERP workflow",
            content_text=(
                "Students review indexed notes before quizzes. "
                "Tagged notes improve chatbot retrieval accuracy."
            ),
        )

        translation = self.service.translate_resource(
            student_id="S001",
            resource_id=resource["resource_id"],
        )
        chat = self.service.chat(
            student_id="S001",
            course_code="CSC101",
            topic="ERP workflow",
            question="Why should students review indexed notes before quizzes?",
            translate_response=True,
        )

        self.assertEqual(translation["resource"]["resource_id"], resource["resource_id"])
        self.assertEqual(translation["translation"]["target_language"]["code"], "sw")
        self.assertIn("translation", chat)
        self.assertEqual(chat["translation"]["target_language"]["code"], "sw")


class DashboardApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_service = dashboard_api.service
        dashboard_api.service = build_dashboard_service(Path(self.temp_dir.name))
        self.client = TestClient(dashboard_api.app)

    def tearDown(self) -> None:
        dashboard_api.service = self.original_service
        self.temp_dir.cleanup()

    def test_root_route_serves_integrated_frontend(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("IUIU Kampala Campus", response.text)
        self.assertIn("Kampala Campus Academic ERP System", response.text)
        self.assertIn("IUIU ERP Login", response.text)
        self.assertIn("Forgotten Password?", response.text)
        self.assertNotIn("E-Learning Centre", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_login_endpoint_returns_lecturer_workspace(self) -> None:
        response = self.client.post(
            "/auth/login",
            json={"username": "lecturer", "password": "demo123"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["role"], "lecturer")
        self.assertEqual(payload["workspace"]["role"], "lecturer")
        self.assertEqual(payload["workspace"]["lecturer"]["lecturer_id"], "L001")
        self.assertTrue(payload["workspace"]["quick_info_tiles"])

    def test_forgot_password_endpoint_returns_generic_reset_message(self) -> None:
        response = self.client.post(
            "/auth/forgot-password",
            json={"username": "student"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("reset instructions", payload["message"])
        self.assertIn("@", payload["destination"])

    def test_admin_and_student_endpoints_work_together(self) -> None:
        profile_response = self.client.post(
            "/admin/profiles",
            json={"student_id": "S001", "nationality": "Kenya"},
        )
        self.assertEqual(profile_response.status_code, 200)

        resource_response = self.client.post(
            "/admin/resources/text",
            json={
                "lecturer_id": "L001",
                "course_code": "CSC101",
                "title": "Week 3 ERP Notes",
                "topic": "ERP workflow",
                "content_text": "Students review indexed notes before quizzes.",
            },
        )
        self.assertEqual(resource_response.status_code, 200)
        resource_id = resource_response.json()["resource_id"]

        translation_response = self.client.post(
            "/student/resources/translate",
            json={"student_id": "S001", "resource_id": resource_id},
        )
        self.assertEqual(translation_response.status_code, 200)
        self.assertEqual(
            translation_response.json()["translation"]["target_language"]["code"],
            "sw",
        )

        lecturer_workspace = self.client.get("/lecturer/L001", params={"course_code": "CSC101"})
        self.assertEqual(lecturer_workspace.status_code, 200)
        self.assertIn(
            resource_id,
            [resource["resource_id"] for resource in lecturer_workspace.json()["resources"]],
        )

    def test_student_can_update_preferred_language_endpoint(self) -> None:
        response = self.client.post(
            "/student/profile/language",
            json={"student_id": "S001", "preferred_language": "French"},
        )
        workspace_response = self.client.get("/student/S001", params={"course_code": "CSC101"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preferred_language"], "fr")
        self.assertEqual(workspace_response.status_code, 200)
        self.assertEqual(workspace_response.json()["profile"]["preferred_language"], "fr")

    def test_proposal_specific_endpoints_work_together(self) -> None:
        resource_response = self.client.post(
            "/admin/resources/text",
            json={
                "lecturer_id": "L001",
                "course_code": "CSC101",
                "title": "Quiz Notes",
                "topic": "ERP workflow",
                "content_text": "Students review indexed notes before quizzes.",
            },
        )
        resource_id = resource_response.json()["resource_id"]

        timetable_response = self.client.post(
            "/student/timetables/generate",
            json={
                "student_id": "S001",
                "available_hours_per_week": 16,
                "preferred_times": ["19:00 - 21:00"],
            },
        )
        self.assertEqual(timetable_response.status_code, 200)

        quiz_response = self.client.post(
            "/lecturer/quizzes/generate",
            json={
                "lecturer_id": "L001",
                "course_code": "CSC101",
                "resource_id": resource_id,
                "question_count": 3,
            },
        )
        self.assertEqual(quiz_response.status_code, 200)
        quiz_id = quiz_response.json()["quiz_id"]

        quizzes_response = self.client.get("/student/S001/quizzes", params={"course_code": "CSC101"})
        self.assertEqual(quizzes_response.status_code, 200)
        self.assertEqual(quizzes_response.json()["quizzes"][0]["quiz_id"], quiz_id)

        attempt_response = self.client.post(
            f"/student/quizzes/{quiz_id}/attempt",
            json={"student_id": "S001", "answers": [0, 0, 0]},
        )
        self.assertEqual(attempt_response.status_code, 200)

        lecturer_workspace = self.client.get("/lecturer/L001", params={"course_code": "CSC101"})
        self.assertEqual(lecturer_workspace.status_code, 200)
        self.assertIn("pass_count", lecturer_workspace.json()["quizzes"][0])

        feedback_response = self.client.post(
            "/student/feedback",
            json={
                "student_id": "S001",
                "course_code": "CSC101",
                "resource_id": resource_id,
                "difficulty_area": "ERP workflow",
                "comment": "Please explain the process flow again.",
            },
        )
        self.assertEqual(feedback_response.status_code, 200)

        lecturer_feedback = self.client.get("/lecturer/L001/feedback", params={"course_code": "CSC101"})
        self.assertEqual(lecturer_feedback.status_code, 200)
        self.assertEqual(lecturer_feedback.json()["total_count"], 1)

    def test_student_pdf_endpoint_returns_translated_and_original_documents(self) -> None:
        workspace_response = self.client.get("/student/S001", params={"course_code": "CSC101"})
        self.assertEqual(workspace_response.status_code, 200)
        resource_id = workspace_response.json()["resources"][0]["resource_id"]

        translated_response = self.client.get(
            f"/student/resources/{resource_id}/pdf",
            params={"student_id": "S001", "translate": "true"},
        )
        original_response = self.client.get(
            f"/student/resources/{resource_id}/pdf",
            params={"student_id": "S001", "translate": "false"},
        )

        self.assertEqual(translated_response.status_code, 200)
        self.assertEqual(original_response.status_code, 200)
        self.assertEqual(translated_response.headers["content-type"], "application/pdf")
        self.assertEqual(original_response.headers["content-type"], "application/pdf")
        self.assertTrue(translated_response.content.startswith(b"%PDF"))
        self.assertTrue(original_response.content.startswith(b"%PDF"))
        self.assertNotEqual(translated_response.content, original_response.content)

    def test_lecture_session_endpoints_group_multiple_uploaded_pdfs(self) -> None:
        workspace_response = self.client.get("/lecturer/L001", params={"course_code": "CSC101"})
        self.assertEqual(workspace_response.status_code, 200)
        next_number = workspace_response.json()["next_lecture_number"]

        create_response = self.client.post(
            "/lecturer/L001/rooms/CSC101/sessions",
            json={
                "lecturer_id": "L001",
                "course_code": "CSC101",
                "topic": "Workflow clinic",
                "status": "Delivered",
                "notes_text": "Lecture notes and worked examples for students.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        session_id = create_response.json()["session_id"]
        self.assertEqual(create_response.json()["lecture_number"], next_number)

        readable_pdf = build_mock_pdf(
            dashboard_api.service,
            title="Workflow Clinic",
            body_text="Students review indexed lecture material before quizzes and discussions.",
        )
        unreadable_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        attachments_response = self.client.post(
            f"/lecturer/sessions/{session_id}/attachments",
            data={"lecturer_id": "L001"},
            files=[
                ("files", ("workflow-clinic.pdf", readable_pdf, "application/pdf")),
                ("files", ("workflow-scan.pdf", unreadable_pdf, "application/pdf")),
            ],
        )
        self.assertEqual(attachments_response.status_code, 200)
        attachment_payload = attachments_response.json()

        self.assertEqual(attachment_payload["session"]["attachment_count"], 2)
        self.assertEqual(len(attachment_payload["session"]["attachments"]), 2)

        student_workspace = self.client.get("/student/S001", params={"course_code": "CSC101"})
        self.assertEqual(student_workspace.status_code, 200)
        grouped_session = next(
            item for item in student_workspace.json()["lecture_sessions"] if item["session_id"] == session_id
        )

        self.assertEqual(grouped_session["attachment_count"], 2)
        self.assertEqual(len(grouped_session["attachments"]), 2)
