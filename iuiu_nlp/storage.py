from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


class JsonFileStore:
    def __init__(self, path: Path, default_factory: Callable[[], Any]):
        self.path = path
        self.default_factory = default_factory
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(self.default_factory())

    def read(self) -> Any:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            data = self.default_factory()
            self.write(data)
            return data

    def write(self, data: Any) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)


class ProfileRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get(self, student_id: str) -> dict[str, Any] | None:
        return self.store.read().get(student_id)

    def upsert(self, student_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[student_id] = payload
        self.store.write(data)
        return payload


class GlossaryRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get_terms(self, course_code: str | None) -> list[dict[str, Any]]:
        if not course_code:
            return []
        data = self.store.read()
        return deepcopy(data.get(course_code.upper(), []))

    def upsert_terms(self, course_code: str, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        data = self.store.read()
        key = course_code.upper()
        existing_terms = data.setdefault(key, [])
        index = {term["source"].casefold(): position for position, term in enumerate(existing_terms)}

        for term in terms:
            source_key = term["source"].casefold()
            if source_key in index:
                current = existing_terms[index[source_key]]
                current_targets = current.setdefault("targets", {})
                current_targets.update(term.get("targets", {}))
                if term.get("notes"):
                    current["notes"] = term["notes"]
            else:
                existing_terms.append(term)
                index[source_key] = len(existing_terms) - 1

        self.store.write(data)
        return deepcopy(existing_terms)


class TranslationCacheRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def get(self, cache_key: str) -> dict[str, Any] | None:
        return self.store.read().get(cache_key)

    def set(self, cache_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[cache_key] = payload
        self.store.write(data)
        return payload


class AuditLogRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, list)

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data.append(payload)
        self.store.write(data)
        return payload


class NationalityMapRepository:
    def __init__(self, path: Path, default_mapping: dict[str, str]):
        self.store = JsonFileStore(path, lambda: deepcopy(default_mapping))

    def get_all(self) -> dict[str, str]:
        return self.store.read()

    def upsert(self, nationality: str, language: str) -> dict[str, str]:
        data = self.store.read()
        data[nationality] = language
        self.store.write(data)
        return data

