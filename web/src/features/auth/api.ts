import { apiRequest } from "../../lib/api-client";
import { authConfigSchema, authSessionSchema, userSchema, type LoginForm, type RegisterForm } from "./schemas";

export const authApi = {
  config: () => apiRequest("/api/auth/config", authConfigSchema),
  me: () => apiRequest("/api/auth/me", userSchema),
  login: (data: LoginForm) =>
    apiRequest("/api/auth/login", authSessionSchema, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  register: ({ confirmPassword: _, ...data }: RegisterForm) =>
    apiRequest("/api/auth/register", authSessionSchema, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
