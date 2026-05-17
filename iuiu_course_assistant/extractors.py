from __future__ import annotations

import re
import zipfile
import zlib
from html import unescape
from io import BytesIO
from pathlib import Path


TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".html",
    ".htm",
    ".xml",
    ".yml",
    ".yaml",
}


def extract_text_from_upload(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return _normalize_text(_decode_text_bytes(content))
    if suffix == ".docx":
        return _extract_docx_text(content)
    if suffix == ".pdf":
        return _extract_pdf_text(content)

    decoded = _normalize_text(_decode_text_bytes(content, strict=False))
    if _looks_like_text(decoded):
        return decoded
    raise ValueError(
        "Unsupported upload type. Use .pdf, .txt, .md, .csv, .json, .html, or .docx."
    )


def _decode_text_bytes(content: bytes, *, strict: bool = True) -> str:
    encodings = ("utf-8", "utf-16", "latin-1")
    errors = "strict" if strict else "ignore"
    for encoding in encodings:
        try:
            return content.decode(encoding, errors=errors)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except (KeyError, zipfile.BadZipFile) as error:
        raise ValueError("The uploaded .docx file could not be read.") from error

    text = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    text = re.sub(r"</w:p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return _normalize_text(unescape(text))


def _extract_pdf_text(content: bytes) -> str:
    stream_pattern = re.compile(rb"(<<.*?>>)\s*stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    extracted_fragments: list[str] = []
    for match in stream_pattern.finditer(content):
        dictionary_bytes = match.group(1)
        stream_bytes = match.group(2)
        decoded_stream = stream_bytes
        if b"/FlateDecode" in dictionary_bytes:
            try:
                decoded_stream = zlib.decompress(stream_bytes)
            except zlib.error:
                continue

        fragment = _extract_pdf_stream_text(decoded_stream)
        if fragment:
            extracted_fragments.append(fragment)

    return _normalize_text("\n".join(fragment for fragment in extracted_fragments if fragment))


def _extract_pdf_stream_text(stream_bytes: bytes) -> str:
    text = stream_bytes.decode("latin-1", errors="ignore")
    collected: list[str] = []

    for literal in re.findall(r"\((.*?)(?<!\\)\)\s*Tj", text, flags=re.DOTALL):
        value = _decode_pdf_literal(literal)
        if value.strip():
            collected.append(value)

    for array_content in re.findall(r"\[(.*?)\]\s*TJ", text, flags=re.DOTALL):
        parts = [_decode_pdf_literal(part) for part in re.findall(r"\((.*?)(?<!\\)\)", array_content)]
        joined = "".join(part for part in parts if part)
        if joined.strip():
            collected.append(joined)

    return "\n".join(collected)


def _decode_pdf_literal(value: str) -> str:
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    value = re.sub(
        r"\\([0-7]{1,3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )
    value = value.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")
    return value


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _looks_like_text(text: str) -> bool:
    if not text.strip():
        return False
    printable = sum(1 for character in text if character.isprintable() or character in "\n\t")
    return printable / max(len(text), 1) > 0.9
