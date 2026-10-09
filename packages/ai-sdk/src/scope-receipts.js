import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}

function toolInput(value) {
  if (typeof value === 'string') { try { return JSON.parse(value); } catch {} }
  return value;
}

function fingerprint(request, binding, model) {
  const snapshot = {
    version: 1, model, binding,
    text: request.text, policy: request.systemPrompt,
    identity: { userId: request.identity.userId, roles: [...request.identity.roles].sort(),
      authenticated: request.identity.authenticated === true },
    messages: (request.messages ?? []).map(message => ({ role: message.role,
      content: message.content, ...(message.tool_name ? { tool_name: message.tool_name } : {}) })),
    tool: request.tool ? { name: request.tool.name, input: toolInput(request.tool.input),
      description: request.tool.description ?? '' } : null,
  };
  return createHash('sha256').update(JSON.stringify(canonical(snapshot))).digest('hex');
}

function validBinding(binding) {
  return binding && typeof binding.request_id === 'string' && binding.request_id.length > 0
    && binding.request_id.length <= 200 && typeof binding.tenant_id === 'string' && binding.tenant_id.length <= 256
    && typeof binding.conversation_id === 'string' && binding.conversation_id.length <= 256;
}

export function issueScopeReceipt(request, binding, model, secret, now = Date.now()) {
  if (!secret || !validBinding(binding)) return null;
  const body = Buffer.from(JSON.stringify({ hash: fingerprint(request, binding, model),
    expires: now + 120000 })).toString('base64url');
  return `${body}.${createHmac('sha256', secret).update(body).digest('base64url')}`;
}

export function verifyScopeReceipt(receipt, request, binding, model, secret, now = Date.now()) {
  if (!secret || !validBinding(binding) || typeof receipt !== 'string' || receipt.length > 4096) return false;
  try {
    const pieces = receipt.split('.');
    if (pieces.length !== 2) return false;
    const [body, signature] = pieces;
    const actual = Buffer.from(signature, 'base64url');
    const expected = createHmac('sha256', secret).update(body).digest();
    if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) return false;
    const data = JSON.parse(Buffer.from(body, 'base64url').toString());
    return Number.isSafeInteger(data.expires) && data.expires > now && data.expires <= now + 120000
      && data.hash === fingerprint(request, binding, model);
  } catch { return false; }
}

export function withScopeReceipts(evaluate, { receipts = [], binding, model, secret, requestId, onReceipt }) {
  return async request => {
    const candidates = Array.isArray(receipts) ? receipts.slice(0, 32) : [];
    if (binding?.request_id === requestId && candidates.some(receipt =>
      verifyScopeReceipt(receipt, request, binding, model, secret))) {
      return { classification: 'IN_SCOPE', reason: 'in_scope', allowed: true, status: 200,
        provider_calls: 0, usage: null, model, reused: true };
    }
    const decision = await evaluate(request);
    if (decision.classification === 'IN_SCOPE' && decision.reason === 'in_scope' && binding?.request_id === requestId) {
      const receipt = issueScopeReceipt(request, binding, model, secret);
      if (receipt && typeof onReceipt === 'function') onReceipt(receipt);
    }
    return decision;
  };
}
