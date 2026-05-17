from __future__ import annotations

import re
from typing import Any


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 1 and token not in STOP_WORDS
    }


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized) if sentence.strip()]
    if not sentences:
        return [normalized[:chunk_size]]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for sentence in sentences:
        if len(sentence) > chunk_size:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_length = 0
            chunks.extend(_slice_long_text(sentence, chunk_size, overlap))
            continue

        projected = current_length + len(sentence) + (1 if current else 0)
        if current and projected > chunk_size:
            chunk = " ".join(current).strip()
            chunks.append(chunk)
            overlap_text = chunk[-overlap:].strip() if overlap else ""
            current = [overlap_text, sentence] if overlap_text else [sentence]
            current_length = sum(len(part) for part in current) + max(len(current) - 1, 0)
            continue

        current.append(sentence)
        current_length = projected

    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def rank_chunks(
    *,
    question: str,
    chunks: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    if not question_tokens:
        return []

    ranked: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_tokens = set(chunk.get("terms", [])) or tokenize(chunk.get("text", ""))
        title_tokens = tokenize(chunk.get("title", ""))
        topic_tokens = tokenize(chunk.get("topic", ""))
        overlap = len(question_tokens & chunk_tokens)
        if overlap == 0:
            continue

        score = float(overlap * 3)
        score += len(question_tokens & title_tokens) * 1.5
        score += len(question_tokens & topic_tokens) * 1.5
        if any(token in chunk.get("text", "").casefold() for token in question_tokens):
            score += 0.5

        enriched = dict(chunk)
        enriched["score"] = round(score, 3)
        ranked.append(enriched)

    ranked.sort(key=lambda item: (-item["score"], item.get("position", 0)))
    return ranked[:top_k]


def best_snippet(text: str, question: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text) if sentence.strip()]
    if not sentences:
        return text.strip()

    question_tokens = tokenize(question)
    best_sentence = sentences[0]
    best_score = -1
    for sentence in sentences:
        score = len(question_tokens & tokenize(sentence))
        if score > best_score:
            best_score = score
            best_sentence = sentence
    return best_sentence


def _slice_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        return [text]
    step = max(chunk_size - overlap, 1)
    return [
        text[index : index + chunk_size].strip()
        for index in range(0, len(text), step)
        if text[index : index + chunk_size].strip()
    ]
