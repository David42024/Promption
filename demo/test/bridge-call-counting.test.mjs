import { test } from 'node:test';
import assert from 'node:assert/strict';
import { streamText, generateText, wrapLanguageModel, NoOutputGeneratedError } from 'ai';
import { createPromption, createScopeEvaluator, PromptionError } from '@promption/ai-sdk';
import { createTrackingModel } from '../lib/ai/tracking.js';
import { aiFailure } from '../lib/ai/errors.mjs';

const identity = { userId: 'u1', roles: ['customer'], authenticated: true };
const system = 'Shop assistant only';

test('createTrackingModel correctly increments on doStream and doGenerate invocation', async () => {
  let streamCount = 0;
  let genCount = 0;

  const baseModel = {
    specificationVersion: 'v3',
    modelId: 'test-model',
    provider: 'test-provider',
    async doStream() {
      return {
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({ type: 'stream-start', warnings: [] });
            controller.enqueue({ type: 'text-start', id: '1' });
            controller.enqueue({ type: 'text-delta', id: '1', delta: 'hello' });
            controller.enqueue({ type: 'text-end', id: '1' });
            controller.enqueue({ type: 'finish', finishReason: { unified: 'stop', raw: 'stop' }, usage: {} });
            controller.close();
          },
        }),
      };
    },
    async doGenerate() {
      return {
        content: [{ type: 'text', text: 'response' }],
        finishReason: { unified: 'stop', raw: 'stop' },
        usage: { inputTokens: { total: 5 }, outputTokens: { total: 5 } },
        warnings: [],
      };
    },
  };

  const tracked = createTrackingModel(baseModel, () => { streamCount++; });
  const trackedGen = createTrackingModel(baseModel, () => { genCount++; });

  assert.equal(streamCount, 0);
  assert.equal(genCount, 0);

  await tracked.doStream();
  assert.equal(streamCount, 1);

  await trackedGen.doGenerate();
  assert.equal(genCount, 1);
});

test('Case 1: Invalid request or cancelled before starting makes zero provider calls', async () => {
  let callCount = 0;
  const baseModel = {
    specificationVersion: 'v3',
    modelId: 'test-model',
    provider: 'test',
    async doStream() {
      throw new Error('should not be reached');
    },
  };
  const tracked = createTrackingModel(baseModel, () => { callCount++; });

  const controller = new AbortController();
  controller.abort(new Error('Pre-call abort'));

  try {
    const result = streamText({
      model: tracked,
      prompt: 'hello',
      abortSignal: controller.signal,
    });
    await result.text;
    assert.fail('Should reject');
  } catch (err) {
    // Expected abort
  }
  assert.equal(callCount, 0, 'Zero calls initiated when cancelled before starting');
});

test('Case 2: Middleware blocking (CONTENT_BLOCKED) before generation makes zero generation calls', async () => {
  let genCalls = 0;
  let scopeCalls = 0;

  const sdk = createPromption({
    transport: async ({ text, direction }) => {
      if (direction === 'input') {
        return { allowed: false, action: 'BLOCK' };
      }
      return { allowed: true, text, action: 'PASS' };
    },
  });

  const baseGenModel = {
    specificationVersion: 'v3',
    modelId: 'gen-model',
    provider: 'test',
    async doStream() {
      throw new Error('Should not reach generation model');
    },
  };
  const trackedGen = createTrackingModel(baseGenModel, () => { genCalls++; });

  const baseScopeModel = {
    specificationVersion: 'v3',
    modelId: 'scope-model',
    provider: 'test',
    async doGenerate() {
      throw new Error('Should not reach scope model when input guard blocks');
    },
  };
  const trackedScope = createTrackingModel(baseScopeModel, () => { scopeCalls++; });

  const model = wrapLanguageModel({
    model: trackedGen,
    middleware: sdk.middleware({
      identity,
      originalText: 'malicious prompt',
      scopeEvaluator: createScopeEvaluator({ model: trackedScope }),
    }),
  });

  let streamError = null;
  const result = streamText({
    model,
    prompt: 'malicious prompt',
    onError({ error }) {
      streamError = error;
    },
  });

  try {
    await result.text;
    assert.fail('Should reject');
  } catch (err) {
    const error = streamError || err?.cause || err;
    const failure = aiFailure(error);
    assert.equal(failure.code, 'CONTENT_BLOCKED');
    assert.equal(failure.status, 403);
  }

  assert.equal(genCalls, 0, 'Generation calls must be zero');
  assert.equal(scopeCalls, 0, 'Scope calls must be zero because input blocked first');
});

