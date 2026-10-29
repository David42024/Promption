import test from 'node:test';
import assert from 'node:assert/strict';
import { generateText, jsonSchema, tool } from 'ai';
import { createContextEvaluator } from '@promption/ai-sdk';
import { createChatProvider, getChatModelConfiguration, getChatProviderOptions } from '../lib/ai/provider.js';

const env = { AI_PROVIDER: 'deepseek', DEEPSEEK_API_KEY: 'synthetic-key',
  DEEPSEEK_MODEL: 'deepseek-flash', DEEPSEEK_TOOL_MODEL: 'deepseek-flash',
  OPENAI_API_KEY: 'unused-openai-key', OPENAI_MODEL: 'unused-openai-model' };

function completion(message) {
  return new Response(JSON.stringify({ id: 'test-completion', object: 'chat.completion',
    created: 1, model: 'deepseek-flash', choices: [{ index: 0, message,
      finish_reason: message.tool_calls ? 'tool_calls' : 'stop' }],
    usage: { prompt_tokens: 10, completion_tokens: 10, total_tokens: 20 } }),
  { headers: { 'content-type': 'application/json' } });
}

test('DeepSeek requires its own credentials and configured models', () => {
  const config = getChatModelConfiguration(env);
  assert.equal(config.apiKey, 'synthetic-key');
  assert.equal(config.model, 'deepseek-flash');
  assert.throws(() => getChatModelConfiguration({ ...env, DEEPSEEK_API_KEY: '' }));
  assert.throws(() => getChatModelConfiguration({ ...env, DEEPSEEK_TOOL_MODEL: '' }));
  assert.throws(() => getChatModelConfiguration({ ...env, AI_PROVIDER: 'unknown' }));
  assert.equal(getChatModelConfiguration({ ...env, DEEPSEEK_TOOL_MODEL: '' }, { requireTools: false }).model, 'deepseek-flash');
});

test('DeepSeek scope uses official JSON mode and local schema validation', async () => {
  const config = getChatModelConfiguration(env);
  const requests = [];
  const provider = createChatProvider(config, { fetch: async (url, options) => {
    requests.push({ url: String(url), headers: options.headers, body: JSON.parse(options.body) });
    return completion({ role: 'assistant', content: JSON.stringify({
      decision: 'in_scope', intent: { name: 'social', attack: 'none', origin: 'none',
        relation: 'standalone', confidence: 0.98, evidence: [] } }) });
  } });
  const evaluate = createContextEvaluator({ model: provider(config.model),
    providerOptions: getChatProviderOptions(config, config.model) });
  const decision = await evaluate({ text: 'Hola', systemPrompt: 'Asistente de una tienda. Permite saludos.',
    identity: { userId: 'synthetic-user', roles: ['customer'], authenticated: true } });
  assert.equal(decision.allowed, true);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'https://api.deepseek.com/chat/completions');
  assert.equal(new Headers(requests[0].headers).get('authorization'), 'Bearer synthetic-key');
  assert.deepEqual(requests[0].body.response_format, { type: 'json_object' });
  assert.deepEqual(requests[0].body.thinking, { type: 'disabled' });
  assert.ok(requests[0].body.messages.some(message => /"decision"/.test(message.content)));
  assert.equal(requests[0].body.reasoning_effort, undefined);
});

test('DeepSeek returns tool calls through AI SDK without executing them', async () => {
  const config = getChatModelConfiguration(env);
  let sent;
  const provider = createChatProvider(config, { fetch: async (_url, options) => {
    sent = JSON.parse(options.body);
    return completion({ role: 'assistant', content: null, tool_calls: [{ id: 'call-stock', type: 'function',
      function: { name: 'getStockInfo', arguments: '{}' } }] });
  } });
  const result = await generateText({ model: provider(config.toolModel), prompt: 'Consulta el stock.',
    tools: { getStockInfo: tool({ description: 'Consulta stock autorizado',
      inputSchema: jsonSchema({ type: 'object', properties: {} }) }) },
    providerOptions: getChatProviderOptions(config, config.toolModel, { parallelToolCalls: false, maxToolCalls: 1 }) });
  assert.equal(result.toolCalls[0].toolName, 'getStockInfo');
  assert.equal(sent.tools[0].function.name, 'getStockInfo');
  assert.equal(sent.parallel_tool_calls, undefined);
  assert.equal(sent.max_tool_calls, undefined);
  assert.equal(sent.reasoning_effort, undefined);
});

test('DeepSeek malformed scope output fails closed', async () => {
  const config = getChatModelConfiguration(env);
  const provider = createChatProvider(config, { fetch: async () => completion({ role: 'assistant',
    content: JSON.stringify({ assessment: 'Invalid decision', decision: 'do_whatever' }) }) });
  const evaluate = createContextEvaluator({ model: provider(config.model),
    providerOptions: getChatProviderOptions(config, config.model) });
  const decision = await evaluate({ text: 'Hola', systemPrompt: 'Asistente de tienda.',
    identity: { userId: 'synthetic-user', roles: [], authenticated: false } });
  assert.equal(decision.allowed, false);
});
