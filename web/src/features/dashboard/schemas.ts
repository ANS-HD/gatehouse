import { z } from "zod";

export const gatewayKeySchema = z.object({
  id: z.string(),
  name: z.string(),
  provider_id: z.string(),
  provider_name: z.string(),
  model_id: z.string().nullable(),
  model_name: z.string().nullable(),
  prefix: z.string(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  rpm: z.number().int(),
  token_limit: z.number().int().nullable(),
  tokens_used: z.number().int(),
  account_tokens_used: z.number().int(),
  enabled: z.boolean(),
});

export const keyCreatedSchema = gatewayKeySchema.extend({ key: z.string() });
export const keysSchema = z.array(gatewayKeySchema);

export const overviewSchema = z.object({
  summary: z.object({
    active_keys: z.number().int(),
    requests_24h: z.number().int(),
    tokens_24h: z.number().int(),
    errors_24h: z.number().int(),
  }),
  recent: z.array(
    z.object({
      id: z.number().int(),
      key_name: z.string(),
      provider_name: z.string(),
      endpoint: z.string(),
      model: z.string().nullable(),
      status_code: z.number().int(),
      total_tokens: z.number().int(),
      latency_ms: z.number().int(),
      error: z.string().nullable(),
      created_at: z.string(),
    }),
  ),
  daily: z.array(
    z.object({
      date: z.string(),
      requests: z.number().int(),
      tokens: z.number().int(),
    }),
  ),
});

export const requestDetailSchema = z.object({
  id: z.number().int(),
  key_name: z.string(),
  provider_name: z.string(),
  method: z.string(),
  endpoint: z.string(),
  query_string: z.string().nullable(),
  model: z.string().nullable(),
  status_code: z.number().int(),
  input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  total_tokens: z.number().int(),
  latency_ms: z.number().int(),
  error: z.string().nullable(),
  created_at: z.string(),
  request_headers: z.string().nullable(),
  request_body: z.string().nullable(),
  response_headers: z.string().nullable(),
  response_body: z.string().nullable(),
  detail_truncated: z.boolean(),
});

export const codexSessionSchema = z.object({
  session_id: z.string(),
  source: z.string(),
  cwd: z.string().nullable(),
  title: z.string(),
  started_at: z.string(),
  ended_at: z.string(),
  event_count: z.number().int(),
  message_count: z.number().int(),
  user_message_count: z.number().int(),
  assistant_message_count: z.number().int(),
  tool_call_count: z.number().int(),
  turn_count: z.number().int(),
  model: z.string().nullable(),
  total_tokens: z.number().int(),
  input_tokens: z.number().int(),
  cached_input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  reasoning_tokens: z.number().int(),
  context_tokens: z.number().int(),
  context_window: z.number().int(),
  byte_count: z.number().int(),
  imported_at: z.string(),
  deleted_at: z.string().nullable(),
});

export const codexSessionsSchema = z.array(codexSessionSchema);
export const codexSessionDetailSchema = codexSessionSchema.extend({
  messages: z.array(z.object({
    role: z.string(),
    text: z.string(),
    timestamp: z.string().nullable(),
  })),
  tool_calls: z.array(z.object({
    call_id: z.string(),
    name: z.string(),
    input: z.string().nullable(),
    output: z.string().nullable(),
    status: z.string().nullable(),
    timestamp: z.string().nullable(),
  })),
  context: z.object({
    model: z.string().nullable(),
    effort: z.string().nullable(),
    cwd: z.string().nullable(),
    approval_policy: z.string().nullable(),
    sandbox: z.string().nullable(),
    workspace_roots: z.array(z.string()),
    summary: z.string().nullable(),
    summary_mode: z.string().nullable().optional(),
    base_instructions: z.string().nullable().optional(),
  }).nullable(),
  turns: z.array(z.object({
    turn_id: z.string(),
    sequence: z.number().int(),
    started_at: z.string().nullable(),
    ended_at: z.string().nullable(),
    model: z.string().nullable(),
    effort: z.string().nullable(),
    status: z.string(),
    input_tokens: z.number().int(),
    cached_input_tokens: z.number().int(),
    output_tokens: z.number().int(),
    reasoning_tokens: z.number().int(),
    total_tokens: z.number().int(),
    context_window: z.number().int(),
    message_count: z.number().int(),
    tool_call_count: z.number().int(),
    context: z.object({
      cwd: z.string().nullable(),
      workspace_roots: z.array(z.string()),
      current_date: z.string().nullable(),
      timezone: z.string().nullable(),
      approval_policy: z.string().nullable(),
      approvals_reviewer: z.string().nullable(),
      sandbox: z.string().nullable(),
      permission_profile: z.string().nullable(),
      personality: z.string().nullable(),
      collaboration_mode: z.string().nullable(),
      realtime_active: z.boolean().nullable(),
      summary: z.string().nullable(),
      summary_mode: z.string().nullable().optional(),
    }).nullable(),
    events: z.array(z.object({
      kind: z.string(),
      timestamp: z.string().nullable(),
      role: z.string().nullable().optional(),
      text: z.string().nullable().optional(),
      call_id: z.string().nullable().optional(),
      name: z.string().nullable().optional(),
      input: z.string().nullable().optional(),
      output: z.string().nullable().optional(),
      status: z.string().nullable().optional(),
    })),
  })),
});

export const codexImportResultSchema = z.object({
  status: z.enum(["created", "updated", "unchanged"]),
  session: codexSessionSchema,
});

export const keyFormSchema = z.object({
  name: z.string().trim().min(1, "请输入名称").max(64, "最多 64 个字符"),
  provider_id: z.string().min(1, "请选择上游供应商"),
  model_id: z.string().min(1, "请选择模型"),
});

export type GatewayKey = z.infer<typeof gatewayKeySchema>;
export type KeyCreated = z.infer<typeof keyCreatedSchema>;
export type Overview = z.infer<typeof overviewSchema>;
export type RequestDetail = z.infer<typeof requestDetailSchema>;
export type CodexSession = z.infer<typeof codexSessionSchema>;
export type CodexSessionDetail = z.infer<typeof codexSessionDetailSchema>;
export type KeyForm = z.infer<typeof keyFormSchema>;
