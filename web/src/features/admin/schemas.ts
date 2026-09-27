import { z } from "zod";
import { userSchema } from "../auth/schemas";

export const adminUserSchema = userSchema.extend({
  allowed_model_ids: z.array(z.string()),
  active_keys: z.number().int(),
  total_tokens: z.number().int(),
  requests_count: z.number().int(),
});

export const adminUsersSchema = z.array(adminUserSchema);

export const adminUserFormSchema = z.object({
  email: z.string().trim().email("请输入有效邮箱"),
  password: z.string().max(256).optional(),
  enabled: z.boolean(),
  rpm_limit: z.number().int().min(1).max(10_000),
  token_limit: z.number().int().positive().nullable(),
  model_ids: z.array(z.string()),
});

export const adminUserCreateSchema = adminUserFormSchema.extend({
  password: z.string().min(8, "密码至少需要 8 个字符").max(256),
});

export type AdminUser = z.infer<typeof adminUserSchema>;
export type AdminUserForm = z.infer<typeof adminUserFormSchema>;
