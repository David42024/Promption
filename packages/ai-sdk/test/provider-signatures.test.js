import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateText, jsonSchema, tool, stepCountIs, wrapLanguageModel } from 'ai';
import { MockLanguageModelV3 } from 'ai/test';
import { createPromption } from '../src/index.js';
import { createToolSignatureStore } from '../src/provider-signatures.js';

const signature = 'opaqueSignedState'.repeat(8);
const call = { type: 'tool-call', toolCallId: 'call-1', toolName: 'catalog', input: '{"query":"lamp"}',
  providerMetadata: { google: { thoughtSignature: signature }, other: { private: 'hidden' } } };
const prompt = part => [{ role: 'assistant', content: [part] }];
const part = { type: 'tool-call', toolCallId: 'call-1', toolName: 'catalog', input: { query: 'lamp' } };

test('server-owned signatures bind the exact call and never accept caller-supplied signatures', () => {
  const store = createToolSignatureStore();
  store.remember(call);
  assert.equal(store.restore(prompt(part), () => true)[0].content[0].providerOptions.google.thoughtSignature, signature);
  for (const changed of [{ input: { query: 'secret' } }, { toolCallId: 'forged' }, { toolName: 'admin' }]) {
    const forged = { ...part, ...changed, providerOptions: { google: { thoughtSignature: signature } } };
    assert.equal(store.restore(prompt(forged), () => true)[0].content[0].providerOptions.google.thoughtSignature, undefined);
  }
  assert.equal(store.restore(prompt({ ...part, providerOptions: { google: { thoughtSignature: signature } } }),
    () => false)[0].content[0].providerOptions.google.thoughtSignature, undefined);
  assert.equal(createToolSignatureStore().restore(prompt(part), () => true)[0].content[0].providerOptions, undefined);
});

test('signature state is bounded and rejects oversized or malformed metadata', () => {
  const store = createToolSignatureStore();
  for (let i = 0; i < 33; i++) store.remember({ ...call, toolCallId: 'call-' + i });
  assert.equal(store.restore(prompt({ ...part, toolCallId: 'call-0' }), () => true)[0].content[0].providerOptions, undefined);
  for (const invalid of ['x'.repeat(65537), 'invalid\nvalue', '', { nested: 'signature' }]) {
    const isolated = createToolSignatureStore();
    isolated.remember({ ...call, providerMetadata: { google: { thoughtSignature: invalid } } });
    assert.equal(isolated.restore(prompt(part), () => true)[0].content[0].providerOptions, undefined);
  }
});

test('generateText tool loop restores signatures only inside the provider request', async () => {
  const usage = { inputTokens: { total: 1 }, outputTokens: { total: 1 } };
  const provider = new MockLanguageModelV3({ doGenerate: [
    { content: [call], usage, warnings: [], finishReason: { unified: 'tool-calls', raw: 'tool-calls' } },
    { content: [{ type: 'text', text: 'Public lamp available.' }], usage, warnings: [], finishReason: { unified: 'stop', raw: 'stop' } },
  ] });
  const protection = createPromption({ transport: async ({ text }) => ({ allowed: true, text }) });
  const model = wrapLanguageModel({ model: provider, middleware: protection.middleware({
    identity: { userId: 'customer', roles: ['customer'], authenticated: true }, toolPolicies: { catalog: { roles: ['customer'] } },
  }) });
  const result = await generateText({ model, prompt: 'Show the public catalog.', stopWhen: stepCountIs(2),
    tools: { catalog: tool({ inputSchema: jsonSchema({ type: 'object', properties: { query: { type: 'string' } }, required: ['query'] }),
      execute: async () => ({ lamp: 'available' }) }) } });
  assert.equal(result.text, 'Public lamp available.');
  const sent = provider.doGenerateCalls[1].prompt.find(message => message.role === 'assistant').content[0];
  assert.equal(sent.providerOptions.google.thoughtSignature, signature);
  assert.equal(JSON.stringify(result.steps).includes(signature), false);
  assert.equal(JSON.stringify(result.response).includes(signature), false);
  assert.equal(JSON.stringify(result.steps).includes('hidden'), false);
});

test('streaming keeps signatures private while retaining them for the next authorized model step', async () => {
  const protection = createPromption({ transport: async ({ text }) => ({ allowed: true, text }) });
  const middleware = protection.middleware({ identity: { userId: 'customer', roles: ['customer'], authenticated: true },
    toolPolicies: { catalog: { roles: ['customer'] } } });
  const params = { prompt: [{ role: 'user', content: [{ type: 'text', text: 'Show the public catalog.' }] }],
    tools: [{ type: 'function', name: 'catalog' }] };
  const result = await middleware.wrapStream({ params, doStream: async () => ({ stream: new ReadableStream({
    start(controller) { controller.enqueue(call); controller.close(); },
  }) }) });
  const delivered = [];
  for await (const chunk of result.stream) delivered.push(chunk);
  assert.equal(JSON.stringify(delivered).includes(signature), false);
  const restored = await middleware.transformParams({ params: { ...params, prompt: [...params.prompt,
    ...prompt(part), { role: 'tool', content: [{ type: 'tool-result', toolCallId: 'call-1', toolName: 'catalog',
      output: { type: 'json', value: { lamp: 'available' } } }] }] } });
  assert.equal(restored.prompt[1].content[0].providerOptions.google.thoughtSignature, signature);
});
