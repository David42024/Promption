import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { createContextEvaluator, createScopeEvaluator } from '../../packages/ai-sdk/src/index.js';
import { intentNames, attacks, origins, relations } from '../../packages/ai-sdk/src/intent.js';

const folder = path.resolve(process.argv[2] || 'output/context_eval_20261023');
if (!process.argv.includes('--allow-external')) throw Error('Explicit --allow-external is required');
if (!process.env.OPENAI_API_KEY) throw Error('Missing local API credential');
const protocol = JSON.parse(await fs.readFile(path.join(folder, 'protocol.json'), 'utf8'));
const dataBytes = await fs.readFile(path.join(folder, 'cases_private.json'));
if (crypto.createHash('sha256').update(dataBytes).digest('hex') !== protocol.cases_sha256) {
  throw Error('Frozen input changed');
}
const data = JSON.parse(dataBytes);
if (!Number.isInteger(protocol.max_calls) || protocol.max_calls < 1 || protocol.max_calls > 100
    || !Number.isFinite(protocol.max_usd) || protocol.max_usd <= 0 || protocol.max_usd > 1 || data.cases.length !== 50
    || !Array.isArray(protocol.profiles) || !protocol.profiles.length
    || protocol.profiles.some(profile => !['legacy_scope', 'context_intent'].includes(profile))) {
  throw Error('Unexpected authorization bounds');
}
for (const [name, expected] of Object.entries(protocol.library_sources)) {
  const actual = crypto.createHash('sha256').update(await fs.readFile(path.resolve(name))).digest('hex');
  if (actual !== expected) throw Error('Frozen library source changed');
}
const app = path.resolve(process.env.PROMPTION_COMPETITION_DIR || '../promption_compe');
const require = createRequire(path.join(app, 'package.json'));
const { createOpenAI } = await import(require.resolve('@ai-sdk/openai'));
const ledgerPath = path.join(folder, 'api_ledger.jsonl');
const resultsPath = path.join(folder, 'scope_results.jsonl');
async function readLines(file) {
  try { return (await fs.readFile(file, 'utf8')).split('\n').filter(Boolean).map(JSON.parse); }
  catch (error) { if (error.code === 'ENOENT') return []; throw error; }
}
let serial = Promise.resolve();
function append(file, value) {
  serial = serial.then(() => fs.appendFile(file, JSON.stringify(value) + '\n', { mode: 0o600 }));
  return serial;
}
const previous = await readLines(ledgerPath);
let calls = previous.filter(row => row.kind === 'reserved').length;
const accounted = new Map(previous.filter(row => row.kind === 'reserved').map(row => [row.call, row.reservation]));
for (const row of previous.filter(row => row.kind === 'settled')) accounted.set(row.call, row.charged_upper_usd);
let spent = (protocol.prior_spent_upper_usd ?? 0) + [...accounted.values()].reduce((a, b) => a + b, 0);
let reserved = 0;
let stop = false;
let stopReason = null;
const guardedFetch = async (url, options) => {
  const target = new URL(url);
  if (target.origin !== 'https://api.openai.com' || target.pathname !== '/v1/responses') {
    throw Error('Unexpected evaluation endpoint');
  }
  const body = typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString();
  const parsed = JSON.parse(body);
  if (parsed.model !== protocol.model || parsed.store !== false || parsed.tools?.length
      || parsed.max_output_tokens !== protocol.max_output_tokens) throw Error('Unexpected request configuration');
  const reservation = (Buffer.byteLength(body) + 4000) * protocol.input_usd_per_million / 1e6
    + protocol.max_output_tokens * protocol.output_usd_per_million / 1e6;
  if (stop || calls >= protocol.max_calls || spent + reserved + reservation > protocol.max_usd) {
    stop = true;
    stopReason = 'budget';
    throw Error('Evaluation authorization limit reached');
  }
  const call = ++calls;
  reserved += reservation;
  await append(ledgerPath, { kind: 'reserved', call, reservation,
    request_sha256: crypto.createHash('sha256').update(body).digest('hex'), timestamp: new Date().toISOString() });
  let charged = reservation;
  const entry = { kind: 'settled', call };
  try {
    const response = await fetch(url, options);
    entry.http_status = response.status;
    const payload = await response.clone().json();
    const usage = payload.usage;
    if (Number.isSafeInteger(usage?.input_tokens) && Number.isSafeInteger(usage?.output_tokens)) {
      charged = (usage.input_tokens * protocol.input_usd_per_million
        + usage.output_tokens * protocol.output_usd_per_million) / 1e6;
      entry.input_tokens = usage.input_tokens;
      entry.output_tokens = usage.output_tokens;
    }
    entry.response_id = payload.id;
    entry.model = payload.model;
    const outputText = (payload.output ?? []).flatMap(item => item.content ?? [])
      .filter(item => item.type === 'output_text').map(item => item.text).join('');
    try {
      const structured = JSON.parse(outputText);
      if (['in_scope', 'topic_outside_scope', 'system_limit', 'ambiguous'].includes(structured.decision)) {
        entry.structured_decision = structured.decision;
      }
      if (structured.intent) {
        const value = structured.intent;
        entry.structured_intent = Object.fromEntries(Object.entries({ name: intentNames, attack: attacks,
          origin: origins, relation: relations }).map(([key, allowed]) => [key, allowed.includes(value[key]) ? value[key] : '[invalid]']));
        if (Number.isFinite(value.confidence)) entry.structured_intent.confidence = value.confidence;
        if (Array.isArray(value.evidence)) entry.structured_intent.evidence = value.evidence
          .filter(index => Number.isSafeInteger(index) && index >= 0 && index < 128).slice(0, 8);
      }
    } catch {}
    return response;
  } catch (error) {
    entry.error_name = error.name;
    throw error;
  } finally {
    reserved -= reservation;
    spent += charged;
    await append(ledgerPath, { ...entry, charged_upper_usd: charged });
  }
};
const provider = createOpenAI({ apiKey: process.env.OPENAI_API_KEY, fetch: guardedFetch });
const settings = { model: provider(protocol.model), maxOutputTokens: protocol.max_output_tokens,
  timeoutMs: 30000, providerOptions: { openai: { reasoningEffort: 'none', store: false } } };
