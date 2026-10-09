import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class InvalidCodexLog(ValueError):
    pass


@dataclass
class ParsedCodexLog:
    session_id: str
    source: str
    cwd: str | None
    title: str
    started_at: str
    ended_at: str
    event_count: int
    message_count: int
    user_message_count: int
    assistant_message_count: int
    tool_call_count: int
    turn_count: int
    model: str | None
    total_tokens: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    context_tokens: int
    context_window: int
    byte_count: int
    content_hash: str
    transcript: str
    turns: list[dict[str, Any]]


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _clean_user_text(text: str) -> str | None:
    if "## My request:" in text:
        return text.rsplit("## My request:", 1)[1].strip() or None
    if text.lstrip().startswith(
        ("<recommended_plugins>", "<environment_context>", "<in-app-browser-context>")
    ):
        return None
    return text.strip() or None


def _message(record: dict[str, Any]) -> tuple[str, str] | None:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    if record.get("type") == "response_item" and payload.get("type") == "message":
        role = payload.get("role")
        if role not in {"user", "assistant", "developer", "system"}:
            return None
        parts = []
        for item in payload.get("content") or []:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and item.get("type") in {"input_text", "output_text"}:
                parts.append(text)
            elif item.get("type") == "input_image":
                parts.append("[图片输入]")
            elif item.get("type") in {"input_audio", "audio"}:
                parts.append("[音频输入]")
        value = "\n".join(parts).strip()
        if role == "user" and value:
            cleaned = _clean_user_text(value)
            if cleaned is None:
                role = "system"
                value = value[:12_000]
            else:
                value = cleaned
        return (role, value) if value else None
    if record.get("type") == "event_msg":
        event_type = payload.get("type")
        role = {"user_message": "user", "agent_message": "assistant"}.get(event_type)
        text = payload.get("message")
        if role and isinstance(text, str) and text.strip():
            if role == "user":
                value = _clean_user_text(text)
                if value is None:
                    return ("system", text.strip()[:12_000])
            else:
                value = text.strip()
            return (role, value) if value else None
    return None


def _title(messages: list[tuple[str, str]], filename: str) -> str:
    for role, text in messages:
        if role != "user":
            continue
        candidate = _clean_user_text(text)
        if candidate:
            return " ".join(candidate.split())[:160]
    return Path(filename).stem


