import { z } from "zod";

export const providerProtocolSchema = z.enum(["openai", "anthropic"]);
export const providerModelSchema = z.object({ id: z.string(), name: z.string() });

export const providerSchema = z.object({
  id: z.string(),
  name: z.string(),
  protocol: providerProtocolSchema,
  base_url: z.string().url(),
  enabled: z.boolean(),
  created_at: z.string(),
  key_hint: z.string(),
  models: z.array(providerModelSchema),
});

export const providersSchema = z.array(providerSchema);

export const providerFormSchema = z.object({
  name: z.string().trim().min(1, "请输入名称").max(64),
  protocol: providerProtocolSchema,
  base_url: z.string().trim().url("请输入完整的 API 地址"),
  api_key: z.string().trim().optional(),
  models: z.array(z.string().trim().min(1).max(128)).min(1, "至少配置一个模型"),
  enabled: z.boolean(),
});

export type Provider = z.infer<typeof providerSchema>;
export type ProviderForm = z.infer<typeof providerFormSchema>;
