import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import readline from 'node:readline';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { createPromption, createContextEvaluator, PromptionError } from '../../packages/ai-sdk/src/index.js';
import { ApiBudget, sha, lines } from './api_budget.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const directory = path.resolve(process.argv[2] ?? 'output/api_primary_20261024');
if (!process.argv.includes('--allow-external')) throw Error('Explicit --allow-external is required');
const protocol = JSON.parse(fs.readFileSync(path.join(directory, 'protocol.json')));
for (const [name, expected] of Object.entries(protocol.source_hashes)) {
  if (sha(fs.readFileSync(path.join(root, name))) !== expected) throw Error('Frozen source changed: ' + name);
}
for (const [name, expected] of Object.entries(protocol.artifact_hashes)) {
  if (sha(fs.readFileSync(path.join(directory, name))) !== expected) throw Error('Frozen data changed: ' + name);
}
if (protocol.planned_episodes !== 144 || protocol.repetitions !== 3 || protocol.budget_usd !== 2) throw Error('Unexpected protocol');
const settings = JSON.parse(fs.readFileSync(path.join(directory, 'settings.json')));
const cases = new Map(JSON.parse(fs.readFileSync(path.join(directory, 'cases.json'))).map(c => [c.id, c]));
const plan = JSON.parse(fs.readFileSync(path.join(directory, 'plan.json')));
const require = createRequire(path.join(root, 'demo/package.json'));
const { createOpenAI } = await import(pathToFileURL(require.resolve('@ai-sdk/openai')).href);
const { generateText, wrapLanguageModel, jsonSchema, tool, stepCountIs } = await import(pathToFileURL(path.join(root, 'packages/ai-sdk/node_modules/ai/dist/index.mjs')).href)
  .catch(() => import(pathToFileURL(path.join(root, 'packages/ai-sdk/node_modules/ai/dist/index.js')).href));
let apiKey = process.env.OPENAI_API_KEY;
if (!apiKey) {
  const credentialFile = path.resolve(root, '../promption_compe/.env.local');
  apiKey = parseEnv(fs.readFileSync(credentialFile, 'utf8')).OPENAI_API_KEY;
}
if (!apiKey) throw Error('Missing local OpenAI credential');
const budget = new ApiBudget(directory, protocol);
const lock = path.join(directory, 'execution.lock');
fs.writeFileSync(lock, JSON.stringify({ pid: process.pid, at: new Date().toISOString() }), { flag: 'wx', mode: 0o600 });
const pending = new Map();
let rpcId = 0;
const worker = spawn(path.join(root, '.venv/bin/python'), [path.join(root, 'scripts/research/api_primary_worker.py'), 'serve', '--output', directory],
  { cwd: root, stdio: ['pipe', 'pipe', 'pipe'] });
const ready = new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(Error('Worker startup timeout')), 30000);
  const input = readline.createInterface({ input: worker.stdout });
  input.on('line', line => {
    let value;
    try { value = JSON.parse(line); } catch { return; }
    if (value.ready) { clearTimeout(timer); resolve(); }
    if (value.id && pending.has(value.id)) {
      const item = pending.get(value.id); pending.delete(value.id);
      clearTimeout(item.timer);
      if (value.error) item.reject(Error('PythonWorker:' + value.error)); else item.resolve(value.result);
    }
  });
  worker.once('exit', code => {
    clearTimeout(timer);
    reject(Error('Worker stopped:' + code));
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(Error('Worker stopped')); }
    pending.clear();
  });
});
worker.stderr.on('data', bytes => fs.appendFileSync(path.join(directory, 'worker.log'), bytes));
async function rpc(payload) {
  await ready;
  const id = ++rpcId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(Error('Worker RPC timeout')); }, 30000);
    pending.set(id, { resolve, reject, timer });
    worker.stdin.write(JSON.stringify({ id, ...payload }) + '\n');
  });
}

const policies = { company_information: { roles: ['customer'] }, web_open: { roles: ['customer'] },
  make_document: { roles: ['customer'] }, read_internal_file: { roles: ['admin'] }, set_internal_discount: { roles: ['admin'] } };
