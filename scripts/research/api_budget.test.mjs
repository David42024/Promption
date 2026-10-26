import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ApiBudget, BudgetStop, lines } from './api_budget.mjs';

const protocol = { budget_usd: 2, max_api_calls: 600, max_output_tokens: 1536, request_timeout_ms: 1000,
  rates_usd_per_million: { 'test-model': { input: .75, output: 4.5 } } };
const body = JSON.stringify({ model: 'test-model', store: false, max_output_tokens: 1536, reasoning: { effort: 'none' }, input: 'Synthetic' });
const setup = () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'promption-api-budget-'));
  for (const folder of ['requests', 'api_responses']) fs.mkdirSync(path.join(dir, folder));
  return dir;
};
const response = () => new Response(JSON.stringify({ id: 'synthetic-response', model: 'test-model',
  usage: { input_tokens: 1000, output_tokens: 200 }, output: [] }), { status: 200 });

test('records a reservation before transport and settles undiscounted actual usage', async () => {
  const dir = setup();
  const budget = new ApiBudget(dir, protocol, async () => {
    assert.equal(lines(budget.file)[0].kind, 'reserved');
    return response();
  });
  await budget.request('https://api.openai.com/v1/responses', { body }, { episode: 'fixture', purpose: 'scope' });
  assert.equal(budget.calls, 1);
  assert.ok(Math.abs(budget.total() - .00165) < 1e-12);
  assert.equal(new ApiBudget(dir, protocol).total(), budget.total());
});

test('never calls transport if the next reservation would exceed two dollars', async () => {
  const dir = setup();
  fs.writeFileSync(path.join(dir, 'api_ledger.jsonl'), JSON.stringify({ kind: 'reserved', call: 1, reserved_usd: 1.9999 }) + '\n');
  let called = false;
  const budget = new ApiBudget(dir, protocol, async () => { called = true; return response(); });
  await assert.rejects(budget.request('https://api.openai.com/v1/responses', { body }, {}), BudgetStop);
  assert.equal(called, false);
  assert.equal(budget.calls, 1);
});

test('an unsettled request stays reserved after restart', () => {
  const dir = setup();
  fs.writeFileSync(path.join(dir, 'api_ledger.jsonl'), JSON.stringify({ kind: 'reserved', call: 1, reserved_usd: .04 }) + '\n');
  assert.equal(new ApiBudget(dir, protocol).total(), .04);
});

test('unknown usage retains the upper reservation and stops further calls', async () => {
  const dir = setup();
  const budget = new ApiBudget(dir, protocol, async () => new Response(JSON.stringify({ error: { type: 'invalid', code: 'invalid', message: 'DO_NOT_SAVE_THIS' } }), { status: 400 }));
  await budget.request('https://api.openai.com/v1/responses', { body }, {});
  assert.ok(budget.total() > 0);
  assert.equal(budget.stopped, true);
  assert.ok(!fs.readFileSync(path.join(dir, 'api_responses/1.json'), 'utf8').includes('DO_NOT_SAVE_THIS'));
  await assert.rejects(budget.request('https://api.openai.com/v1/responses', { body }, {}), BudgetStop);
});

test('rejects alternate endpoints and hosted tools before spending', async () => {
  const dir = setup();
  let called = false;
  const budget = new ApiBudget(dir, protocol, async () => { called = true; return response(); });
  await assert.rejects(budget.request('https://example.com/v1/responses', { body }, {}));
  await assert.rejects(budget.request('https://api.openai.com/v1/responses',
    { body: JSON.stringify({ ...JSON.parse(body), tools: [{ type: 'web_search' }] }) }, {}));
  assert.equal(called, false);
});
