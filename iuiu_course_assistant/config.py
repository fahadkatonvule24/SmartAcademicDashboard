from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    upload_dir: Path
    answer_provider: str = "demo"
    chunk_size: int = 520
    chunk_overlap: int = 120
    default_top_k: int = 3
    translation_enabled: bool = True


def load_settings() -> Settings:
    cwd = Path.cwd()
    data_dir = Path(os.getenv("COURSE_ASSISTANT_DATA_DIR", cwd / "data" / "course_assistant"))
    upload_dir = Path(os.getenv("COURSE_ASSISTANT_UPLOAD_DIR", data_dir / "uploads"))
    return Settings(
        data_dir=data_dir,
        upload_dir=upload_dir,
        answer_provider=os.getenv("COURSE_ASSISTANT_PROVIDER", "demo").strip().casefold(),
        chunk_size=max(int(os.getenv("COURSE_ASSISTANT_CHUNK_SIZE", "520")), 180),
        chunk_overlap=max(int(os.getenv("COURSE_ASSISTANT_CHUNK_OVERLAP", "120")), 0),
        default_top_k=max(int(os.getenv("COURSE_ASSISTANT_TOP_K", "3")), 1),
        translation_enabled=os.getenv("COURSE_ASSISTANT_TRANSLATION", "true").strip().casefold()
        != "false",
    )