const object = properties => jsonSchema({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false });
const schemas = { company_information: object({}), web_open: object({ url: { type: 'string' } }),
  make_document: object({ title: { type: 'string' }, content: { type: 'string' }, format: { type: 'string', enum: ['pdf', 'docx', 'xlsx'] } }),
  read_internal_file: object({ path: { type: 'string' } }), set_internal_discount: object({ percent: { type: 'integer' } }) };
const operationalCodes = new Set(['GUARD_UNAVAILABLE', 'INVALID_GUARD_RESPONSE', 'CONTENT_TOO_LARGE', 'CONVERSATION_TOO_LARGE']);

async function runEpisode(episode) {
  const c = cases.get(episode.case_id);
  const record = { ...episode, started_at: new Date().toISOString(), status: 'running', events: [],
    artifacts: [], tool_calls: 0, delivered: '', unauthorized_effect: false };
  const protectedRun = episode.condition === 'promption';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new Error('Episode timeout')), protocol.episode_timeout_ms);
  const identity = { userId: 'synthetic-customer', roles: ['customer'], authenticated: true };
  const provider = createOpenAI({ apiKey, baseURL: 'https://api.openai.com/v1', fetch: (url, options) => {
    const request = JSON.parse(options.body);
    return budget.request(url, options, { episode: episode.id,
      purpose: request.model === protocol.scope_model ? 'context_scope' : 'generation' });
  } });
  const scope = createContextEvaluator({ model: provider(protocol.scope_model), maxOutputTokens: protocol.max_output_tokens,
    timeoutMs: protocol.request_timeout_ms, providerOptions: { openai: protocol.scope_options } });
  let terminal = null;
  const rememberTerminal = (status, reason) => { terminal ??= { status, reason }; };
  const protection = createPromption({
    transport: async request => {
      const decision = await rpc({ op: request.direction, text: request.text, messages: request.messages });
      record.events.push({ stage: 'python_guard', direction: request.direction, text_sha256: sha(request.text), decision });
      if (!decision.allowed) rememberTerminal(decision.status >= 500 ? 'operational' : 'blocked', decision.reason);
      return decision;
    },
    scopeEvaluator: async request => {
      const decision = await scope(request);
      record.events.push({ stage: 'context_scope', decision, proposed_tool: request.tool ?? null });
      if (!decision.allowed) rememberTerminal(decision.status >= 500 ? 'operational' : 'blocked', decision.reason);
      return decision;
    },
    onDecision: event => record.events.push({ stage: 'sdk_decision', ...event }),
  });
  const tools = {};
  for (const [name, info] of Object.entries(settings.tools)) {
    let created = [];
    const definition = tool({ description: info.description, inputSchema: schemas[name], strict: true,
      execute: async input => {
        if (record.tool_calls >= protocol.max_tool_calls) { rememberTerminal('operational', 'tool_limit'); throw Error('Tool limit'); }
        const result = await rpc({ op: 'tool', episode, name, input, call_index: record.tool_calls++ });
        record.events.push({ stage: 'mcp', name, input, ...result, artifacts: result.artifacts.map(a => ({ ...a, delivered: false })) });
        record.unauthorized_effect ||= result.unauthorized_effect;
        created = result.artifacts.map(a => ({ ...a, delivered: false }));
        record.artifacts.push(...created);
        if (!result.ok) {
          rememberTerminal(result.status ?? 'operational', result.reason ?? 'mcp_error');
          throw new PromptionError(result.status === 'blocked' ? 'CONTENT_BLOCKED' : 'GUARD_UNAVAILABLE');
        }
        return result.value;
      },
    });
    const secured = protectedRun ? protection.protectTool(definition, { name, identity, policy: policies[name],
      systemPrompt: settings.policy, originalText: c.text, securityMessages: c.history, signal: controller.signal }) : definition;
    tools[name] = { ...secured, execute: async (...args) => {
      try {
        const value = await secured.execute(...args);
        for (const artifact of created) artifact.delivered = true;
        return value;
      } catch (error) {
        rememberTerminal(operationalCodes.has(error.code) ? 'operational' : error instanceof PromptionError ? 'blocked' : 'operational', error.code ?? error.name);
        controller.abort(new Error('Tool pipeline stopped'));
        throw error;
      }
    } };
  }
  const captured = wrapLanguageModel({ model: provider(protocol.generation_model), middleware: {
    specificationVersion: 'v3', wrapGenerate: async ({ doGenerate }) => {
      const result = await doGenerate();
      record.events.push({ stage: 'model_candidate', content: result.content, finishReason: result.finishReason,
        usage: result.usage, model: result.response?.modelId });
      return result;
    },
  } });
  const model = protectedRun ? wrapLanguageModel({ model: captured, middleware: protection.middleware({
    identity, originalText: c.text, systemPrompt: settings.policy, securityMessages: c.history,
    signal: controller.signal, toolPolicies: policies,
  }) }) : captured;
  try {
    const result = await generateText({ model, system: settings.generation_system,
      messages: [...c.history, { role: 'user', content: c.text }], tools,
      stopWhen: stepCountIs(protocol.max_model_steps), maxOutputTokens: protocol.max_output_tokens,
      maxRetries: 0, abortSignal: controller.signal,
      providerOptions: { openai: protocol.generation_options },
      allowSystemInMessages: false,
      prepareStep: () => { if (terminal) throw Error('Pipeline stopped'); },
      onStepFinish: step => record.events.push({ stage: 'sdk_step', finishReason: step.finishReason,
        text: step.text, toolCalls: step.toolCalls, toolResults: step.toolResults, usage: step.usage }),
    });
    if (terminal) Object.assign(record, terminal);
    else if (result.finishReason === 'length' || result.finishReason === 'tool-calls' || !result.text.trim()) {
      Object.assign(record, { status: 'operational', reason: 'generation_incomplete' });
    } else Object.assign(record, { status: 'answered', reason: 'final_response', delivered: result.text });
  } catch (error) {
    Object.assign(record, terminal ?? { status: error instanceof PromptionError && !operationalCodes.has(error.code) ? 'blocked' : 'operational',
      reason: error.scope?.reason ?? error.code ?? error.name });
    record.error = { name: error.name, code: error.code, scope: error.scope };
  } finally {
    clearTimeout(timeout);
    record.finished_at = new Date().toISOString();
    fs.writeFileSync(path.join(directory, 'episodes', episode.id + '.json'), JSON.stringify(record, null, 2), { mode: 0o600 });
  }
  return record;
}

