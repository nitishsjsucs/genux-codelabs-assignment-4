"""Server-Sent Events framing and a small transcript printer shared by the labs."""

from __future__ import annotations

import json
from typing import Any


def encode(payload: Any) -> bytes:
    """One SSE frame: `data: <json>` and a blank line. Newlines inside JSON are escaped by json.dumps."""
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def short(value: Any, limit: int = 110) -> str:
    text = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    text = text.replace("\n", "\\n")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def banner(title: str) -> str:
    line = "=" * max(60, len(title) + 4)
    return f"{line}\n  {title}\n{line}"
