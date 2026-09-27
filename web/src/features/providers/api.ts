import { apiRequest } from "../../lib/api-client";
import { providerSchema, providersSchema, type ProviderForm } from "./schemas";

export const providersApi = {
  list: () => apiRequest("/api/providers", providersSchema),
  create: (data: ProviderForm & { api_key: string }) =>
    apiRequest("/api/providers", providerSchema, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<ProviderForm>) =>
    apiRequest(`/api/providers/${id}`, providerSchema, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};
