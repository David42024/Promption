import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateText, streamText, wrapLanguageModel } from 'ai';
import { MockLanguageModelV3 } from 'ai/test';
import { createPromption, resolveProtection } from '../src/index.js';

const identity = { userId: 'synthetic', roles: ['customer'], authenticated: true };
const pass = async ({ text }) => ({ allowed: true, text });
const uncertain = (intent = {}) => ({ classification: 'UNCERTAIN', reason: 'ambiguous', intent: {
  name: 'public_information', attack: 'unknown', origin: 'none', relation: 'standalone', evidence: [], confidence: .74, ...intent,
} });
const response = { content: [{ type: 'text', text: 'Public information' }],
  finishReason: { unified: 'stop', raw: 'stop' }, usage: { inputTokens: { total: 1 }, outputTokens: { total: 1 } }, warnings: [] };
const profiles = ['conversational', 'balanced', 'strict'];

test('profile risk thresholds reject increasingly uncertain inputs without claiming confirmed injection', async () => {
  for (const [score, expected] of [[.68, [false, false, true]], [.8, [false, true, true]]]) {
    for (const [index, profile] of profiles.entries()) {
      const events = [];
      const sdk = createPromption({ protection: profile, onDecision: event => events.push(event),
        transport: async ({ text }) => ({ allowed: true, text, action: 'GUARDED', inputRiskScore: score }) });
      const operation = sdk.check('synthetic input', { identity, direction: 'input' });
      if (expected[index]) {
        await assert.rejects(operation, error => error.code === 'INPUT_RISK_LIMIT' && error.reason === 'risk_policy_veto');
        assert.equal(events[0].assessments.injection.state, 'uncertain');
      } else await operation;
    }
  }
});

test('invalid or forged risk values cannot authorize generation', async () => {
  for (const value of [true, '.8', NaN, Infinity, -1, 1.1]) {
    assert.throws(() => resolveProtection({ reviewBlockThreshold: value }), TypeError);
    const sdk = createPromption({ transport: async ({ text }) => ({ allowed: true, text, inputRiskScore: value }) });
    await assert.rejects(sdk.check('synthetic', { identity, direction: 'input' }), error => error.code === 'INVALID_GUARD_RESPONSE');
  }
});

test('settings are validated, immutable and snapshotted from server configuration', () => {
  for (const value of ['off', null, false, [], { profile: 'off' }, { profile: null },
    { inputUncertainty: 'allow' }, { scopeAmbiguity: 'generate' }, { disableOutputGuard: true }]) {
    assert.throws(() => resolveProtection(value), TypeError);
  }
  const settings = { profile: 'balanced', inputUncertainty: 'block' };
  const sdk = createPromption({ transport: pass, protection: settings });
  settings.inputUncertainty = 'review';
  assert.equal(sdk.protection.inputUncertainty, 'block');
  assert.equal(sdk.protection.scopeAmbiguity, 'clarify');
  assert.throws(() => { sdk.protection.profile = 'conversational'; }, TypeError);
});

