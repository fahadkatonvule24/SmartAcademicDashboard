from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from iuiu_nlp.api import app
from iuiu_nlp.config import Settings
from iuiu_nlp.providers import DemoTranslationProvider, ProviderTranslationResult
from iuiu_nlp.service import TranslationService
from nlp_translation_service.main import app as compatibility_app


class AlternateProvider(DemoTranslationProvider):
    name = "alternate_demo"

    def translate(self, *, text, source_language, target_language, glossary_terms=None):
        result = super().translate(
            text=text,
            source_language=source_language,
            target_language=target_language,
            glossary_terms=glossary_terms,
        )
        return ProviderTranslationResult(
            text=f"{result.text} [alternate]",
            glossary_terms_applied=result.glossary_terms_applied,
        )


class TranslationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            data_dir=Path(self.temp_dir.name),
            provider="demo",
            default_source_language="en",
            fallback_language="en",
            default_bilingual=True,
        )
        self.service = TranslationService(settings=settings, provider=DemoTranslationProvider())
        self.service.upsert_profile(student_id="S001", nationality="Kenya")
        self.service.add_glossary_terms(
            course_code="CSC101",
            terms=[
                {"source": "ERP", "targets": {"sw": "ERP", "fr": "ERP"}},
                {"source": "quiz", "targets": {"sw": "jaribio", "fr": "quiz"}},
            ],
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_uses_nationality_mapping_when_no_override_exists(self) -> None:
        result = self.service.translate(
            student_id="S001",
            text="The student opens the quiz dashboard.",
            course_code="CSC101",
        )
        self.assertEqual(result["target_language"]["code"], "sw")
        self.assertEqual(result["target_language"]["resolution_source"], "nationality")
        self.assertIn("jaribio", result["translated_text"])

    def test_profile_language_beats_nationality(self) -> None:
        self.service.upsert_profile(
            student_id="S002",
            nationality="Kenya",
            preferred_language="French",
        )
        result = self.service.translate(
            student_id="S002",
            text="The student opens the dashboard.",
            course_code="CSC101",
        )
        self.assertEqual(result["target_language"]["code"], "fr")
        self.assertEqual(result["target_language"]["resolution_source"], "profile")
        self.assertIn("tableau", result["translated_text"])

    def test_manual_override_beats_profile_and_nationality(self) -> None:
        self.service.upsert_profile(
            student_id="S003",
            nationality="Kenya",
            preferred_language="French",
        )
        result = self.service.translate(
            student_id="S003",
            text="This course note needs translation.",
            course_code="CSC101",
            target_language="so",
        )
        self.assertEqual(result["target_language"]["code"], "so")
        self.assertEqual(result["target_language"]["resolution_source"], "override")
        self.assertIn("koorso", result["translated_text"])

    def test_glossary_terms_are_preserved_during_translation(self) -> None:
        result = self.service.translate(
            student_id="S001",
            text="The ERP quiz covers the dashboard workflow.",
            course_code="CSC101",
        )
        self.assertIn("ERP", result["translated_text"])
        self.assertIn("jaribio", result["translated_text"])
        self.assertIn("ERP", result["glossary_terms_applied"])
        self.assertIn("quiz", result["glossary_terms_applied"])

    def test_cached_translations_are_reused(self) -> None:
        first = self.service.translate(
            student_id="S001",
            text="The student reads the course notes.",
            course_code="CSC101",
        )
        second = self.service.translate(
            student_id="S001",
            text="The student reads the course notes.",
            course_code="CSC101",
        )
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["translated_text"], second["translated_text"])

    def test_cache_is_separated_by_provider(self) -> None:
        first = self.service.translate(
            student_id="S001",
            text="The student reads the course notes.",
            course_code="CSC101",
        )
        second_service = TranslationService(
            settings=self.service.settings,
            provider=AlternateProvider(),
        )
        second = second_service.translate(
            student_id="S001",
            text="The student reads the course notes.",
            course_code="CSC101",
        )
        self.assertFalse(first["cache_hit"])
        self.assertFalse(second["cache_hit"])
        self.assertEqual(second["provider"], "alternate_demo")
        self.assertIn("[alternate]", second["translated_text"])


class UiTests(unittest.TestCase):
    def test_root_route_serves_frontend(self) -> None:
        client = TestClient(app)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("IUIU Kampala Campus | NLP Translation", response.text)
        self.assertIn("Kampala Campus ERP System", response.text)
        self.assertIn("NLP Translation Portal", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_compatibility_import_path_serves_same_app(self) -> None:
        client = TestClient(compatibility_app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