test('Case 3: Provider returns 503 error after initiation: call is counted and error preserved', async () => {
  let genCalls = 0;
  const baseModel = {
    specificationVersion: 'v3',
    modelId: 'gen-model',
    provider: 'test',
    async doStream() {
      const err = new Error('Service Unavailable');
      err.statusCode = 503;
      throw err;
    },
  };
  const tracked = createTrackingModel(baseModel, () => { genCalls++; });

  let streamError = null;
  const result = streamText({
    model: tracked,
    prompt: 'hello',
    onError({ error }) {
      streamError = error;
    },
  });

  try {
    await result.text;
    assert.fail('Should reject');
  } catch (err) {
    const error = streamError || err?.cause || err;
    const failure = aiFailure(error);
    assert.equal(failure.code, 'MODEL_UNAVAILABLE');
    assert.equal(failure.status, 503);
  }

  assert.equal(genCalls, 1, 'Exactly one call was initiated');
});

test('Case 4: Timeout after initiating transport: call is counted, usage unknown as null', async () => {
  let genCalls = 0;
  const baseModel = {
    specificationVersion: 'v3',
    modelId: 'gen-model',
    provider: 'test',
    async doStream() {
      const err = new Error('Gateway Timeout');
      err.statusCode = 504;
      throw err;
    },
  };
  const tracked = createTrackingModel(baseModel, () => { genCalls++; });

  let streamError = null;
  const result = streamText({
    model: tracked,
    prompt: 'hello',
    onError({ error }) {
      streamError = error;
    },
  });

  try {
    await result.text;
  } catch (err) {
    const error = streamError || err?.cause || err;
    const failure = aiFailure(error);
    assert.equal(failure.code, 'GATEWAY_TIMEOUT');
    assert.equal(failure.status, 504);
  }
  assert.equal(genCalls, 1);
});

test('Case 5: Cancellation before start does not invent a call', async () => {
  let calls = 0;
  const controller = new AbortController();
  controller.abort(new DOMException('User cancelled', 'AbortError'));

  const baseModel = {
    specificationVersion: 'v3',
    modelId: 'test',
    provider: 'test',
    async doStream() {
      throw new Error('should not call');
    },
  };
  const tracked = createTrackingModel(baseModel, () => { calls++; });

  try {
    const result = streamText({
      model: tracked,
      prompt: 'hello',
      abortSignal: controller.signal,
    });
    await result.text;
  } catch (err) {
    const failure = aiFailure(err, { signal: controller.signal, aborted: true });
    assert.equal(failure.code, 'CANCELLED');
    assert.equal(failure.status, 499);
  }
  assert.equal(calls, 0);
});

test('Case 6: Cancellation after start counts initiated attempt without success', async () => {
  let calls = 0;
  const controller = new AbortController();

  const baseModel = {
    specificationVersion: 'v3',
    modelId: 'test',
    provider: 'test',
    async doStream() {
      controller.abort(new DOMException('Cancelled during streaming', 'AbortError'));
      throw controller.signal.reason;
    },
  };
  const tracked = createTrackingModel(baseModel, () => { calls++; });

  try {
    const result = streamText({
      model: tracked,
      prompt: 'hello',
      abortSignal: controller.signal,
    });
    await result.text;
  } catch (err) {
    const failure = aiFailure(err, { signal: controller.signal, aborted: true });
    assert.equal(failure.code, 'CANCELLED');
  }
  assert.equal(calls, 1, 'Initiated attempt was counted');
});

