import { z } from "zod";

export const userSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  is_admin: z.boolean(),
  enabled: z.boolean(),
  rpm_limit: z.number().int(),
  token_limit: z.number().int().nullable(),
  created_at: z.string(),
});

export const authSessionSchema = z.object({
  token: z.string(),
  user: userSchema,
});

export const authConfigSchema = z.object({ registration_enabled: z.boolean() });

export const loginFormSchema = z.object({
  email: z.string().trim().email("请输入有效邮箱"),
  password: z.string().min(1, "请输入密码").max(256),
});

export const registerFormSchema = loginFormSchema
  .extend({
    password: z.string().min(8, "密码至少需要 8 个字符").max(256),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ["confirmPassword"],
    message: "两次输入的密码不一致",
  });

export type User = z.infer<typeof userSchema>;
export type AuthSession = z.infer<typeof authSessionSchema>;
export type LoginForm = z.infer<typeof loginFormSchema>;
export type RegisterForm = z.infer<typeof registerFormSchema>;
