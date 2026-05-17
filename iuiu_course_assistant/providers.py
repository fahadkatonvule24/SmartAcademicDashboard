from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .retrieval import best_snippet


@dataclass(frozen=True)
class AnswerResult:
    text: str
    citations: list[dict[str, Any]]


class AnswerProvider:
    name = "base"

    def answer(
        self,
        *,
        question: str,
        course_code: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> AnswerResult:
        raise NotImplementedError


class DemoGroundedAnswerProvider(AnswerProvider):
    name = "course_support"

    def answer(
        self,
        *,
        question: str,
        course_code: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> AnswerResult:
        if not retrieved_chunks:
            return AnswerResult(
                text=(
                    f"I could not find enough indexed evidence in {course_code.upper()} resources "
                    "to answer that yet. Upload notes for this topic or ask a more specific question."
                ),
                citations=[],
            )

        guidance_lines: list[str] = []
        citations: list[dict[str, Any]] = []
        for chunk in retrieved_chunks[:3]:
            snippet = best_snippet(chunk.get("text", ""), question)
            guidance_lines.append(f"{chunk['title']}: {snippet}")
            citations.append(
                {
                    "resource_id": chunk["resource_id"],
                    "chunk_id": chunk["chunk_id"],
                    "title": chunk["title"],
                    "topic": chunk.get("topic"),
                    "snippet": snippet,
                    "score": chunk.get("score"),
                }
            )

        answer_text = (
            f"Based on the indexed {course_code.upper()} materials, the strongest evidence is: "
            + " ".join(guidance_lines)
        )
        return AnswerResult(text=answer_text, citations=citations)


def build_provider(name: str) -> AnswerProvider:
    if name in {"demo", "grounded_demo", "auto"}:
        return DemoGroundedAnswerProvider()
    raise ValueError(f"Unsupported answer provider: {name}")
