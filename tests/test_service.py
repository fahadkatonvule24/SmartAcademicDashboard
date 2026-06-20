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


class FailingProvider(DemoTranslationProvider):
    name = "real_provider"

    def translate(self, *, text, source_language, target_language, glossary_terms=None):
        raise RuntimeError("provider unavailable")


class RecoveryProvider(DemoTranslationProvider):
    name = "real_provider"

    def translate(self, *, text, source_language, target_language, glossary_terms=None):
        return ProviderTranslationResult(
            text=f"[real] {text}",
            glossary_terms_applied=[],
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

    def test_glossary_terms_do_not_rewrite_inside_longer_words(self) -> None:
        result = self.service.translate(
            student_id="S001",
            text="Enterprise resource planning connects ERP modules.",
            course_code="CSC101",
        )

        self.assertIn("Enterprise", result["translated_text"])
        self.assertNotIn("EntERP", result["translated_text"])
        self.assertIn("ERP", result["glossary_terms_applied"])

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

    def test_fallback_cache_does_not_mask_recovered_provider(self) -> None:
        settings = Settings(
            data_dir=Path(self.temp_dir.name) / "fallback-cache",
            provider="demo",
            default_source_language="en",
            fallback_language="en",
            default_bilingual=True,
        )
        failing_service = TranslationService(settings=settings, provider=FailingProvider())
        text = "The student reads the course notes."

        fallback = failing_service.translate(
            student_id="S001",
            text=text,
            target_language="sw",
        )
        primary_key = failing_service._build_cache_key(
            text=text,
            course_code=None,
            source_language="en",
            target_language="sw",
            glossary_terms=[],
            provider_name="real_provider",
        )

        self.assertEqual(fallback["provider"], "local_fallback")
        self.assertIsNone(failing_service.cache.get(primary_key))

        recovered_service = TranslationService(settings=settings, provider=RecoveryProvider())
        recovered = recovered_service.translate(
            student_id="S001",
            text=text,
            target_language="sw",
        )

        self.assertFalse(recovered["cache_hit"])
        self.assertEqual(recovered["provider"], "real_provider")
        self.assertEqual(recovered["translated_text"], f"[real] {text}")

    def test_legacy_fallback_cache_entry_is_ignored_for_primary_provider(self) -> None:
        settings = Settings(
            data_dir=Path(self.temp_dir.name) / "legacy-cache",
            provider="demo",
            default_source_language="en",
            fallback_language="en",
            default_bilingual=True,
        )
        service = TranslationService(settings=settings, provider=RecoveryProvider())
        text = "The student reads the course notes."
        primary_key = service._build_cache_key(
            text=text,
            course_code=None,
            source_language="en",
            target_language="sw",
            glossary_terms=[],
            provider_name="real_provider",
        )
        service.cache.set(
            primary_key,
            {
                "student_id": "S001",
                "course_code": None,
                "content_type": "notes",
                "source_language": {"code": "en", "name": "English"},
                "target_language": {
                    "code": "sw",
                    "name": "Swahili",
                    "resolution_source": "override",
                },
                "provider": "local_fallback",
                "translated_text": "[stale fallback]",
                "glossary_terms_applied": [],
                "cache_hit": False,
                "translated_at": "2026-01-01T00:00:00+00:00",
            },
        )

        result = service.translate(
            student_id="S001",
            text=text,
            target_language="sw",
        )

        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["provider"], "real_provider")
        self.assertEqual(result["translated_text"], f"[real] {text}")


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
