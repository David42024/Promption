import { createPromption, createGuardEndpointTransport, createScopeEvaluator } from "@promption/ai-sdk";

const CHAT_API_URL = (process.env.CHAT_API_URL || process.env.NEXT_PUBLIC_CHAT_API_URL || "").replace(/\/$/, "");

const toolPolicies = {
  make_document: {}, getBrandInfo: {}, getShippingPolicy: {}, getCatalogSummary: {},
  getPromotions: { roles: ["ventas", "admin"] },
  getStockInfo: { roles: ["ventas", "admin"] },
  getMarketingCampaigns: { roles: ["ventas", "admin"] },
  getEmployees: { roles: ["admin"] }, getVIPClients: { roles: ["admin"] },
  getKPIStats: { roles: ["admin"] }, getRevenueReport: { roles: ["admin"] },
  getTopProducts: { roles: ["admin"] },
  ask_user: {}, attach_existing_document: {},
  web_search: { roles: ["ventas", "admin"] }, web_open: { roles: ["ventas", "admin"] },
};

function promption(scopeModel, scopeProviderOptions) {
  const evaluateScope = scopeModel ? createScopeEvaluator({ model: scopeModel, providerOptions: scopeProviderOptions }) : null;
  return createPromption({
    transport: createGuardEndpointTransport({
      url: `${CHAT_API_URL}/api/v1/ai/guard`, token: process.env.CHAT_SERVICE_TOKEN,
      timeoutMs: 60000,
    }),
    ...(evaluateScope ? { scopeEvaluator: async request => {
      try { return await evaluateScope(request); }
      catch (error) {
        console.error('[ai/turn] scope evaluation failed', {
          name: typeof error?.name === 'string' ? error.name : 'UnknownError',
          code: typeof error?.code === 'string' ? error.code.slice(0, 80) : undefined,
          statusCode: Number.isInteger(error?.statusCode) ? error.statusCode : undefined,
          causeName: typeof error?.cause?.name === 'string' ? error.cause.name : undefined,
        });
        throw error;
      }
    } } : {}),
  });
}

export function promptionMiddleware(identity, originalText, signal, securityMessages, scopeModel, scopeProviderOptions) {
  return promption(scopeModel, scopeProviderOptions).middleware({ identity, originalText, signal, securityMessages, toolPolicies });
}

export function checkPromption(text, identity, direction, signal) {
  return promption().check(text, { identity, direction, signal });
}
