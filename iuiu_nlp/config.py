from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    provider: str = "auto"
    default_source_language: str = "en"
    fallback_language: str = "en"
    default_bilingual: bool = True


def load_settings() -> Settings:
    cwd = Path.cwd()
    data_dir = Path(os.getenv("DATA_DIR", cwd / "data"))
    return Settings(
        data_dir=data_dir,
        provider=os.getenv("TRANSLATION_PROVIDER", "auto").strip().casefold(),
        default_source_language=os.getenv("DEFAULT_SOURCE_LANGUAGE", "en").strip().casefold(),
        fallback_language=os.getenv("FALLBACK_LANGUAGE", "en").strip().casefold(),
        default_bilingual=os.getenv("DEFAULT_BILINGUAL", "true").strip().casefold() != "false",
    )

