"""AG-UI with no library: typed events, a run as a generator, and checks.

AG-UI (Agent-User Interaction protocol) is a stream of JSON events from the
agent to the frontend. One HTTP POST carries a RunAgentInput (threadId, runId,
state, messages, tools, context, forwardedProps); the reply is SSE, one event
per frame. The event names and camelCase fields below follow the AG-UI core
schema (docs.ag-ui.com/concepts/events).

`run_agent()` is the whole server: it streams the model's text and tool calls
as events, executes *server* tools (whose effects arrive as STATE_DELTA JSON
Patches), and ends the run when the model calls a *client* tool - a tool the
frontend declared in RunAgentInput.tools - so the page can execute it and send
the result on the next run.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from common.jsonpatch import apply_patch
from common.llm import assistant_message
from common.sse import short

# event type -> required fields (camelCase on the wire)
EVENT_FIELDS: Dict[str, List[str]] = {
    "RUN_STARTED": ["threadId", "runId"],
    "RUN_FINISHED": ["threadId", "runId"],
    "RUN_ERROR": ["message"],
    "STEP_STARTED": ["stepName"],
    "STEP_FINISHED": ["stepName"],
    "TEXT_MESSAGE_START": ["messageId", "role"],
    "TEXT_MESSAGE_CONTENT": ["messageId", "delta"],
    "TEXT_MESSAGE_END": ["messageId"],
    "TOOL_CALL_START": ["toolCallId", "toolCallName"],
    "TOOL_CALL_ARGS": ["toolCallId", "delta"],
    "TOOL_CALL_END": ["toolCallId"],
    "TOOL_CALL_RESULT": ["messageId", "toolCallId", "content"],
    "STATE_SNAPSHOT": ["snapshot"],
    "STATE_DELTA": ["delta"],
    "MESSAGES_SNAPSHOT": ["messages"],
    "CUSTOM": ["name", "value"],
}


def event(kind: str, **fields) -> dict:
    if kind not in EVENT_FIELDS:
        raise ValueError(f"not an AG-UI event type: {kind}")
    e = {"type": kind, **fields}
    e.setdefault("timestamp", int(time.time() * 1000))
    return e


def validate_event(e: dict) -> List[str]:
    kind = e.get("type")
    if kind not in EVENT_FIELDS:
        return [f"unknown event type {kind!r}"]
    errors = [f"{kind}: missing {f}" for f in EVENT_FIELDS[kind] if f not in e]
    if kind == "TEXT_MESSAGE_CONTENT" and e.get("delta") == "":
        errors.append("TEXT_MESSAGE_CONTENT: delta must not be empty")
    if kind == "STATE_DELTA" and not isinstance(e.get("delta"), list):
        errors.append("STATE_DELTA: delta must be a JSON Patch array")
    return errors


def check_sequence(events: List[dict]) -> List[str]:
    """Lifecycle rules a client relies on: one run, balanced messages and tool calls."""
    errors = [err for e in events for err in validate_event(e)]
    if not events or events[0]["type"] != "RUN_STARTED":
        errors.append("the first event must be RUN_STARTED")
    if not events or events[-1]["type"] not in ("RUN_FINISHED", "RUN_ERROR"):
        errors.append("the last event must be RUN_FINISHED or RUN_ERROR")
    open_text, open_calls = set(), set()
    for e in events:
        t = e["type"]
        if t == "TEXT_MESSAGE_START":
            open_text.add(e["messageId"])
        elif t == "TEXT_MESSAGE_CONTENT" and e["messageId"] not in open_text:
            errors.append(f"content for a message that is not open: {e['messageId']}")
        elif t == "TEXT_MESSAGE_END":
            open_text.discard(e["messageId"])
        elif t == "TOOL_CALL_START":
            open_calls.add(e["toolCallId"])
        elif t == "TOOL_CALL_ARGS" and e["toolCallId"] not in open_calls:
            errors.append(f"args for a call that is not open: {e['toolCallId']}")
        elif t == "TOOL_CALL_END":
            open_calls.discard(e["toolCallId"])
    if open_text:
        errors.append(f"text messages never ended: {sorted(open_text)}")
    if open_calls:
        errors.append(f"tool calls never ended: {sorted(open_calls)}")
    return errors


def to_neutral(messages: List[dict]) -> List[dict]:
    """AG-UI messages (camelCase, OpenAI-like toolCalls) -> the neutral shape common/llm.py uses."""
    out = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            out.append({"role": "tool", "tool_call_id": m["toolCallId"], "content": m.get("content", "")})
        elif role == "assistant":
            entry = {"role": "assistant", "content": m.get("content")}
            if m.get("toolCalls"):
                entry["tool_calls"] = [
                    {"id": c["id"], "name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                    for c in m["toolCalls"]
                ]
            out.append(entry)
        elif role in ("user", "system", "developer"):
            out.append({"role": "user", "content": m.get("content", "")})
    return out


def run_input(messages: List[dict], state: Optional[dict] = None, tools: Optional[list] = None,
              forwarded: Optional[dict] = None, thread_id: str = "thread-voltpilot") -> dict:
    """A RunAgentInput, as the page would POST it."""
    return {
        "threadId": thread_id,
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "state": state if state is not None else {},
        "messages": messages,
        "tools": tools or [],
        "context": [],
        "forwardedProps": forwarded or {},
    }


# A server tool: name -> (schema for the model, fn(args, state) -> (result text, JSON Patch ops, extra events))
ServerTool = Tuple[dict, Callable[[dict, dict], Tuple[str, list, list]]]

MAX_TURNS = 6  # model calls per run: a model that keeps calling tools must not run up the bill


def run_agent(inp: dict, model, system: str, server_tools: Dict[str, ServerTool],
              initial_state: Optional[dict] = None) -> Iterator[dict]:
    """Yield every event of one run."""
    thread_id, run_id = inp["threadId"], inp["runId"]
    yield event("RUN_STARTED", threadId=thread_id, runId=run_id)
    state = copy.deepcopy(inp.get("state") or initial_state or {})
    yield event("STATE_SNAPSHOT", snapshot=copy.deepcopy(state))  # a copy: later deltas must not rewrite it

    client_tools = {t["name"] for t in inp.get("tools") or []}
    schemas = [schema for schema, _fn in server_tools.values()] + list(inp.get("tools") or [])
    messages = to_neutral(inp.get("messages") or [])
    try:
        for turn in range(MAX_TURNS + 1):
            if turn == MAX_TURNS:
                raise RuntimeError(f"stopped after {MAX_TURNS} model calls")
            message_id = f"msg-{uuid.uuid4().hex[:8]}"
            text: List[str] = []
            calls: Dict[str, dict] = {}
            text_open = False
            for piece in model.stream(messages, schemas, system):
                if piece[0] == "text" and piece[1]:
                    if not text_open:
                        yield event("TEXT_MESSAGE_START", messageId=message_id, role="assistant")
                        text_open = True
                    text.append(piece[1])
                    yield event("TEXT_MESSAGE_CONTENT", messageId=message_id, delta=piece[1])
                elif piece[0] == "tool_start":
                    if text_open:  # close the text before the first tool call
                        yield event("TEXT_MESSAGE_END", messageId=message_id)
                        text_open = False
                    calls[piece[1]] = {"id": piece[1], "name": piece[2], "arguments": ""}
                    yield event("TOOL_CALL_START", toolCallId=piece[1], toolCallName=piece[2], parentMessageId=message_id)
                elif piece[0] == "tool_args":
                    calls[piece[1]]["arguments"] += piece[2]
                    yield event("TOOL_CALL_ARGS", toolCallId=piece[1], delta=piece[2])
                elif piece[0] == "tool_end":
                    yield event("TOOL_CALL_END", toolCallId=piece[1])
            if text_open:
                yield event("TEXT_MESSAGE_END", messageId=message_id)
            messages.append(assistant_message(model, "".join(text), list(calls.values())))
            if not calls:
                break

            waiting_on_client = False
            for call in calls.values():
                if call["name"] in client_tools:
                    waiting_on_client = True  # the page runs it; its result opens the next run
                    continue
                result, ops, extra = execute(server_tools, call, state)
                if ops:
                    apply_patch(state, ops)
                    yield event("STATE_DELTA", delta=ops)
                for e in extra:
                    yield e
                yield event("TOOL_CALL_RESULT", messageId=f"msg-{uuid.uuid4().hex[:8]}", toolCallId=call["id"],
                            content=result, role="tool")
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            if waiting_on_client:
                break
    except Exception as error:  # noqa: BLE001 - the client must always see a terminal event
        yield event("RUN_ERROR", message=str(error))
        return
    yield event("RUN_FINISHED", threadId=thread_id, runId=run_id)


def execute(server_tools: Dict[str, ServerTool], call: dict, state: dict) -> Tuple[str, list, list]:
    """Run one server tool. Every failure becomes a result the model can read - never an exception."""
    if call["name"] not in server_tools:
        return f"error: unknown tool {call['name']}", [], []
    try:
        args = json.loads(call["arguments"] or "{}")
    except json.JSONDecodeError as error:
        return f"error: arguments are not JSON ({error})", [], []
    try:
        return server_tools[call["name"]][1](args, state)
    except Exception as error:  # noqa: BLE001
        return f"error: {error}", [], []


def tool_schema(name: str, description: str, properties: dict, required: List[str]) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}


def messages_from_events(events: List[dict]) -> List[dict]:
    """Rebuild the AG-UI messages a run produced - what a client keeps for the next run."""
    msgs: List[dict] = []
    by_id: Dict[str, dict] = {}
    calls: Dict[str, dict] = {}

    def assistant(mid: str) -> dict:
        if mid not in by_id:
            by_id[mid] = {"id": mid, "role": "assistant", "content": ""}
            msgs.append(by_id[mid])
        return by_id[mid]

    for e in events:
        t = e["type"]
        if t == "TEXT_MESSAGE_START":
            assistant(e["messageId"])
        elif t == "TEXT_MESSAGE_CONTENT":
            assistant(e["messageId"])["content"] += e["delta"]
        elif t == "TOOL_CALL_START":
            m = assistant(e.get("parentMessageId") or e["toolCallId"])
            call = {"id": e["toolCallId"], "type": "function", "function": {"name": e["toolCallName"], "arguments": ""}}
            m.setdefault("toolCalls", []).append(call)
            calls[e["toolCallId"]] = call
        elif t == "TOOL_CALL_ARGS":
            calls[e["toolCallId"]]["function"]["arguments"] += e["delta"]
        elif t == "TOOL_CALL_RESULT":
            msgs.append({"id": e["messageId"], "role": "tool", "toolCallId": e["toolCallId"], "content": e["content"]})
    return msgs


def final_state(events: List[dict]) -> dict:
    """Replay STATE_SNAPSHOT / STATE_DELTA exactly as a client does."""
    state: dict = {}
    for e in events:
        if e["type"] == "STATE_SNAPSHOT":
            state = copy.deepcopy(e["snapshot"])
        elif e["type"] == "STATE_DELTA":
            state = apply_patch(state, e["delta"])
    return state


# ------------------------------------------------- the action round-trip (modes 3 and 4)


def schedule_tool_schema(windows: List[str]) -> dict:
    return tool_schema("schedule_ev_charge", "Book the EV charge for one of the offered windows.",
                       {"window": {"type": "string", "enum": windows}}, ["window"])


def click_input(history: List[dict], events: List[dict], name: str, params: dict, action_text: str) -> dict:
    """The RunAgentInput the page sends after a click: the history, the action as a user turn,
    the current state, and the action itself in forwardedProps for the server's allow-list check."""
    messages = history + messages_from_events(events) + [{"id": "u-action", "role": "user", "content": action_text}]
    return run_input(messages, state=final_state(events), forwarded={"action": {"name": name, "params": params}})


