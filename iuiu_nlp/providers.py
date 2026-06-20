from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


TOKEN_TEMPLATE = "ZXQTERM{index:03d}ZXQ"


@dataclass(frozen=True)
class ProviderTranslationResult:
    text: str
    glossary_terms_applied: list[str]


def protect_glossary_terms(
    text: str, glossary_terms: list[dict[str, object]], target_language: str
) -> tuple[str, dict[str, str], list[str]]:
    protected_text = text
    replacements: dict[str, str] = {}
    applied_terms: list[str] = []

    ordered_terms = sorted(glossary_terms, key=lambda item: len(str(item["source"])), reverse=True)
    for index, term in enumerate(ordered_terms):
        source = str(term["source"]).strip()
        if not source:
            continue

        placeholder = TOKEN_TEMPLATE.format(index=index)
        target_map = term.get("targets", {})
        replacement = source
        if isinstance(target_map, dict):
            replacement = str(target_map.get(target_language) or source)

        pattern = glossary_term_pattern(source)
        if not pattern.search(protected_text):
            continue

        protected_text = pattern.sub(placeholder, protected_text)
        replacements[placeholder] = replacement
        applied_terms.append(source)

    return protected_text, replacements, applied_terms


def glossary_term_pattern(source: str) -> re.Pattern[str]:
    escaped = re.escape(source)
    prefix = r"(?<!\w)" if source[0].isalnum() else ""
    suffix = r"(?!\w)" if source[-1].isalnum() else ""
    return re.compile(f"{prefix}{escaped}{suffix}", flags=re.IGNORECASE)


def restore_glossary_terms(text: str, replacements: dict[str, str]) -> str:
    restored_text = text
    for placeholder, value in replacements.items():
        restored_text = restored_text.replace(placeholder, value)
    return restored_text


class TranslationProvider(ABC):
    name = "base"

    @abstractmethod
    def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        glossary_terms: list[dict[str, object]] | None = None,
    ) -> ProviderTranslationResult:
        raise NotImplementedError


class DemoTranslationProvider(TranslationProvider):
    name = "local_translation"

    LEXICON = {
        "sw": {
            "course": "kozi",
            "dashboard": "dashibodi",
            "feedback": "maoni",
            "language": "lugha",
            "note": "dokezo",
            "notes": "madokezo",
            "plan": "mpango",
            "quiz": "jaribio",
            "resource": "rasilimali",
            "resources": "rasilimali",
            "student": "mwanafunzi",
            "study": "somo",
            "translation": "tafsiri",
        },
        "fr": {
            "course": "cours",
            "dashboard": "tableau",
            "feedback": "retour",
            "language": "langue",
            "note": "note",
            "notes": "notes",
            "plan": "plan",
            "quiz": "quiz",
            "resource": "ressource",
            "resources": "ressources",
            "student": "etudiant",
            "study": "etude",
            "translation": "traduction",
        },
        "rw": {
            "course": "amasomo",
            "dashboard": "ikibaho",
            "feedback": "ibitekerezo",
            "language": "ururimi",
            "note": "inyandiko",
            "notes": "inyandiko",
            "plan": "gahunda",
            "quiz": "ikizamini",
            "resource": "ibikoresho",
            "resources": "ibikoresho",
            "student": "umunyeshuri",
            "study": "kwiga",
            "translation": "ubusobanuro",
        },
        "so": {
            "course": "koorso",
            "dashboard": "dashboard",
            "feedback": "jawaab",
            "language": "luuqad",
            "note": "qoraal",
            "notes": "qoraallo",
            "plan": "qorshe",
            "quiz": "imtixaan",
            "resource": "kheyraad",
            "resources": "kheyraad",
            "student": "arday",
            "study": "barasho",
            "translation": "turjumid",
        },
        "tr": {
            "course": "ders",
            "dashboard": "panel",
            "feedback": "geri bildirim",
            "language": "dil",
            "note": "not",
            "notes": "notlar",
            "plan": "plan",
            "quiz": "test",
            "resource": "kaynak",
            "resources": "kaynaklar",
            "student": "ogrenci",
            "study": "calisma",
            "translation": "ceviri",
        },
        "ur": {
            "course": "course",
            "dashboard": "dashboard",
            "feedback": "feedback",
            "language": "language",
            "note": "note",
            "notes": "notes",
            "plan": "plan",
            "quiz": "quiz",
            "resource": "resource",
            "resources": "resources",
            "student": "student",
            "study": "study",
            "translation": "translation",
        },
    }

    def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        glossary_terms: list[dict[str, object]] | None = None,
    ) -> ProviderTranslationResult:
        protected_text, replacements, applied_terms = protect_glossary_terms(
            text, glossary_terms or [], target_language
        )

        if target_language == source_language:
            translated_text = protected_text
        else:
            translated_text = self._replace_known_terms(protected_text, target_language)

        restored_text = restore_glossary_terms(translated_text, replacements)
        return ProviderTranslationResult(
            text=restored_text,
            glossary_terms_applied=applied_terms,
        )

    def _replace_known_terms(self, text: str, target_language: str) -> str:
        replacements = self.LEXICON.get(target_language, {})
        translated_text = text
        for source, target in replacements.items():
            pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
            translated_text = pattern.sub(target, translated_text)
        return translated_text


class DeepTranslatorProvider(TranslationProvider):
    name = "deep_translator"

    def __init__(self) -> None:
        from deep_translator import GoogleTranslator

        self._translator_class = GoogleTranslator

    def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        glossary_terms: list[dict[str, object]] | None = None,
    ) -> ProviderTranslationResult:
        protected_text, replacements, applied_terms = protect_glossary_terms(
            text, glossary_terms or [], target_language
        )
        translated_text = self._translator_class(
            source=source_language,
            target=target_language,
        ).translate(protected_text)
        restored_text = restore_glossary_terms(translated_text, replacements)
        return ProviderTranslationResult(
            text=restored_text,
            glossary_terms_applied=applied_terms,
        )


def build_provider(provider_name: str) -> TranslationProvider:
    selected = provider_name.strip().casefold()
    if selected in {"auto", "deep_translator"}:
        try:
            return DeepTranslatorProvider()
        except Exception:
            if selected == "deep_translator":
                raise

    if selected in {"auto", "demo"}:
        return DemoTranslationProvider()

    raise ValueError(f"Unsupported provider: {provider_name}")
