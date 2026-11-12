"""The model behind every lab: a scripted stand-in by default, Claude with --live.

Both classes expose one method, ``stream(messages, tools=None, system=None)``,
that yields *pieces*:

    ("text", delta)                     the model is writing prose / a spec
    ("tool_start", call_id, name)       a tool call begins
    ("tool_args", call_id, delta)       a chunk of the call's JSON arguments
    ("tool_end", call_id)               the call's arguments are complete

Messages use one neutral shape so the labs never depend on a provider:

    {"role": "user", "content": str}
    {"role": "assistant", "content": str | None, "tool_calls": [{"id", "name", "arguments": str}]}
    {"role": "tool", "tool_call_id": str, "content": str}

ScriptedModel replays fixed turns (so every demo and test is deterministic and
free). A script is either a list of turns - turn i answers the conversation
that already holds i assistant messages - or a function of the messages, for
scripts that react to a tool result (the self-correction demos).
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Iterator, List, Optional, Union

Turn = dict  # {"text": str, "tool_calls": [{"name": str, "arguments": dict}]}


class ScriptedModel:
    name = "scripted"

    def __init__(self, script: Union[List[Turn], Callable[[list], Turn]], chunk: int = 32, delay: float = 0.0):
        self.script = script
        self.chunk = chunk
        self.delay = delay
        self.calls = 0  # model calls made, for the transcripts

    def _turn(self, messages: list) -> Turn:
        if callable(self.script):
            return self.script(messages)
        index = sum(1 for m in messages if m["role"] == "assistant")
        if index >= len(self.script):
            return {"text": "(the script has no more turns)"}
        return self.script[index]

    def _pieces(self, text: str) -> Iterator[str]:
        for i in range(0, len(text), self.chunk):
            if self.delay:
                time.sleep(self.delay)
            yield text[i:i + self.chunk]

    def stream(self, messages: list, tools: Optional[list] = None, system: Optional[str] = None) -> Iterator[tuple]:
        self.calls += 1
        turn = self._turn(messages)
        for delta in self._pieces(turn.get("text", "")):
            yield ("text", delta)
        for n, call in enumerate(turn.get("tool_calls", []), 1):
            call_id = call.get("id") or f"call_{self.calls}_{n}"
            yield ("tool_start", call_id, call["name"])
            for delta in self._pieces(json.dumps(call["arguments"])):
                yield ("tool_args", call_id, delta)
            yield ("tool_end", call_id)


class LiveClaude:
    """Claude through the official Anthropic Python SDK (pip install anthropic; Python 3.10+).

    Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login`
    profile). The model defaults to claude-opus-5-5 and can be changed with
    VOLTPILOT_MODEL. Server-side refusal fallbacks are switched on.
    Text streams token by token; tool inputs are emitted once the turn completes.
    """

    def __init__(self, model: Optional[str] = None, max_tokens: int = 16000):
        import anthropic  # imported lazily: offline demos must not need it

        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.name = model or os.environ.get("VOLTPILOT_MODEL", "claude-opus-5-5")
        self.max_tokens = max_tokens
        self.last_raw = None

    @staticmethod
    def to_anthropic(messages: list) -> list:
        out: list = []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                if m.get("_raw") is not None:  # replay the model's own blocks unchanged (thinking included)
                    out.append({"role": "assistant", "content": m["_raw"]})
                    continue
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for c in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": json.loads(c["arguments"] or "{}")})
                out.append({"role": "assistant", "content": blocks})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)  # all results of one turn go in one user message
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    def stream(self, messages: list, tools: Optional[list] = None, system: Optional[str] = None) -> Iterator[tuple]:
        kwargs = dict(
            model=self.name,
            max_tokens=self.max_tokens,
            messages=self.to_anthropic(messages),
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools
            ]
        with self.client.beta.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "text":
                    yield ("text", event.text)
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            raise RuntimeError("the model declined this request (stop_reason=refusal)")
        self.last_raw = final.content
        for block in final.content:
            if block.type == "tool_use":
                yield ("tool_start", block.id, block.name)
                yield ("tool_args", block.id, json.dumps(block.input))
                yield ("tool_end", block.id)


def collect(pieces: Iterator[tuple]) -> tuple:
    """Drain a piece stream into (text, [calls]) - for code that does not stream to a UI."""
    text, calls = [], {}
    for piece in pieces:
        if piece[0] == "text":
            text.append(piece[1])
        elif piece[0] == "tool_start":
            calls[piece[1]] = {"id": piece[1], "name": piece[2], "arguments": ""}
        elif piece[0] == "tool_args":
            calls[piece[1]]["arguments"] += piece[2]
    return "".join(text), list(calls.values())


def assistant_message(model, text: str, calls: list) -> dict:
    """The assistant turn to append to the history; keeps Claude's raw blocks when there are any."""
    message = {"role": "assistant", "content": text or None}
    if calls:
        message["tool_calls"] = calls
    raw = getattr(model, "last_raw", None)
    if raw is not None:
        message["_raw"] = raw
    return message


def get_model(script, live: bool = False, delay: float = 0.0):
    """The scripted model, or Claude when --live was passed."""
    if live:
        return LiveClaude()
    return ScriptedModel(script, delay=delay)


def wants_live(argv: list) -> bool:
    return "--live" in argv