let next = 0;
let completedThisRun = 0;
const firstAt = process.argv.indexOf('--first');
const first = firstAt >= 0 ? Number(process.argv[firstAt + 1]) : Infinity;
if (!(first > 0)) throw Error('Invalid first limit');
const remaining = plan.filter(ep => !fs.existsSync(path.join(directory, 'episodes', ep.id + '.json'))).slice(0, first);
try {
  await ready;
  await Promise.all(Array.from({ length: protocol.concurrency }, async () => {
    while (!budget.stopped && next < remaining.length) {
      const episode = remaining[next++];
      const result = await runEpisode(episode);
      completedThisRun++;
      if (completedThisRun % 6 === 0 || completedThisRun === remaining.length) {
        console.log(JSON.stringify({ completed_this_run: completedThisRun, remaining_this_run: remaining.length - completedThisRun,
          api_calls: budget.calls, accounted_upper_usd: +budget.total().toFixed(6), last_status: result.status }));
      }
    }
  }));
} finally {
  worker.stdin.end();
  worker.kill();
  fs.rmSync(lock, { force: true });
  const count = fs.readdirSync(path.join(directory, 'episodes')).filter(f => f.endsWith('.json')).length;
  const status = { completed_episodes: count, planned_episodes: plan.length, api_calls: budget.calls,
    accounted_upper_usd: budget.total(), stopped: budget.stopped,
    protocol_sha256: sha(fs.readFileSync(path.join(directory, 'protocol.json'))) };
  fs.writeFileSync(path.join(directory, 'execution_summary.json'), JSON.stringify(status, null, 2));
  console.log(JSON.stringify(status));
}
