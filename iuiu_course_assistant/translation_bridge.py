from __future__ import annotations

from typing import Any


class LocalTranslationBridge:
    def __init__(self, enabled: bool = True):
        self.available = False
        self._service = None
        if not enabled:
            return

        try:
            from iuiu_nlp.config import load_settings
            from iuiu_nlp.service import TranslationService

            self._service = TranslationService(settings=load_settings())
            self.available = True
        except Exception:
            self._service = None
            self.available = False

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
        if not self._service:
            raise RuntimeError("Translation bridge is unavailable")
        return self._service.translate(
            student_id=student_id,
            text=text,
            course_code=course_code,
            target_language=target_language,
            nationality=nationality,
            content_type="chat",
            bilingual=bilingual,
        )