test('Case 7: Scope fails before generation: scope is counted, generation remains zero', async () => {
  let scopeCalls = 0;
  let genCalls = 0;

  const baseScopeModel = {
    specificationVersion: 'v3',
    modelId: 'scope-model',
    provider: 'test',
    async doGenerate() {
      const err = new Error('Scope classifier 503');
      err.statusCode = 503;
      throw err;
    },
  };
  const trackedScope = createTrackingModel(baseScopeModel, () => { scopeCalls++; });

  const baseGenModel = {
    specificationVersion: 'v3',
    modelId: 'gen-model',
    provider: 'test',
    async doStream() {
      throw new Error('Should not reach generation model');
    },
  };
  const trackedGen = createTrackingModel(baseGenModel, () => { genCalls++; });

  const sdk = createPromption({
    transport: async ({ text }) => ({ allowed: true, text, action: 'PASS' }),
    scopeEvaluator: createScopeEvaluator({ model: trackedScope }),
  });

  const model = wrapLanguageModel({
    model: trackedGen,
    middleware: sdk.middleware({ identity, originalText: 'test prompt' }),
  });

  let streamError = null;
  const result = streamText({
    model,
    system,
    prompt: 'test prompt',
    onError({ error }) {
      streamError = error;
    },
  });

  try {
    await result.text;
    assert.fail('Should reject');
  } catch (err) {
    const error = streamError || err?.cause || err;
    const failure = aiFailure(error);
    assert.equal(failure.code, 'SCOPE_UNCERTAIN');
    assert.equal(failure.status, 503);
  }

  assert.equal(scopeCalls, 1, 'Scope call was initiated and counted');
  assert.equal(genCalls, 0, 'Generation model was never called');
});

test('Case 8: Scope and generation completed: both counted without duplication', async () => {
  let scopeCalls = 0;
  let genCalls = 0;

  const baseScopeModel = {
    specificationVersion: 'v3',
    modelId: 'scope-model',
    provider: 'test',
    async doGenerate() {
      return {
        content: [{ type: 'text', text: JSON.stringify({ assessment: 'valid', decision: 'in_scope' }) }],
        finishReason: { unified: 'stop', raw: 'stop' },
        usage: { inputTokens: { total: 10 }, outputTokens: { total: 5 } },
        warnings: [],
      };
    },
  };
  const trackedScope = createTrackingModel(baseScopeModel, () => { scopeCalls++; });

  const baseGenModel = {
    specificationVersion: 'v3',
    modelId: 'gen-model',
    provider: 'test',
    async doStream() {
      return {
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({ type: 'stream-start', warnings: [] });
            controller.enqueue({ type: 'text-start', id: '1' });
            controller.enqueue({ type: 'text-delta', id: '1', delta: 'Generation text' });
            controller.enqueue({ type: 'text-end', id: '1' });
            controller.enqueue({ type: 'finish', finishReason: { unified: 'stop', raw: 'stop' }, usage: { inputTokens: { total: 20 }, outputTokens: { total: 10 } } });
            controller.close();
          },
        }),
      };
    },
  };
  const trackedGen = createTrackingModel(baseGenModel, () => { genCalls++; });

  const sdk = createPromption({
    transport: async ({ text }) => ({ allowed: true, text, action: 'PASS' }),
    scopeEvaluator: createScopeEvaluator({ model: trackedScope }),
  });

  const model = wrapLanguageModel({
    model: trackedGen,
    middleware: sdk.middleware({ identity, originalText: 'test prompt' }),
  });

  const result = streamText({
    model,
    system,
    prompt: 'test prompt',
  });

  const text = await result.text;
  assert.equal(text, 'Generation text');
  assert.equal(scopeCalls, 1);
  assert.equal(genCalls, 1);
  assert.equal(scopeCalls + genCalls, 2);
});

test('Case 9: CONTENT_BLOCKED preserves security code and status without provider fallback', async () => {
  let genCalls = 0;

  const sdk = createPromption({
    transport: async () => ({ allowed: false, action: 'BLOCK' }),
  });

  const baseGenModel = {
    specificationVersion: 'v3',
    modelId: 'gen-model',
    provider: 'test',
    async doStream() {
      throw new Error('Should never call provider');
    },
  };
  const trackedGen = createTrackingModel(baseGenModel, () => { genCalls++; });

  const model = wrapLanguageModel({
    model: trackedGen,
    middleware: sdk.middleware({ identity, originalText: 'attack prompt' }),
  });

  let streamError = null;
  const result = streamText({
    model,
    prompt: 'attack prompt',
    onError({ error }) {
      streamError = error;
    },
  });

  try {
    await result.text;
    assert.fail('Should reject');
  } catch (err) {
    const error = streamError || err?.cause || err;
    const failure = aiFailure(error);
    assert.equal(failure.code, 'CONTENT_BLOCKED');
    assert.equal(failure.status, 403);
  }

  assert.equal(genCalls, 0);
});