def parse_codex_log(raw: bytes, filename: str) -> ParsedCodexLog:
    try:
        transcript = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidCodexLog("Codex log must be UTF-8 JSONL") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(transcript.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            # A Codex process can be interrupted while appending an event. Keep
            # the rest of an otherwise valid JSONL session importable.
            continue
        if not isinstance(value, dict):
            raise InvalidCodexLog(f"Line {line_number} must contain a JSON object")
        records.append(value)
    if not records:
        raise InvalidCodexLog("Codex log is empty")

    meta_record = next((item for item in records if item.get("type") == "session_meta"), None)
    if not meta_record or not isinstance(meta_record.get("payload"), dict):
        raise InvalidCodexLog("Missing Codex session_meta record")
    meta = meta_record["payload"]
    session_id = meta.get("id") or meta.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise InvalidCodexLog("Missing Codex session id")

    timestamps = [value for item in records if (value := _timestamp(item.get("timestamp")))]
    meta_timestamp = _timestamp(meta.get("timestamp"))
    if meta_timestamp:
        timestamps.append(meta_timestamp)
    fallback = datetime.fromtimestamp(0, UTC)
    started_at = min(timestamps, default=fallback)
    ended_at = max(timestamps, default=started_at)

    messages = [
        (item["role"], item["text"])
        for item in messages_from_transcript(transcript, limit=100_000)
    ]
    user_message_count = sum(1 for role, _ in messages if role == "user")
    assistant_message_count = sum(1 for role, _ in messages if role == "assistant")
    tool_call_count = 0
    model = None
    for item in records:
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if item.get("type") == "response_item" and payload.get("type") in {
            "function_call",
            "custom_tool_call",
            "local_shell_call",
        }:
            tool_call_count += 1
        if item.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            model = payload["model"]
    title = _title(messages, filename)
    total_tokens = 0
    context_tokens = 0
    context_window = 0
    for item in records:
        payload = item.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        usage = info.get("total_token_usage") if isinstance(info, dict) else None
        if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
            total_tokens = max(total_tokens, usage["total_tokens"])
        last_usage = info.get("last_token_usage") if isinstance(info, dict) else None
        if isinstance(last_usage, dict) and isinstance(last_usage.get("total_tokens"), int):
            context_tokens = last_usage["total_tokens"]
        if isinstance(info, dict) and isinstance(info.get("model_context_window"), int):
            context_window = info["model_context_window"]

    turns = turns_from_records(records)
    input_tokens = sum(turn["input_tokens"] for turn in turns)
    cached_input_tokens = sum(turn["cached_input_tokens"] for turn in turns)
    output_tokens = sum(turn["output_tokens"] for turn in turns)
    reasoning_tokens = sum(turn["reasoning_tokens"] for turn in turns)
    source = meta.get("source") or meta.get("originator") or "codex"
    cwd = meta.get("cwd")
    return ParsedCodexLog(
        session_id=session_id.strip(),
        source=str(source)[:64],
        cwd=str(cwd) if cwd else None,
        title=title,
        started_at=started_at.isoformat(),
        ended_at=ended_at.isoformat(),
        event_count=len(records),
        message_count=len(messages),
        user_message_count=user_message_count,
        assistant_message_count=assistant_message_count,
        tool_call_count=tool_call_count,
        turn_count=len(turns),
        model=model,
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        context_tokens=context_tokens,
        context_window=context_window,
        byte_count=len(raw),
        content_hash=hashlib.sha256(raw).hexdigest(),
        transcript=transcript,
        turns=turns,
    )


def messages_from_transcript(transcript: str, limit: int = 500) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], datetime | None] = {}
    for line in transcript.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not (message := _message(record)):
            continue
        role, text = message
        timestamp = _timestamp(record.get("timestamp"))
        key = (role, text)
        previous = seen.get(key)
        duplicate = key in seen and (
            (previous is None and timestamp is None)
            or (
                previous is not None
                and timestamp is not None
                and abs((timestamp - previous).total_seconds()) <= 10
            )
        )
        if duplicate:
            continue
        seen[key] = timestamp
        messages.append(
            {"role": role, "text": text, "timestamp": timestamp.isoformat() if timestamp else None}
        )
        if len(messages) >= limit:
            break
    return messages


def _preview(value: Any, limit: int = 6000) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return text if len(text) <= limit else f"{text[:limit]}\n…（已截断）"


def _tool_call(payload: dict[str, Any], timestamp: str | None) -> dict[str, Any] | None:
    payload_type = payload.get("type")
    if payload_type not in {"function_call", "custom_tool_call", "local_shell_call"}:
        return None
    call_id = payload.get("call_id") or payload.get("id")
    if not isinstance(call_id, str):
        return None
    name = payload.get("name")
    if not isinstance(name, str):
        name = "shell" if payload_type == "local_shell_call" else "tool"
    namespace = payload.get("namespace")
    if isinstance(namespace, str) and namespace and namespace != "functions":
        name = f"{namespace}.{name}"
    return {
        "kind": "tool",
        "call_id": call_id,
        "name": name,
        "input": _preview(payload.get("arguments", payload.get("input", payload.get("command")))),
        "output": None,
        "status": payload.get("status") if isinstance(payload.get("status"), str) else None,
        "timestamp": timestamp,
    }


