from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import iuiu_course_assistant.api as assistant_api
from iuiu_course_assistant.config import Settings
from iuiu_course_assistant.service import CourseAssistantService


class FakeTranslator:
    available = True

    def translate_answer(
        self,
        *,
        student_id,
        course_code,
        text,
        target_language=None,
        nationality=None,
        bilingual=True,
    ):
        return {
            "student_id": student_id,
            "course_code": course_code,
            "target_language": {"code": target_language or "sw", "resolution_source": "override"},
            "translated_text": f"[translated] {text}",
            "bilingual_text": {"source": text, "translated": f"[translated] {text}"} if bilingual else None,
        }


class CourseAssistantServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            data_dir=Path(self.temp_dir.name) / "course_assistant",
            upload_dir=Path(self.temp_dir.name) / "course_assistant" / "uploads",
            answer_provider="demo",
            chunk_size=220,
            chunk_overlap=40,
            default_top_k=3,
            translation_enabled=True,
        )
        self.service = CourseAssistantService(settings=settings, translator=FakeTranslator())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_text_resource_is_indexed_and_versioned(self) -> None:
        first = self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Week 3 ERP Notes",
            topic="ERP workflow",
            content_text=(
                "ERP integrates registration, finance, and academic workflows in one dashboard. "
                "Students can view indexed resources before attempting quizzes."
            ),
        )
        second = self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Week 3 ERP Notes",
            topic="ERP workflow",
            content_text="A replacement version keeps the same title but new notes.",
        )

        resources = self.service.list_resources(course_code="CSC101")
        self.assertEqual(len(resources), 2)
        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertGreaterEqual(self.service.health()["indexed_chunk_count"], 2)

    def test_chat_returns_grounded_answer_with_citations(self) -> None:
        self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Week 3 ERP Notes",
            topic="ERP workflow",
            content_text=(
                "Students prepare for quizzes by reviewing indexed notes in the virtual room. "
                "Tagged notes help the chatbot retrieve the right explanation quickly."
            ),
        )

        result = self.service.ask(
            course_code="CSC101",
            topic="ERP workflow",
            question="How do indexed notes help students prepare for quizzes?",
        )

        self.assertIn("indexed CSC101 materials", result["answer_text"])
        self.assertEqual(len(result["citations"]), 1)
        self.assertIn("quizzes", result["citations"][0]["snippet"].casefold())

    def test_chat_can_reuse_translation_module(self) -> None:
        self.service.add_text_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Quiz Guidance",
            topic="Quiz prep",
            content_text="Students should review indexed notes before attempting the quiz.",
        )

        result = self.service.ask(
            student_id="S001",
            course_code="CSC101",
            question="What should students do before attempting the quiz?",
            translate_response=True,
            target_language="sw",
        )

        self.assertIn("translation", result)
        self.assertTrue(result["translation"]["translated_text"].startswith("[translated]"))

    def test_docx_upload_is_extracted_and_indexed(self) -> None:
        docx_buffer = io.BytesIO()
        with zipfile.ZipFile(docx_buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                (
                    "<w:document><w:body><w:p><w:r><w:t>"
                    "The virtual room stores lecturer notes for indexed search."
                    "</w:t></w:r></w:p></w:body></w:document>"
                ),
            )

        resource = self.service.add_uploaded_resource(
            lecturer_id="L001",
            course_code="CSC101",
            title="Lecture Notes",
            topic="Virtual room",
            filename="lecture_notes.docx",
            content=docx_buffer.getvalue(),
        )

        result = self.service.ask(
            course_code="CSC101",
            topic="Virtual room",
            question="What does the virtual room store?",
        )

        self.assertEqual(resource["source_type"], "upload")
        self.assertIn("lecturer notes", result["answer_text"].casefold())


class CourseAssistantApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            data_dir=Path(self.temp_dir.name) / "course_assistant",
            upload_dir=Path(self.temp_dir.name) / "course_assistant" / "uploads",
            answer_provider="demo",
            chunk_size=220,
            chunk_overlap=40,
            default_top_k=3,
            translation_enabled=True,
        )
        self.original_service = assistant_api.service
        assistant_api.service = CourseAssistantService(settings=settings, translator=FakeTranslator())
        self.client = TestClient(assistant_api.app)

    def tearDown(self) -> None:
        assistant_api.service = self.original_service
        self.temp_dir.cleanup()

    def test_root_route_serves_frontend(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("IUIU Kampala Campus | Course Assistant", response.text)
        self.assertIn("Kampala Campus ERP System", response.text)
        self.assertIn("Course Assistant Portal", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_text_resource_endpoint_and_chat_endpoint(self) -> None:
        resource_response = self.client.post(
            "/resources/text",
            json={
                "lecturer_id": "L001",
                "course_code": "CSC101",
                "title": "Week 3 ERP Notes",
                "topic": "ERP workflow",
                "content_text": (
                    "ERP integrates registration and finance workflows. "
                    "Students review indexed notes before quizzes."
                ),
            },
        )
        self.assertEqual(resource_response.status_code, 200)

        chat_response = self.client.post(
            "/chat",
            json={
                "course_code": "CSC101",
                "topic": "ERP workflow",
                "question": "Why should students review indexed notes?",
            },
        )
        self.assertEqual(chat_response.status_code, 200)
        payload = chat_response.json()
        self.assertIn("indexed", payload["answer_text"].casefold())
