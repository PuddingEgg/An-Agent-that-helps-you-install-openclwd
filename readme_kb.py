from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._+-]{1,}", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
STAGE_HINTS = {
    "welcome": ("install", "quick start", "configuration"),
    "env": ("install", "quick start"),
    "install": ("install", "quick start", "from source"),
    "onboard": ("quick start", "install", "configuration"),
    "gateway": ("quick start", "how it works", "key subsystems"),
    "config": ("configuration", "agent workspace"),
}


@dataclass
class Chunk:
    source_name: str
    title: str
    level: int
    start_line: int
    content: str

    @property
    def label(self) -> str:
        return f"{self.title} ({self.source_name}:{self.start_line})"


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class ReadmeKB:
    def __init__(self, readme_path: str | Path) -> None:
        self.readme_path = Path(readme_path)
        self.text = self.readme_path.read_text(encoding="utf-8")
        self.chunks = self._parse_chunks(self.text)

    def _parse_chunks(self, text: str) -> list[Chunk]:
        lines = text.splitlines()
        chunks: list[Chunk] = []
        heading_stack: list[str] = []
        current_title = "README Overview"
        current_level = 0
        current_start = 1
        current_lines: list[str] = []
        in_code_block = False

        for lineno, line in enumerate(lines, start=1):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                current_lines.append(line)
                continue

            match = None if in_code_block else HEADING_RE.match(line)
            if match:
                if current_lines:
                    chunks.append(
                        Chunk(
                            source_name=self.readme_path.name,
                            title=current_title,
                            level=current_level,
                            start_line=current_start,
                            content="\n".join(current_lines).strip(),
                        )
                    )
                level = len(match.group(1))
                heading = match.group(2).strip()
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(heading)
                current_title = " > ".join(heading_stack)
                current_level = level
                current_start = lineno
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            chunks.append(
                Chunk(
                    source_name=self.readme_path.name,
                    title=current_title,
                    level=current_level,
                    start_line=current_start,
                    content="\n".join(current_lines).strip(),
                )
            )

        return chunks

    def search(self, query: str, stage: str, limit: int = 4) -> list[Chunk]:
        query_tokens = set(tokenize(query))
        stage_tokens = set(tokenize(stage))
        combined_tokens = query_tokens | stage_tokens
        if not combined_tokens:
            return self._fallback_chunks(limit)

        scored: list[tuple[float, Chunk]] = []
        for chunk in self.chunks:
            title_tokens = tokenize(chunk.title)
            body_tokens = tokenize(chunk.content)
            title_matches = sum(1 for token in combined_tokens if token in title_tokens)
            body_matches = sum(1 for token in combined_tokens if token in body_tokens)
            score = title_matches * 4 + body_matches

            title_lower = chunk.title.lower()
            if any(word in title_lower for word in ("install", "quick start", "onboard", "configuration")):
                score += 1.5
            if stage and stage.lower() in title_lower:
                score += 3
            for hint in STAGE_HINTS.get(stage.lower(), ()):
                if hint in title_lower:
                    score += 3
            if query.strip().lower() in chunk.content.lower():
                score += 5

            if score > 0:
                scored.append((score, chunk))

        if not scored:
            return self._fallback_chunks(limit)

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]

    def _fallback_chunks(self, limit: int) -> list[Chunk]:
        preferred = []
        keywords = ("install", "quick start", "from source", "configuration", "how it works")
        for chunk in self.chunks:
            title_lower = chunk.title.lower()
            if any(word in title_lower for word in keywords):
                preferred.append(chunk)
        return preferred[:limit] or self.chunks[:limit]

    def format_chunks(self, chunks: list[Chunk]) -> str:
        blocks = []
        for chunk in chunks:
            blocks.append(f"[{chunk.label}]\n{chunk.content}")
        return "\n\n".join(blocks)