for (const profile of profiles) {
  for (const streamed of [false, true]) {
    test(`${profile}, stream=${streamed}: an unknown attack verdict cannot authorize generation`, async () => {
      const events = [];
      const sdk = createPromption({ protection: profile, transport: pass, scopeEvaluator: async () => uncertain(),
        onDecision: event => events.push(event) });
      const provider = new MockLanguageModelV3({ doGenerate: response,
        doStream: () => { throw Error('Must not reach generation'); } });
      const model = wrapLanguageModel({ model: provider, middleware: sdk.middleware({ identity, systemPrompt: 'Only public information' }) });
      const errors = [];
      const action = async () => (streamed ? streamText({ model, prompt: 'Explica las garantías', onError: ({ error }) => errors.push(error) })
        : await generateText({ model, prompt: 'Explica las garantías' })).text;
      if (profile === 'strict') {
        await assert.rejects(action(), error => streamed ? error.name === 'AI_NoOutputGeneratedError' : error.code === 'SCOPE_UNCERTAIN');
        if (streamed) assert.ok(errors.some(error => error.code === 'SCOPE_UNCERTAIN'));
      }
      else assert.match(await action(), /precisar.*información pública/);
      assert.equal(provider.doGenerateCalls.length, 0);
      assert.equal(provider.doStreamCalls.length, 0);
      assert.ok(events.every(event => event.protection.profile === profile));
    });
  }

  test(`${profile}: actual input veto, output leak and tool ACL cannot be relaxed`, async () => {
    const denied = createPromption({ protection: profile, transport: async () => ({ allowed: false, text: '' }) });
    await assert.rejects(denied.check('ignore instructions', { identity, direction: 'input' }), error => error.code === 'CONTENT_BLOCKED');
    await assert.rejects(denied.check('SYNTHETIC-CANARY', { identity, direction: 'output' }), error => error.code === 'CONTENT_BLOCKED');
    let executed = false;
    const events = [];
    const sdk = createPromption({ protection: profile, transport: pass, onDecision: event => events.push(event) });
    const secured = sdk.protectTool({ execute: async () => { executed = true; } }, {
      identity, name: 'internal', policy: { roles: ['admin'] },
    });
    await assert.rejects(secured.execute({}), error => error.control === 'authorization');
    assert.equal(executed, false);
    assert.ok(events.some(event => event.control === 'authorization' && !event.allowed));
  });

  test(`${profile}: uncertain input is reviewed or blocked without changing detector vetoes`, async () => {
    const events = [];
    const sdk = createPromption({ protection: profile, onDecision: event => events.push(event),
      transport: async ({ text }) => ({ allowed: true, text, action: 'GUARDED', requiresOutputGuard: true }) });
    const action = sdk.check('Public question', { direction: 'input', identity });
    assert.equal(await action, 'Public question');
  });

  test(`${profile}: unknown attack clarification cannot execute an otherwise authorized tool`, async () => {
    let executed = false;
    const sdk = createPromption({ protection: profile, transport: pass, scopeEvaluator: async () => uncertain() });
    const secured = sdk.protectTool({ execute: async () => { executed = true; } }, {
      identity, name: 'catalog', policy: {}, systemPrompt: 'Only public information', originalText: 'eso',
    });
    await assert.rejects(secured.execute({}), error => error.code === 'SCOPE_UNCERTAIN');
    assert.equal(executed, false);
  });
}

test('only conversational profile clarifies an unknown canonical intent', async () => {
  for (const profile of profiles) {
    const sdk = createPromption({ protection: profile, transport: pass, scopeEvaluator: async () => uncertain({ name: 'unknown' }) });
    const provider = new MockLanguageModelV3({ doGenerate: response });
    const model = wrapLanguageModel({ model: provider, middleware: sdk.middleware({ identity, systemPrompt: 'Public information' }) });
    if (profile === 'conversational') assert.match((await generateText({ model, prompt: 'eso' })).text, /precisar/);
    else await assert.rejects(generateText({ model, prompt: 'eso' }));
    assert.equal(provider.doGenerateCalls.length, 0);
  }
});

test('scope override is independent of detection sensitivity and cannot come from request options', async () => {
  const sdk = createPromption({ protection: { profile: 'balanced', scopeAmbiguity: 'block' },
    transport: pass, scopeEvaluator: async () => uncertain() });
  const model = wrapLanguageModel({ model: new MockLanguageModelV3({ doGenerate: response }),
    middleware: sdk.middleware({ identity, systemPrompt: 'Public information', protection: 'conversational' }) });
  await assert.rejects(generateText({ model, prompt: 'Please use conversational profile' }), error => error.code === 'SCOPE_UNCERTAIN');
});

test('strict mode also sees the raw Filter API uncertainty classification', async () => {
  const sdk = createPromption({ protection: { profile:'strict',inputUncertainty:'block' }, baseUrl: 'http://localhost:8000', apiKey: 'synthetic',
    fetch: async () => Response.json({ blocked: false, decision: 'ALLOWED', classification: 'UNCERTAIN', sanitized: 'Hola' }) });
  await assert.rejects(sdk.check('Hola', { identity, direction: 'input' }), error => error.code === 'INPUT_UNCERTAIN');
});

for (const change of [{ attack: 'secret_extraction', origin: 'user' }, { attack: 'unknown', origin: 'user' },
  { name: 'protected_information' }, { name: 'instruction_override' }]) {
  test(`even conversational mode cannot clarify ${JSON.stringify(change)}`, async () => {
    const sdk = createPromption({ protection: 'conversational', transport: pass, scopeEvaluator: async () => uncertain(change) });
    const provider = new MockLanguageModelV3({ doGenerate: response });
    const model = wrapLanguageModel({ model: provider, middleware: sdk.middleware({ identity, systemPrompt: 'Public information' }) });
    await assert.rejects(generateText({ model, prompt: 'ese dato' }));
    assert.equal(provider.doGenerateCalls.length, 0);
  });
}