const evaluate = { legacy_scope: createScopeEvaluator(settings), context_intent: createContextEvaluator(settings) };
const completed = new Set((await readLines(resultsPath)).map(row => row.id + ':' + row.profile));
let index = 0;
let processed = 0;
async function runCase(row) {
  const request = { text: row.text, messages: row.messages, tool: row.tool || undefined,
    systemPrompt: data.systemPrompt, identity: data.identity };
  const profiles = [...protocol.profiles];
  if (parseInt(crypto.createHash('sha256').update(row.id).digest('hex').slice(0, 2), 16) % 2) profiles.reverse();
  for (const profile of profiles) {
    if (stop || completed.has(row.id + ':' + profile)) continue;
    const started = Date.now();
    let decision;
    try { decision = await evaluate[profile](request); }
    catch (error) {
      decision = { classification: 'UNCERTAIN', allowed: false, status: error.name === 'TimeoutError' ? 504 : 503,
        reason: error.name === 'TimeoutError' ? 'scope_timeout' : 'scope_unavailable', error_name: error.name };
    }
    if (!stop) await append(resultsPath, { id: row.id, profile, decision, latency_ms: Date.now() - started });
    if (protocol.stop_on_operational_error && decision.status >= 500) {
      stop = true;
      stopReason ??= 'operational_failure';
    }
    processed++;
    if (processed % 10 === 0) console.log(JSON.stringify({ evaluated: processed, calls, spent_upper_usd: +spent.toFixed(6) }));
  }
}
const smokeIds = new Set([data.cases.find(row => row.cohort === 'research_held_participants' && row.policy_label === 0)?.id,
  data.cases.find(row => row.cohort === 'research_held_participants' && row.policy_label === 1)?.id, 'CONTROL_greeting_clean']);
const runCases = process.argv.includes('--smoke') ? data.cases.filter(row => smokeIds.has(row.id)) : data.cases;
await Promise.all(Array.from({ length: 2 }, async () => {
  while (index < runCases.length && !stop) await runCase(runCases[index++]);
}));
await serial;
const summary = { calls, spent_upper_usd: +spent.toFixed(6), budget_stopped: stopReason === 'budget', stop_reason: stopReason,
  decisions: (await readLines(resultsPath)).length, external_tools_executed: 0 };
await fs.writeFile(path.join(folder, 'api_summary.json'), JSON.stringify(summary, null, 2), { mode: 0o600 });
console.log(JSON.stringify(summary));
