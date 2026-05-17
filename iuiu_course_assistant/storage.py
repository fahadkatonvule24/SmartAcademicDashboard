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


class ResourceRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, dict)

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data[payload["resource_id"]] = payload
        self.store.write(data)
        return deepcopy(payload)

    def get(self, resource_id: str) -> dict[str, Any] | None:
        resource = self.store.read().get(resource_id)
        return deepcopy(resource) if resource else None

    def list(self, course_code: str | None = None) -> list[dict[str, Any]]:
        values = list(self.store.read().values())
        if course_code:
            values = [
                value for value in values if value.get("course_code") == course_code.strip().upper()
            ]
        values.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return deepcopy(values)

    def count(self) -> int:
        return len(self.store.read())


class ChunkRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, list)

    def replace_for_resource(self, resource_id: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        data = [item for item in self.store.read() if item.get("resource_id") != resource_id]
        data.extend(chunks)
        self.store.write(data)
        return deepcopy(chunks)

    def list(self, course_code: str | None = None, topic: str | None = None) -> list[dict[str, Any]]:
        values = self.store.read()
        if course_code:
            values = [
                value for value in values if value.get("course_code") == course_code.strip().upper()
            ]
        if topic:
            expected = topic.strip().casefold()
            values = [value for value in values if str(value.get("topic", "")).casefold() == expected]
        return deepcopy(values)

    def count(self) -> int:
        return len(self.store.read())


class AuditLogRepository:
    def __init__(self, path: Path):
        self.store = JsonFileStore(path, list)

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.store.read()
        data.append(payload)
        self.store.write(data)
        return deepcopy(payload)

    def count(self) -> int:
        return len(self.store.read())
