import test from 'node:test';
import assert from 'node:assert/strict';
import { createOpenAI } from '@ai-sdk/openai';
import { generateText, jsonSchema, tool } from 'ai';
import { createScopeEvaluator } from '@promption/ai-sdk';
import {
  isReasoningModel,
  validateReasoningEffort,
  getModelProviderOptions,
  validateModelConfiguration,
} from '../lib/ai/modelOptions.js';

function makeFakeResponse(content = 'Respuesta de prueba') {
  return new Response(JSON.stringify({
    id: 'resp-test',
    status: 'completed',
    created_at: Math.floor(Date.now() / 1000),
    output: [
      {
        id: 'msg-test',
        type: 'message',
        role: 'assistant',
        content: [
          {
            type: 'output_text',
            text: content,
            annotations: [],
          },
        ],
      },
    ],
    usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
  }), { status: 200, headers: { 'content-type': 'application/json' } });
}

test('isReasoningModel correctly identifies reasoning vs standard models', () => {
  assert.equal(isReasoningModel('gpt-5'), true);
  assert.equal(isReasoningModel('gpt-5-mini'), true);
  assert.equal(isReasoningModel('gpt-5-nano'), true);
  assert.equal(isReasoningModel('gpt-5-mini-2025-01-01'), true);
  assert.equal(isReasoningModel('o1'), true);
  assert.equal(isReasoningModel('o1-mini'), true);
  assert.equal(isReasoningModel('o3-mini'), true);
  assert.equal(isReasoningModel('gpt-4o'), false);
  assert.equal(isReasoningModel('gpt-4o-mini'), false);
  assert.equal(isReasoningModel('gpt-3.5-turbo'), false);
  assert.equal(isReasoningModel(null), false);
  assert.equal(isReasoningModel(''), false);
});

test('validateReasoningEffort validates effort values and rejects invalid ones', () => {
  assert.equal(validateReasoningEffort('low'), 'low');
  assert.equal(validateReasoningEffort('medium'), 'medium');
  assert.equal(validateReasoningEffort('high'), 'high');
  assert.equal(validateReasoningEffort('minimal'), 'minimal');
  assert.throws(() => validateReasoningEffort('extreme'), TypeError);
  assert.throws(() => validateReasoningEffort(123), TypeError);
});

test('validateModelConfiguration throws on invalid environment configuration', () => {
  assert.throws(() => validateModelConfiguration({ OPENAI_REASONING_EFFORT: 'invalid' }), TypeError);
  assert.doesNotThrow(() => validateModelConfiguration({ OPENAI_REASONING_EFFORT: 'minimal' }));
  assert.doesNotThrow(() => validateModelConfiguration({}));
});

test('getModelProviderOptions resolves reasoningEffort and preserves tool options', () => {
  const reasoningOpts = getModelProviderOptions('gpt-5-mini', { parallelToolCalls: false, maxToolCalls: 1 });
  assert.deepEqual(reasoningOpts, {
    openai: {
      reasoningEffort: 'minimal',
      parallelToolCalls: false,
      maxToolCalls: 1,
    },
  });

  const standardOpts = getModelProviderOptions('gpt-4o', { parallelToolCalls: false, maxToolCalls: 1 });
  assert.deepEqual(standardOpts, {
    openai: {
      parallelToolCalls: false,
      maxToolCalls: 1,
    },
  });
  assert.equal(standardOpts.openai?.reasoningEffort, undefined);
});

test('captures HTTP body locally with fake fetch and verifies reasoning.effort in generation', async () => {
  const capturedRequests = [];
  const fakeFetch = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    capturedRequests.push({ url, body });
    return makeFakeResponse('Respuesta generada de prueba');
  };

  const provider = createOpenAI({ apiKey: 'mock-key', fetch: fakeFetch });
  const modelId = 'gpt-5-mini';
  const providerOptions = getModelProviderOptions(modelId, { parallelToolCalls: false, maxToolCalls: 1 });

  const result = await generateText({
    model: provider(modelId),
    prompt: 'Hola, ¿cómo estás?',
    providerOptions,
  });

  assert.equal(result.text, 'Respuesta generada de prueba');
  assert.equal(capturedRequests.length, 1);
  const reqBody = capturedRequests[0].body;
  assert.ok(reqBody, 'Body should be captured');
  assert.equal(reqBody.reasoning?.effort, 'minimal');
});

test('captures HTTP body locally and verifies tool options are preserved', async () => {
  const capturedRequests = [];
  const fakeFetch = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    capturedRequests.push({ url, body });
    return makeFakeResponse('Herramienta no requerida');
  };

  const provider = createOpenAI({ apiKey: 'mock-key', fetch: fakeFetch });
  const modelId = 'gpt-5-mini';
  const providerOptions = getModelProviderOptions(modelId, { parallelToolCalls: false, maxToolCalls: 1 });

  await generateText({
    model: provider(modelId),
    prompt: 'Consulta stock',
    tools: {
      check_stock: tool({
        description: 'Ver stock',
        inputSchema: jsonSchema({ type: 'object', properties: { item: { type: 'string' } } }),
      }),
    },
    providerOptions,
  });

  assert.equal(capturedRequests.length, 1);
  const reqBody = capturedRequests[0].body;
  assert.equal(reqBody.reasoning?.effort, 'minimal');
  assert.equal(reqBody.parallel_tool_calls, false);
});

test('captures HTTP body locally and verifies reasoning.effort is omitted for standard models', async () => {
  const capturedRequests = [];
  const fakeFetch = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    capturedRequests.push({ url, body });
    return makeFakeResponse('Respuesta estándar');
  };

  const provider = createOpenAI({ apiKey: 'mock-key', fetch: fakeFetch });
  const modelId = 'gpt-4o';
  const providerOptions = getModelProviderOptions(modelId, { parallelToolCalls: false });

  await generateText({
    model: provider(modelId),
    prompt: 'Consulta básica',
    providerOptions,
  });

  assert.equal(capturedRequests.length, 1);
  const reqBody = capturedRequests[0].body;
  assert.equal(reqBody.reasoning, undefined);
  assert.equal(reqBody.parallel_tool_calls, false);
});

test('captures HTTP body locally in createScopeEvaluator and verifies reasoning.effort', async () => {
  const capturedRequests = [];
  const fakeFetch = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    capturedRequests.push({ url, body });
    return makeFakeResponse(JSON.stringify({ assessment: 'Consulta de política permitida', decision: 'in_scope' }));
  };

  const provider = createOpenAI({ apiKey: 'mock-key', fetch: fakeFetch });
  const modelId = 'gpt-5-mini';
  const evaluate = createScopeEvaluator({
    model: provider(modelId),
    providerOptions: getModelProviderOptions(modelId),
  });

  const decision = await evaluate({
    text: '¿Cuáles son las políticas de devolución?',
    systemPrompt: 'Eres un asistente de compras.',
    identity: { userId: 'u1', roles: ['customer'], authenticated: true },
  });

  assert.equal(decision.allowed, true);
  assert.equal(decision.classification, 'IN_SCOPE');
  assert.equal(capturedRequests.length, 1);
  const reqBody = capturedRequests[0].body;
  assert.equal(reqBody.reasoning?.effort, 'minimal');
});
