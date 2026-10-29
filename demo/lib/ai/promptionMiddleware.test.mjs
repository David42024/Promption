import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { generateText, wrapLanguageModel } from 'ai';
import { promptionMiddleware } from './promptionMiddleware.js';

const require = createRequire(import.meta.url);
const library = require('@promption/ai-sdk');

test('Shop uses current context/intent evaluator and guards both boundaries', async () => {
  const originalFetch = globalThis.fetch;
  const previousToken = process.env.CHAT_SERVICE_TOKEN;
  process.env.CHAT_SERVICE_TOKEN = 'local-integration-fixture';
  const directions = [];
  let evaluated = false;
  let observedIntent;
  const result = text => ({ content: [{ type: 'text', text }], finishReason: { unified: 'stop', raw: 'stop' }, usage: { inputTokens: { total: 12 }, outputTokens: { total: 4 } }, warnings: [] });
  const base = { specificationVersion: 'v3', provider: 'fixture', modelId: 'fixture', supportedUrls: {} };
  try {
    globalThis.fetch = async (url, options) => {
      assert.match(String(url), /\/api\/v1\/ai\/guard$/);
      const request = JSON.parse(options.body);
      directions.push(request.direction);
      return Response.json({ allowed: true, text: request.text, action: 'GUARDED', conversation_checked: true,
        requires_scope_review: request.direction === 'input', requires_output_guard: true });
    };
    const scopeModel = { ...base, async doGenerate(request) {
      evaluated = true;
      assert.match(JSON.stringify(request.prompt), /CURRENT_REQUEST/);
      return result(JSON.stringify({ decision: 'in_scope', intent: { name: 'public_information', attack: 'none',
        relation: 'standalone', origin: 'none', confidence: 1, evidence: [] } }));
    } };
    const model = wrapLanguageModel({ model: { ...base, async doGenerate() { return result('Aurora cuesta S/80.'); } },
      middleware: promptionMiddleware({ userId: 'fixture-user', roles: ['customer'], authenticated: true },
        'Precio de Aurora', undefined, [], scopeModel, undefined, { systemPrompt: 'Public catalog questions are allowed.', onScope: decision => { observedIntent = decision.intent; } }) });
    const response = await generateText({ model, system: 'Public catalog questions are allowed.', prompt: 'Precio de Aurora' });
    assert.equal(response.text, 'Aurora cuesta S/80.');
    assert.equal(evaluated, true);
    assert.equal(observedIntent?.name, 'public_information');
    assert.ok(directions.includes('input'));
    assert.ok(directions.includes('output'));
    assert.equal(typeof library.createContextEvaluator, 'function');
  } finally {
    globalThis.fetch = originalFetch;
    if (previousToken === undefined) delete process.env.CHAT_SERVICE_TOKEN; else process.env.CHAT_SERVICE_TOKEN = previousToken;
  }
});
