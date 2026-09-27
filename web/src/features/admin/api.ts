import { apiRequest } from "../../lib/api-client";
import { adminUserSchema, adminUsersSchema, type AdminUserForm } from "./schemas";

export const adminApi = {
  users: () => apiRequest("/api/admin/users", adminUsersSchema),
  createUser: (data: AdminUserForm & { password: string }) =>
    apiRequest("/api/admin/users", adminUserSchema, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateUser: (id: string, data: Omit<AdminUserForm, "email">) =>
    apiRequest(`/api/admin/users/${id}`, adminUserSchema, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};
