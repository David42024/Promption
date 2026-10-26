import { createPromption, createFilterApiTransport, createScopeEvaluator, createContextEvaluator, resolveProtection,
  type IntentAssessment } from '../src/index.js';
import { wrapLanguageModel, generateText, streamText, tool, jsonSchema } from 'ai';

declare const baseModel: Parameters<typeof wrapLanguageModel>[0]['model'];
const identity = { userId: 'server-user', roles: ['customer'], authenticated: true };
const protection = createPromption({ baseUrl: 'http://localhost:8000', apiKey: 'server-only' });
const balanced = resolveProtection({ profile: 'balanced', scopeAmbiguity: 'clarify', inputUncertainty: 'review' });
void createPromption({ transport: async ({ text }) => ({ allowed: true, text }), protection: balanced,
  onDecision: event => { const profile: string = event.protection.profile; return profile; } });
// @ts-expect-error the participant cannot change the profile in a middleware request
protection.middleware({ identity, protection: 'conversational' });
const model = wrapLanguageModel({ model: baseModel, middleware: protection.middleware({ identity, toolPolicies: { catalog: {} } }) });
void generateText({ model, prompt: 'Hola' });
void streamText({ model, prompt: 'Hola' });
const catalog = tool({ inputSchema: jsonSchema<{ query: string }>({ type: 'object' }), execute: async input => input.query });
const protectedCatalog = protection.protectTool(catalog, { name: 'catalog', identity, policy: {} });
void generateText({ model, prompt: 'Consulta', tools: { catalog: protectedCatalog } });
void createFilterApiTransport({ baseUrl: 'http://localhost:8000', apiKey: 'server-only' });
const scoped = createPromption({ baseUrl: 'http://localhost:8000', apiKey: 'server-only',
  scopeEvaluator: createScopeEvaluator({ model: baseModel }) });
void generateText({ model: wrapLanguageModel({ model: baseModel, middleware: scoped.middleware({ identity }) }),
  system: 'Only answer shop questions', prompt: 'What products are available?' });
void scoped.checkScope('Question', { identity, systemPrompt: 'Only answer shop questions' });
const contextual = createPromption({ baseUrl: 'http://localhost:8000', apiKey: 'server-only',
  scopeEvaluator: createContextEvaluator({ model: baseModel, minimumConfidence: .8 }) });
void contextual.checkScope('Export it', { identity, systemPrompt: 'Only public shop documents',
  messages: [{ role: 'user', content: 'Public catalog' }] }).then(result => {
    const intent: IntentAssessment | undefined = result.intent;
    return intent?.relation;
  });
import { withScopeReceipts, issueScopeReceipt, verifyScopeReceipt } from '../src/scope-receipts.js';
const receiptRequest = { text: 'Catalog', systemPrompt: 'Shop only', identity: { userId: 'u', roles: ['customer'], authenticated: true } };
const receiptBinding = { request_id: 'r', tenant_id: 't', conversation_id: 'c' };
const signedReceipt = issueScopeReceipt(receiptRequest, receiptBinding, 'model', 'synthetic-key');
verifyScopeReceipt(signedReceipt, receiptRequest, receiptBinding, 'model', 'synthetic-key');
withScopeReceipts(async () => ({ classification: 'IN_SCOPE', reason: 'in_scope' }),
  { receipts: [signedReceipt], binding: receiptBinding, model: 'model', secret: 'synthetic-key', requestId: 'r' });
