from __future__ import annotations

import math
import re


class FixedSizeChunker:
    """
    Split text into fixed-size chunks with optional overlap.

    Rules:
        - Each chunk is at most chunk_size characters long.
        - Consecutive chunks share overlap characters.
        - The last chunk contains whatever remains.
        - If text is shorter than chunk_size, return [text].
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        step = self.chunk_size - self.overlap
        chunks: list[str] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + self.chunk_size]
            chunks.append(chunk)
            if start + self.chunk_size >= len(text):
                break
        return chunks


class SentenceChunker:
    """
    Split text into chunks of at most max_sentences_per_chunk sentences.

    Sentence detection: split on ". ", "! ", "? " or ".\n".
    Strip extra whitespace from each chunk.
    """

    def __init__(self, max_sentences_per_chunk: int = 3) -> None:
        self.max_sentences_per_chunk = max(1, max_sentences_per_chunk)

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []

        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
        chunks: list[str] = []

        for start in range(0, len(sentences), self.max_sentences_per_chunk):
            chunk_sentences = sentences[start : start + self.max_sentences_per_chunk]
            chunks.append(" ".join(chunk_sentences).strip())

        return chunks


class RecursiveChunker:
    """
    Recursively split text using separators in priority order.

    Default separator priority:
        ["\n\n", "\n", ". ", " ", ""]
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, separators: list[str] | None = None, chunk_size: int = 500) -> None:
        self.separators = self.DEFAULT_SEPARATORS if separators is None else list(separators)
        self.chunk_size = chunk_size

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        return [chunk.strip() for chunk in self._split(text, self.separators) if chunk.strip()]

    def _split(self, current_text: str, remaining_separators: list[str]) -> list[str]:
        current_text = current_text.strip()
        if not current_text:
            return []
        if len(current_text) <= self.chunk_size:
            return [current_text]

        if not remaining_separators:
            return FixedSizeChunker(chunk_size=self.chunk_size, overlap=0).chunk(current_text)

        separator = remaining_separators[0]
        next_separators = remaining_separators[1:]

        if separator == "":
            return FixedSizeChunker(chunk_size=self.chunk_size, overlap=0).chunk(current_text)

        if separator not in current_text:
            return self._split(current_text, next_separators)

        splits = [part.strip() for part in current_text.split(separator) if part.strip()]
        chunks: list[str] = []
        current_chunk = ""

        for part in splits:
            if len(part) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                chunks.extend(self._split(part, next_separators))
                continue

            candidate = part if not current_chunk else f"{current_chunk}{separator}{part}"
            if len(candidate) <= self.chunk_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks


class MarkdownStructureChunker:
    """
    Split Markdown by document structure first, then by recursive size limits.

    The chunker keeps Markdown headings as natural boundaries. This works well
    for FAQ files where each question is a heading such as "### Q: ...".
    """

    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def __init__(self, chunk_size: int = 1000, fallback_chunker: RecursiveChunker | None = None) -> None:
        self.chunk_size = chunk_size
        self.fallback_chunker = fallback_chunker or RecursiveChunker(chunk_size=chunk_size)

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []

        sections = self._split_markdown_sections(text)
        if not sections:
            return self.fallback_chunker.chunk(text)

        chunks: list[str] = []
        for section in sections:
            section_text = section["content"]
            heading_path = section["heading_path"]

            if len(section_text) <= self.chunk_size:
                chunks.append(section_text)
                continue

            for subchunk in self.fallback_chunker.chunk(section_text):
                chunks.append(self._add_heading_context(subchunk, heading_path))

        return [chunk.strip() for chunk in chunks if chunk.strip()]

    def chunk_with_metadata(self, text: str, base_metadata: dict | None = None) -> list[dict]:
        base_metadata = dict(base_metadata or {})
        sections = self._split_markdown_sections(text)
        if not sections:
            sections = [{"content": chunk, "heading_path": []} for chunk in self.fallback_chunker.chunk(text)]

        chunk_records: list[dict] = []

        for section in sections:
            section_text = section["content"]
            heading_path = section["heading_path"]
            section_chunks = (
                [section_text]
                if len(section_text) <= self.chunk_size
                else [self._add_heading_context(chunk, heading_path) for chunk in self.fallback_chunker.chunk(section_text)]
            )

            for chunk in section_chunks:
                index = len(chunk_records)
                chunk_records.append(self._make_chunk_record(chunk, heading_path, index, base_metadata))

        return chunk_records

    def _make_chunk_record(
        self,
        chunk: str,
        heading_path: list[str],
        index: int,
        base_metadata: dict,
    ) -> dict:
        doc_id = base_metadata.get("doc_id", "document")
        metadata = {
            **base_metadata,
            "chunk_index": index,
            "chunk_id": f"{doc_id}_chunk_{index}",
            "heading_path": " > ".join(heading_path),
            "section_title": heading_path[-1] if heading_path else "",
        }
        return {"content": chunk.strip(), "metadata": metadata}

    def _split_markdown_sections(self, text: str) -> list[dict]:
        sections: list[dict] = []
        heading_stack: list[str] = []
        current_heading_path: list[str] = []
        current_lines: list[str] = []

        def flush_current_section() -> None:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(
                    {
                        "heading_path": list(current_heading_path),
                        "content": content,
                    }
                )

        for line in text.splitlines():
            match = self.HEADING_PATTERN.match(line)
            if match:
                flush_current_section()

                level = len(match.group(1))
                title = match.group(2).strip()
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_heading_path = list(heading_stack)
                current_lines = [line]
                continue

            current_lines.append(line)

        flush_current_section()
        return sections

    def _add_heading_context(self, chunk: str, heading_path: list[str]) -> str:
        if not heading_path:
            return chunk

        context = f"[Markdown path: {' > '.join(heading_path)}]"
        if chunk.startswith(context):
            return chunk
        return f"{context}\n{chunk}"

    def _extract_heading_path(self, chunk: str) -> list[str]:
        first_line = chunk.splitlines()[0].strip() if chunk.strip() else ""
        if first_line.startswith("[Markdown path: ") and first_line.endswith("]"):
            path_text = first_line.removeprefix("[Markdown path: ").removesuffix("]")
            return [part.strip() for part in path_text.split(">") if part.strip()]

        headings = []
        for line in chunk.splitlines():
            match = self.HEADING_PATTERN.match(line)
            if match:
                headings.append(match.group(2).strip())
        return headings


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def compute_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    cosine_similarity = dot(a, b) / (||a|| * ||b||)

    Returns 0.0 if either vector has zero magnitude.
    """
    norm_a = math.sqrt(sum(value * value for value in vec_a))
    norm_b = math.sqrt(sum(value * value for value in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return _dot(vec_a, vec_b) / (norm_a * norm_b)


class ChunkingStrategyComparator:
    """Run all built-in chunking strategies and compare their results."""

    def compare(self, text: str, chunk_size: int = 200) -> dict:
        strategies = {
            "fixed_size": FixedSizeChunker(chunk_size=chunk_size, overlap=0),
            "by_sentences": SentenceChunker(max_sentences_per_chunk=3),
            "recursive": RecursiveChunker(chunk_size=chunk_size),
        }

        comparison: dict = {}
        for name, chunker in strategies.items():
            chunks = chunker.chunk(text)
            count = len(chunks)
            avg_length = sum(len(chunk) for chunk in chunks) / count if count else 0
            comparison[name] = {
                "count": count,
                "avg_length": avg_length,
                "chunks": chunks,
            }

        return comparison
