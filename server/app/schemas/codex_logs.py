from datetime import datetime

from pydantic import BaseModel


class CodexSessionView(BaseModel):
    session_id: str
    source: str
    cwd: str | None
    title: str
    started_at: datetime
    ended_at: datetime
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
    imported_at: datetime
    deleted_at: datetime | None


class CodexSessionRename(BaseModel):
    title: str | None = None


class CodexMessageView(BaseModel):
    role: str
    text: str
    timestamp: datetime | None


class CodexToolCallView(BaseModel):
    call_id: str
    name: str
    input: str | None
    output: str | None
    status: str | None
    timestamp: datetime | None


class CodexContextView(BaseModel):
    model: str | None
    effort: str | None
    cwd: str | None
    approval_policy: str | None
    sandbox: str | None
    workspace_roots: list[str]
    summary: str | None
    summary_mode: str | None = None
    base_instructions: str | None = None


class CodexTurnEventView(BaseModel):
    kind: str
    timestamp: datetime | None
    role: str | None = None
    text: str | None = None
    call_id: str | None = None
    name: str | None = None
    input: str | None = None
    output: str | None = None
    status: str | None = None


class CodexTurnContextView(BaseModel):
    cwd: str | None = None
    workspace_roots: list[str] = []
    current_date: str | None = None
    timezone: str | None = None
    approval_policy: str | None = None
    approvals_reviewer: str | None = None
    sandbox: str | None = None
    permission_profile: str | None = None
    personality: str | None = None
    collaboration_mode: str | None = None
    realtime_active: bool | None = None
    summary: str | None = None
    summary_mode: str | None = None


class CodexTurnView(BaseModel):
    turn_id: str
    sequence: int
    started_at: datetime | None
    ended_at: datetime | None
    model: str | None
    effort: str | None
    status: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    context_window: int
    message_count: int
    tool_call_count: int
    context: CodexTurnContextView | None
    events: list[CodexTurnEventView]


class CodexSessionDetail(CodexSessionView):
    messages: list[CodexMessageView]
    tool_calls: list[CodexToolCallView]
    context: CodexContextView | None
    turns: list[CodexTurnView]


class CodexImportResult(BaseModel):
    status: str
    session: CodexSessionView


class CodexUploadTokenView(BaseModel):
    prefix: str
    created_at: datetime
    last_used_at: datetime | None


class CodexUploadTokenCreated(CodexUploadTokenView):
    token: str
