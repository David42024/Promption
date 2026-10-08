import { test } from 'node:test';
import assert from 'node:assert/strict';
import { streamText, wrapLanguageModel, NoOutputGeneratedError } from 'ai';
import { createPromption, PromptionError } from '@promption/ai-sdk';
import { aiFailure } from '../lib/ai/errors.mjs';

test('aiFailure unwraps AI_NoOutputGeneratedError cause when CONTENT_BLOCKED occurs', () => {
  const blockedError = new PromptionError('CONTENT_BLOCKED', { status: 403, reason: 'sensitive_output' });
  const wrapperError = new NoOutputGeneratedError({ message: 'No output generated', cause: blockedError });

  const result = aiFailure(wrapperError);
  assert.equal(result.code, 'CONTENT_BLOCKED');
  assert.equal(result.status, 403);
  assert.equal(result.reason, 'sensitive_output');
  assert.notEqual(result.code, 'MODEL_UNAVAILABLE');
});

test('streamText with Promption middleware preserves CONTENT_BLOCKED and avoids MODEL_UNAVAILABLE', async () => {
  const sdk = createPromption({
    transport: async ({ text, direction }) => {
      if (direction === 'output' && text.includes('secret_leaked')) {
        return { allowed: false, action: 'BLOCK' };
      }
      return { allowed: true, text, action: 'PASS' };
    }
  });

  const mockProvider = {
    specificationVersion: 'v3',
    modelId: 'mock-1',
    provider: 'mock',
    async doStream() {
      return {
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({ type: 'stream-start', warnings: [] });
            controller.enqueue({ type: 'text-start', id: 't' });
            controller.enqueue({ type: 'text-delta', id: 't', delta: 'secret_leaked' });
            controller.enqueue({ type: 'text-end', id: 't' });
            controller.enqueue({ type: 'finish', finishReason: 'stop', usage: {} });
            controller.close();
          }
        })
      };
    }
  };

  const model = wrapLanguageModel({
    model: mockProvider,
    middleware: sdk.middleware({ identity: { userId: 'u1', roles: ['customer'], authenticated: true } })
  });

  let streamError = null;
  const result = streamText({
    model,
    prompt: 'test prompt',
    onError({ error }) {
      streamError = error;
    }
  });

  let caughtError = null;
  try {
    await Promise.all([result.text, result.finishReason]);
  } catch (err) {
    caughtError = streamError || err?.cause || err;
  }

  assert.ok(caughtError, 'StreamText should have failed');
  const failure = aiFailure(caughtError);
  assert.equal(failure.code, 'CONTENT_BLOCKED');
  assert.equal(failure.status, 403);
  assert.notEqual(failure.code, 'MODEL_UNAVAILABLE');
});

test('real provider error preserves its operational classification', () => {
  const providerError = new Error('Rate limit exceeded');
  providerError.statusCode = 429;
  const failure = aiFailure(providerError);
  assert.equal(failure.code, 'QUOTA_EXCEEDED');
  assert.equal(failure.status, 429);
});

test('cancellation does not succeed and returns CANCELLED', () => {
  const abortError = new Error('The operation was aborted');
  abortError.name = 'AbortError';
  const failure = aiFailure(abortError);
  assert.equal(failure.code, 'CANCELLED');
  assert.equal(failure.status, 499);
});

test('GUARD_UNAVAILABLE with cause AbortError and signal.aborted=false preserves GUARD_UNAVAILABLE', () => {
  const abortCause = new Error('The internal operation was aborted');
  abortCause.name = 'AbortError';
  const guardError = new Error('Output guard check failed');
  guardError.code = 'GUARD_UNAVAILABLE';
  guardError.status = 503;
  guardError.cause = abortCause;

  // Signal is not aborted
  const failure = aiFailure(guardError, { aborted: false });
  assert.equal(failure.code, 'GUARD_UNAVAILABLE');
  assert.equal(failure.status, 503);
  assert.notEqual(failure.code, 'CANCELLED');
});

test('nested generic wrapper with cause CONTENT_BLOCKED is correctly classified', () => {
  const securityError = {
    code: 'CONTENT_BLOCKED',
    status: 403,
    reason: 'sensitive_output',
  };
  const intermediateWrapper = new Error('Middle layer failed');
  intermediateWrapper.cause = securityError;
  const outerWrapper = new Error('Top level orchestration failed');
  outerWrapper.cause = intermediateWrapper;

  const failure = aiFailure(outerWrapper);
  assert.equal(failure.code, 'CONTENT_BLOCKED');
  assert.equal(failure.status, 403);
  assert.equal(failure.reason, 'sensitive_output');
});

test('internal AbortError without user cancellation is not reported as user CANCELLED', () => {
  const internalAbort = new Error('Internal fetch connection reset');
  internalAbort.name = 'AbortError';

  const failure = aiFailure(internalAbort, { aborted: false });
  assert.notEqual(failure.code, 'CANCELLED');
  assert.notEqual(failure.status, 499);
  assert.equal(failure.code, 'MODEL_UNAVAILABLE');
  assert.equal(failure.status, 503);
});

test('explicit request cancellation preserves CANCELLED 499', () => {
  const abortError = new Error('User navigated away');
  abortError.name = 'AbortError';

  const failure = aiFailure(abortError, { aborted: true });
  assert.equal(failure.code, 'CANCELLED');
  assert.equal(failure.status, 499);
});
