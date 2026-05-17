from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .config import Settings
from .languages import (
    DEFAULT_NATIONALITY_LANGUAGE,
    LANGUAGES,
    canonicalize_language,
    language_name,
    resolve_target_language,
)
from .providers import DemoTranslationProvider, TranslationProvider, build_provider
from .storage import (
    AuditLogRepository,
    GlossaryRepository,
    NationalityMapRepository,
    ProfileRepository,
    TranslationCacheRepository,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class TranslationService:
    def __init__(self, settings: Settings, provider: TranslationProvider | None = None):
        self.settings = settings
        self.provider = provider or build_provider(settings.provider)
        data_dir = settings.data_dir
        self.profiles = ProfileRepository(data_dir / "profiles.json")
        self.glossary = GlossaryRepository(data_dir / "glossary.json")
        self.cache = TranslationCacheRepository(data_dir / "translation_cache.json")
        self.logs = AuditLogRepository(data_dir / "translation_logs.json")
        self.nationality_map = NationalityMapRepository(
            data_dir / "nationality_language_map.json",
            DEFAULT_NATIONALITY_LANGUAGE,
        )

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "provider": self.provider.name,
            "supported_languages": self.supported_languages(),
        }

    def supported_languages(self) -> list[dict[str, str]]:
        return [{"code": code, "name": name} for code, name in sorted(LANGUAGES.items())]

    def get_profile(self, student_id: str) -> dict[str, Any] | None:
        return self.profiles.get(student_id.strip())

    def upsert_profile(
        self,
        *,
        student_id: str,
        nationality: str,
        preferred_language: str | None = None,
    ) -> dict[str, Any]:
        if not student_id.strip():
            raise ValueError("student_id is required")
        if not nationality.strip():
            raise ValueError("nationality is required")

        preferred = canonicalize_language(preferred_language)
        if preferred_language and preferred is None:
            raise ValueError(f"Unsupported preferred language: {preferred_language}")

        payload = {
            "student_id": student_id.strip(),
            "nationality": nationality.strip(),
            "preferred_language": preferred,
            "updated_at": utc_now_iso(),
        }
        self.logs.append(
            {
                "event": "profile_upserted",
                "student_id": student_id.strip(),
                "preferred_language": preferred,
                "timestamp": utc_now_iso(),
            }
        )
        return self.profiles.upsert(student_id.strip(), payload)

    def add_glossary_terms(
        self,
        *,
        course_code: str,
        terms: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not course_code.strip():
            raise ValueError("course_code is required")
        if not terms:
            raise ValueError("At least one glossary term is required")

        normalized_terms = []
        for term in terms:
            source = str(term.get("source", "")).strip()
            if not source:
                raise ValueError("Each glossary term must include a source value")

            cleaned_targets: dict[str, str] = {}
            for language_code, value in dict(term.get("targets", {})).items():
                canonical_language = canonicalize_language(language_code)
                if canonical_language is None:
                    raise ValueError(f"Unsupported glossary language: {language_code}")
                cleaned_targets[canonical_language] = str(value).strip()

            normalized_terms.append(
                {
                    "source": source,
                    "targets": cleaned_targets,
                    "notes": str(term.get("notes", "")).strip() or None,
                }
            )

        saved_terms = self.glossary.upsert_terms(course_code.strip(), normalized_terms)
        self.logs.append(
            {
                "event": "glossary_updated",
                "course_code": course_code.strip().upper(),
                "term_count": len(normalized_terms),
                "timestamp": utc_now_iso(),
            }
        )
        return saved_terms

    def get_glossary(self, course_code: str) -> list[dict[str, Any]]:
        return self.glossary.get_terms(course_code)

    def translate(
        self,
        *,
        student_id: str,
        text: str,
        course_code: str | None = None,
        source_language: str | None = None,
        target_language: str | None = None,
        nationality: str | None = None,
        content_type: str = "notes",
        bilingual: bool | None = None,
    ) -> dict[str, Any]:
        if not student_id.strip():
            raise ValueError("student_id is required")
        if not text.strip():
            raise ValueError("text is required")

        source = canonicalize_language(source_language or self.settings.default_source_language)
        if source is None:
            raise ValueError(f"Unsupported source language: {source_language}")

        if target_language and canonicalize_language(target_language) is None:
            raise ValueError(f"Unsupported target language: {target_language}")

        profile = self.profiles.get(student_id.strip())
        if profile is None and nationality:
            profile = self.upsert_profile(
                student_id=student_id.strip(),
                nationality=nationality,
                preferred_language=None,
            )

        effective_nationality = nationality or (profile or {}).get("nationality")
        preferred_language = (profile or {}).get("preferred_language")
        language_decision = resolve_target_language(
            override=target_language,
            preferred_language=preferred_language,
            nationality=effective_nationality,
            nationality_map=self.nationality_map.get_all(),
            fallback=self.settings.fallback_language,
        )

        glossary_terms = self.glossary.get_terms(course_code)
        cache_key = self._build_cache_key(
            text=text,
            course_code=course_code,
            source_language=source,
            target_language=language_decision.code,
            glossary_terms=glossary_terms,
            provider_name="identity" if language_decision.code == source else self.provider.name,
        )
        cached = self.cache.get(cache_key)
        if cached:
            cached_result = dict(cached)
            cached_result["cache_hit"] = True
            self._log_translation(
                student_id=student_id.strip(),
                course_code=course_code,
                content_type=content_type,
                source_language=source,
                target_language=language_decision.code,
                cache_hit=True,
                provider_name="cache",
                glossary_terms_applied=cached_result.get("glossary_terms_applied", []),
                resolution_source=language_decision.reason,
            )
            return cached_result

        if language_decision.code == source:
            translated_text = text
            glossary_terms_applied: list[str] = []
            provider_name = "identity"
        else:
            try:
                provider_result = self.provider.translate(
                    text=text,
                    source_language=source,
                    target_language=language_decision.code,
                    glossary_terms=glossary_terms,
                )
                translated_text = provider_result.text
                glossary_terms_applied = provider_result.glossary_terms_applied
                provider_name = self.provider.name
            except Exception:
                fallback_provider = DemoTranslationProvider()
                provider_result = fallback_provider.translate(
                    text=text,
                    source_language=source,
                    target_language=language_decision.code,
                    glossary_terms=glossary_terms,
                )
                translated_text = provider_result.text
                glossary_terms_applied = provider_result.glossary_terms_applied
                provider_name = "local_fallback"

        bilingual_enabled = self.settings.default_bilingual if bilingual is None else bilingual
        result = {
            "student_id": student_id.strip(),
            "course_code": course_code.upper() if course_code else None,
            "content_type": content_type,
            "source_language": {
                "code": source,
                "name": language_name(source),
            },
            "target_language": {
                "code": language_decision.code,
                "name": language_name(language_decision.code),
                "resolution_source": language_decision.reason,
            },
            "provider": provider_name,
            "translated_text": translated_text,
            "glossary_terms_applied": glossary_terms_applied,
            "cache_hit": False,
            "translated_at": utc_now_iso(),
        }
        if bilingual_enabled:
            result["bilingual_text"] = {
                "source": text,
                "translated": translated_text,
            }

        self.cache.set(cache_key, result)
        self._log_translation(
            student_id=student_id.strip(),
            course_code=course_code,
            content_type=content_type,
            source_language=source,
            target_language=language_decision.code,
            cache_hit=False,
            provider_name=provider_name,
            glossary_terms_applied=glossary_terms_applied,
            resolution_source=language_decision.reason,
        )
        return result

    def _build_cache_key(
        self,
        *,
        text: str,
        course_code: str | None,
        source_language: str,
        target_language: str,
        glossary_terms: list[dict[str, Any]],
        provider_name: str,
    ) -> str:
        digest_input = {
            "course_code": course_code.upper() if course_code else None,
            "glossary_terms": glossary_terms,
            "provider_name": provider_name,
            "source_language": source_language,
            "target_language": target_language,
            "text": text,
        }
        serialized = json.dumps(digest_input, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _log_translation(
        self,
        *,
        student_id: str,
        course_code: str | None,
        content_type: str,
        source_language: str,
        target_language: str,
        cache_hit: bool,
        provider_name: str,
        glossary_terms_applied: list[str],
        resolution_source: str,
    ) -> None:
        self.logs.append(
            {
                "event": "translation_requested",
                "student_id": student_id,
                "course_code": course_code.upper() if course_code else None,
                "content_type": content_type,
                "source_language": source_language,
                "target_language": target_language,
                "cache_hit": cache_hit,
                "provider": provider_name,
                "glossary_terms_applied": glossary_terms_applied,
                "resolution_source": resolution_source,
                "timestamp": utc_now_iso(),
            }
        )


def build_demo_service(settings: Settings) -> TranslationService:
    return TranslationService(settings=settings, provider=DemoTranslationProvider())
