import { apiMutation, apiRequest } from "../../lib/api-client";
import {
  gatewayKeySchema,
  keyCreatedSchema,
  keysSchema,
  overviewSchema,
  requestDetailSchema,
  codexImportResultSchema,
  codexSessionSchema,
  codexSessionDetailSchema,
  codexSessionsSchema,
  type GatewayKey,
  type KeyForm,
} from "./schemas";

export const dashboardApi = {
  overview: () => apiRequest("/api/overview", overviewSchema),
  requestDetail: (id: number) => apiRequest(`/api/requests/${id}`, requestDetailSchema),
  codexSessions: (q?: string, project?: string, deleted = false) => {
    const params = new URLSearchParams();
    if (q?.trim()) params.set("q", q.trim());
    if (project) params.set("project", project);
    if (deleted) params.set("deleted", "true");
    const suffix = params.size ? `?${params}` : "";
    return apiRequest(`/api/codex/sessions${suffix}`, codexSessionsSchema);
  },
  codexSessionDetail: (id: string) =>
    apiRequest(`/api/codex/sessions/${encodeURIComponent(id)}`, codexSessionDetailSchema),
  importCodexSession: (file: File) =>
    apiRequest(
      `/api/codex/sessions/import?filename=${encodeURIComponent(file.name)}`,
      codexImportResultSchema,
      { method: "POST", headers: { "Content-Type": "application/x-ndjson" }, body: file },
    ),
  deleteCodexSession: (id: string) =>
    apiMutation(`/api/codex/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreCodexSession: (id: string) =>
    apiMutation(`/api/codex/sessions/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  renameCodexSession: (id: string, title: string | null) =>
    apiRequest(`/api/codex/sessions/${encodeURIComponent(id)}`, codexSessionSchema, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  keys: () => apiRequest("/api/keys", keysSchema),
  createKey: (data: KeyForm) =>
    apiRequest("/api/keys", keyCreatedSchema, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateKey: (
    id: string,
    data: Partial<Pick<GatewayKey, "enabled">>,
  ) =>
    apiRequest(`/api/keys/${id}`, gatewayKeySchema, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  revokeKey: (id: string) => apiMutation(`/api/keys/${id}`, { method: "DELETE" }),
};