def turns_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build user-visible turns without storing repeated full model context snapshots."""
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    calls: dict[str, dict[str, Any]] = {}
    seen_messages: dict[tuple[str, str], datetime | None] = {}
    pending_user_message: dict[str, Any] | None = None

    def begin(turn_id: str, timestamp: str | None) -> dict[str, Any]:
        turn = {
            "turn_id": turn_id,
            "sequence": len(turns) + 1,
            "started_at": timestamp,
            "ended_at": None,
            "model": None,
            "effort": None,
            "status": "running",
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "context_window": 0,
            "context": None,
            "events": [],
        }
        turns.append(turn)
        return turn

    def append_message(turn: dict[str, Any], event: dict[str, Any]) -> None:
        key = (str(event.get("role")), str(event.get("text")))
        event_timestamp = _timestamp(event.get("timestamp"))
        previous = seen_messages.get(key)
        duplicate = key in seen_messages and (
            (previous is None and event_timestamp is None)
            or (
                previous is not None
                and event_timestamp is not None
                and abs((event_timestamp - previous).total_seconds()) <= 10
            )
        )
        # The runtime can emit the same message through response_item and
        # event_msg with other events in between. De-duplicate across the
        # event stream while preserving an intentionally repeated prompt.
        if not duplicate:
            turn["events"].append(event)
            seen_messages[key] = event_timestamp

    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        timestamp_value = _timestamp(record.get("timestamp"))
        timestamp = timestamp_value.isoformat() if timestamp_value else None
        record_type = record.get("type")
        event_type = payload.get("type")

        if record_type == "event_msg" and event_type == "task_started":
            turn_id = payload.get("turn_id")
            if isinstance(turn_id, str):
                current = begin(turn_id, timestamp)
                calls = {}
                seen_messages = {}
                if pending_user_message is not None:
                    append_message(current, pending_user_message)
                    pending_user_message = None
            continue
        if record_type == "turn_context":
            turn_id = payload.get("turn_id")
            if isinstance(turn_id, str) and (
                current is None or current.get("turn_id") != turn_id
            ):
                current = begin(turn_id, timestamp)
                calls = {}
                seen_messages = {}
                if pending_user_message is not None:
                    append_message(current, pending_user_message)
                    pending_user_message = None
            if current is not None:
                if isinstance(payload.get("model"), str):
                    current["model"] = payload["model"]
                if isinstance(payload.get("effort"), str):
                    current["effort"] = payload["effort"]
                sandbox = payload.get("sandbox_policy")
                permission = payload.get("active_permission_profile") or payload.get(
                    "permission_profile"
                )
                collaboration = payload.get("collaboration_mode")
                roots = payload.get("workspace_roots")
                current["context"] = {
                    "cwd": payload.get("cwd") if isinstance(payload.get("cwd"), str) else None,
                    "workspace_roots": (
                        [str(item) for item in roots] if isinstance(roots, list) else []
                    ),
                    "current_date": payload.get("current_date"),
                    "timezone": payload.get("timezone"),
                    "approval_policy": payload.get("approval_policy"),
                    "approvals_reviewer": payload.get("approvals_reviewer"),
                    "sandbox": sandbox.get("type") if isinstance(sandbox, dict) else sandbox,
                    "permission_profile": (
                        permission.get("type") if isinstance(permission, dict) else permission
                    ),
                    "personality": payload.get("personality"),
                    "collaboration_mode": (
                        collaboration.get("mode")
                        if isinstance(collaboration, dict)
                        else collaboration
                    ),
                    "realtime_active": payload.get("realtime_active"),
                    "summary": _preview(payload.get("summary"), limit=12_000),
                }
            continue
        message = _message(record)
        if current is None:
            # Older runtimes may write the actual prompt immediately before
            # task_started. Metadata injected through a user-shaped envelope
            # is normalized to system above and deliberately not queued.
            if message and message[0] == "user":
                role, text = message
                pending_user_message = {
                    "kind": "message",
                    "role": role,
                    "text": text,
                    "timestamp": timestamp,
                }
            continue

        if record_type == "event_msg" and event_type == "task_complete":
            current["ended_at"] = timestamp
            current["status"] = "completed"
            continue

        if message:
            role, text = message
            append_message(
                current,
                {"kind": "message", "role": role, "text": text, "timestamp": timestamp},
            )
            continue

        if record_type == "response_item":
            call = _tool_call(payload, timestamp)
            if call:
                current["events"].append(call)
                calls[call["call_id"]] = call
                continue
            if event_type in {
                "function_call_output",
                "custom_tool_call_output",
                "local_shell_call_output",
            }:
                call_id = payload.get("call_id") or payload.get("id")
                if isinstance(call_id, str) and call_id in calls:
                    calls[call_id]["output"] = _preview(payload.get("output"))
                    if isinstance(payload.get("status"), str):
                        calls[call_id]["status"] = payload["status"]
                continue

        if record_type == "event_msg" and event_type == "token_count":
            info = payload.get("info")
            usage = info.get("last_token_usage") if isinstance(info, dict) else None
            if isinstance(usage, dict):
                current["input_tokens"] = int(usage.get("input_tokens") or 0)
                current["cached_input_tokens"] = int(usage.get("cached_input_tokens") or 0)
                current["output_tokens"] = int(usage.get("output_tokens") or 0)
                current["reasoning_tokens"] = int(usage.get("reasoning_output_tokens") or 0)
                current["total_tokens"] = int(usage.get("total_tokens") or 0)
            if isinstance(info, dict) and isinstance(info.get("model_context_window"), int):
                current["context_window"] = info["model_context_window"]

    for turn in turns:
        events = turn["events"]
        turn["message_count"] = sum(event["kind"] == "message" for event in events)
        turn["tool_call_count"] = sum(event["kind"] == "tool" for event in events)
        if turn["ended_at"] is None:
            turn["ended_at"] = turn["started_at"]
            turn["status"] = "interrupted"
    return turns


def tool_calls_from_transcript(transcript: str, limit: int = 500) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for line in transcript.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get("payload") if isinstance(record, dict) else None
        if record.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        call_id = payload.get("call_id") or payload.get("id")
        if not isinstance(call_id, str):
            continue
        if payload_type in {"function_call", "custom_tool_call", "local_shell_call"}:
            name = payload.get("name")
            if not isinstance(name, str):
                name = "shell" if payload_type == "local_shell_call" else "tool"
            namespace = payload.get("namespace")
            if isinstance(namespace, str) and namespace and namespace != "functions":
                name = f"{namespace}.{name}"
            arguments = payload.get("arguments", payload.get("input", payload.get("command")))
            timestamp = _timestamp(record.get("timestamp"))
            call = {
                "call_id": call_id,
                "name": name,
                "input": _preview(arguments),
                "output": None,
                "status": payload.get("status") if isinstance(payload.get("status"), str) else None,
                "timestamp": timestamp.isoformat() if timestamp else None,
            }
            calls.append(call)
            by_id[call_id] = call
            if len(calls) >= limit:
                break
        elif payload_type in {
            "function_call_output",
            "custom_tool_call_output",
            "local_shell_call_output",
        }:
            call = by_id.get(call_id)
            if call:
                call["output"] = _preview(payload.get("output"))
                if isinstance(payload.get("status"), str):
                    call["status"] = payload["status"]
    return calls


def context_from_transcript(transcript: str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for line in transcript.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get("payload") if isinstance(record, dict) else None
        if record.get("type") == "turn_context" and isinstance(payload, dict):
            latest = payload
    if latest is None:
        return None
    sandbox = latest.get("sandbox_policy")
    sandbox_name = sandbox.get("type") if isinstance(sandbox, dict) else sandbox
    roots = latest.get("workspace_roots")
    return {
        "model": latest.get("model") if isinstance(latest.get("model"), str) else None,
        "effort": latest.get("effort") if isinstance(latest.get("effort"), str) else None,
        "cwd": latest.get("cwd") if isinstance(latest.get("cwd"), str) else None,
        "approval_policy": latest.get("approval_policy")
        if isinstance(latest.get("approval_policy"), str)
        else None,
        "sandbox": sandbox_name if isinstance(sandbox_name, str) else None,
        "workspace_roots": [str(item) for item in roots] if isinstance(roots, list) else [],
        "summary": _preview(latest.get("summary"), limit=12_000),
    }
