import { apiMutation, apiRequest } from "../../lib/api-client";
import {
  gatewayKeySchema,
  keyCreatedSchema,
  keysSchema,
  overviewSchema,
  requestDetailSchema,
  type GatewayKey,
  type KeyForm,
} from "./schemas";

export const dashboardApi = {
  overview: () => apiRequest("/api/overview", overviewSchema),
  requestDetail: (id: number) => apiRequest(`/api/requests/${id}`, requestDetailSchema),
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
