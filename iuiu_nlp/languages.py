from __future__ import annotations

from dataclasses import dataclass

LANGUAGES = {
    "en": "English",
    "sw": "Swahili",
    "fr": "French",
    "so": "Somali",
    "ar": "Arabic",
    "am": "Amharic",
    "rw": "Kinyarwanda",
    "tr": "Turkish",
    "ur": "Urdu",
}

LANGUAGE_NAMES = {name.casefold(): code for code, name in LANGUAGES.items()}

DEFAULT_NATIONALITY_LANGUAGE = {
    "burundi": "fr",
    "burundian": "fr",
    "chad": "fr",
    "chadian": "fr",
    "congo drc": "fr",
    "democratic republic of the congo": "fr",
    "dr congo": "fr",
    "eritrea": "ar",
    "eritrean": "ar",
    "ethiopia": "am",
    "ethiopian": "am",
    "kenya": "sw",
    "kenyan": "sw",
    "nigeria": "en",
    "nigerian": "en",
    "pakistan": "ur",
    "pakistani": "ur",
    "rwanda": "rw",
    "rwandan": "rw",
    "somalia": "so",
    "somali": "so",
    "south sudan": "en",
    "south sudanese": "en",
    "sudan": "ar",
    "sudanese": "ar",
    "tanzania": "sw",
    "tanzanian": "sw",
    "turkey": "tr",
    "turkish": "tr",
    "uganda": "en",
    "ugandan": "en",
}


def normalize_token(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().replace("_", " ").split())
    return normalized or None


def canonicalize_language(value: str | None) -> str | None:
    token = normalize_token(value)
    if token is None:
        return None
    if token in LANGUAGES:
        return token
    return LANGUAGE_NAMES.get(token)


def language_name(language_code: str) -> str:
    return LANGUAGES.get(language_code, language_code)


@dataclass(frozen=True)
class LanguageDecision:
    code: str
    reason: str


def resolve_target_language(
    *,
    override: str | None,
    preferred_language: str | None,
    nationality: str | None,
    nationality_map: dict[str, str],
    fallback: str = "en",
) -> LanguageDecision:
    override_code = canonicalize_language(override)
    if override and override_code is None:
        raise ValueError(f"Unsupported target language: {override}")
    if override_code:
        return LanguageDecision(code=override_code, reason="override")

    preferred_code = canonicalize_language(preferred_language)
    if preferred_language and preferred_code is None:
        raise ValueError(f"Unsupported preferred language: {preferred_language}")
    if preferred_code:
        return LanguageDecision(code=preferred_code, reason="profile")

    nationality_key = normalize_token(nationality)
    if nationality_key:
        mapped_language = canonicalize_language(nationality_map.get(nationality_key))
        if mapped_language:
            return LanguageDecision(code=mapped_language, reason="nationality")

    fallback_code = canonicalize_language(fallback) or "en"
    return LanguageDecision(code=fallback_code, reason="fallback")
