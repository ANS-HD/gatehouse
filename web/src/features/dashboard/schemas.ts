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

export const keyFormSchema = z.object({
  name: z.string().trim().min(1, "请输入名称").max(64, "最多 64 个字符"),
  provider_id: z.string().min(1, "请选择上游供应商"),
  model_id: z.string().min(1, "请选择模型"),
});

export type GatewayKey = z.infer<typeof gatewayKeySchema>;
export type KeyCreated = z.infer<typeof keyCreatedSchema>;
export type Overview = z.infer<typeof overviewSchema>;
export type RequestDetail = z.infer<typeof requestDetailSchema>;
export type KeyForm = z.infer<typeof keyFormSchema>;