# ---------------------------------------------------------------- transcripts


def print_events(events: List[dict], out=print) -> None:
    """One line per event, with runs of TEXT_MESSAGE_CONTENT / TOOL_CALL_ARGS folded together."""
    i = 0
    while i < len(events):
        e = events[i]
        t = e["type"]
        if t in ("TEXT_MESSAGE_CONTENT", "TOOL_CALL_ARGS"):
            key = "messageId" if t == "TEXT_MESSAGE_CONTENT" else "toolCallId"
            j, parts = i, []
            while j < len(events) and events[j]["type"] == t and events[j][key] == e[key]:
                parts.append(events[j]["delta"])
                j += 1
            out(f"  {t:<21} x{j - i:<3} {short(''.join(parts), 96)}")
            i = j
            continue
        fields = {k: v for k, v in e.items() if k not in ("type", "timestamp")}
        if t == "STATE_SNAPSHOT":
            detail = f"snapshot keys={sorted(fields['snapshot'])}"
        elif t == "STATE_DELTA":
            detail = "; ".join(f"{op['op']} {op['path']}" for op in fields["delta"])
        elif t == "CUSTOM":
            value = fields["value"]
            detail = f"name={fields['name']} value={short(value, 80)}"
        else:
            detail = " ".join(f"{k}={short(v, 60)}" for k, v in fields.items())
        out(f"  {t:<21} {short(detail, 104)}")
        i += 1
