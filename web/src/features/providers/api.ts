import { apiRequest } from "../../lib/api-client";
import { discoveredModelsSchema, providerSchema, providersSchema, type ModelDiscoveryInput, type ProviderForm } from "./schemas";

export const providersApi = {
  list: () => apiRequest("/api/providers", providersSchema),
  discoverModels: (data: ModelDiscoveryInput) =>
    apiRequest("/api/providers/discover-models", discoveredModelsSchema, {
      method: "POST",
      body: JSON.stringify(data),
    }),
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
