import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import readline from 'node:readline';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { createPromption, createContextEvaluator, PromptionError } from '../../packages/ai-sdk/src/index.js';
import { sha } from './api_budget.mjs';
import { CorpusBudget } from './corpus_budget.mjs';
import { refusalInstructions } from './corpus_judge.mjs';
import { AsyncLocalStorage } from 'node:async_hooks';
import { deepseekBody } from './deepseek_wire.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const directory = path.resolve(process.argv[2] ?? 'output/corpus_three_conditions_20261024');
if (!process.argv.includes('--allow-external')) throw Error('Explicit --allow-external is required');
const protocol = JSON.parse(fs.readFileSync(path.join(directory, 'protocol.json')));
for (const [name, expected] of Object.entries(protocol.code_sha256)) {
  if (sha(fs.readFileSync(path.join(root, name))) !== expected) throw Error('Frozen source changed: ' + name);
}
for (const [name, expected] of Object.entries(protocol.artifacts_sha256)) {
  if (sha(fs.readFileSync(path.join(directory, name))) !== expected) throw Error('Frozen data changed: ' + name);
}
const profileStudy = protocol.study === 'protection_profiles';
const precisionStudy = protocol.study === 'precision_three_conditions';
const precisionFollowup = protocol.study === 'precision_portable_followup';
const precisionRecovery = protocol.study === 'precision_groq_recovery';
const shopStudy = protocol.study === 'shop_mixed_three_conditions';
const luminaStudy = ['precision_lumina_three_conditions', 'precision_lumina_openai_three_conditions',
  'precision_lumina_gemini_three_conditions', 'precision_lumina_gemini_native_three_conditions','precision_lumina_deepseek_three_conditions'].includes(protocol.study);
if ((profileStudy ? protocol.planned_episodes !== 144 || protocol.cases !== 48
    || JSON.stringify(protocol.conditions) !== JSON.stringify(['conversational', 'balanced', 'strict'])
    : shopStudy ? protocol.cases !== 600 || protocol.planned_episodes !== 1800
      || JSON.stringify(protocol.conditions) !== JSON.stringify(['unprotected', 'prompt_only', 'promption'])
    : luminaStudy ? protocol.cases !== 120 || protocol.planned_episodes !== 360
      || JSON.stringify(protocol.conditions) !== JSON.stringify(['unprotected', 'prompt_only', 'promption'])
    : precisionRecovery ? protocol.cases !== 16 || protocol.planned_episodes !== 48
      || JSON.stringify(protocol.conditions) !== JSON.stringify(['unprotected', 'prompt_only', 'promption'])
    : precisionFollowup ? protocol.cases !== 48 || protocol.planned_episodes !== 48
      || JSON.stringify(protocol.conditions) !== JSON.stringify(['promption'])
    : precisionStudy ? protocol.cases !== 48 || protocol.planned_episodes !== 144
      || JSON.stringify(protocol.conditions) !== JSON.stringify(['unprotected', 'prompt_only', 'promption'])
      : protocol.planned_episodes !== 720)
    || protocol.repetitions !== 1 || protocol.budget_usd !==
      (['precision_lumina_openai_three_conditions','precision_lumina_gemini_three_conditions','precision_lumina_gemini_native_three_conditions','precision_lumina_deepseek_three_conditions','shop_mixed_three_conditions'].includes(protocol.study) ? 5 : luminaStudy ? 7 : 2)) throw Error('Unexpected protocol');
const settings = JSON.parse(fs.readFileSync(path.join(directory, 'settings.json')));
const cases = new Map(JSON.parse(fs.readFileSync(path.join(directory, 'cases_private.json'))).map(c => [c.id, c]));
const plan = JSON.parse(fs.readFileSync(path.join(directory, 'plan.json')));
if (luminaStudy && (cases.size !== 120 || [...cases.values()].some(c => c.corpus !== 'lumina')
    || plan.length !== 360 || new Set(plan.map(ep => ep.id)).size !== 360)) throw Error('Unexpected Lumina cohort');
const require = createRequire(path.join(root, 'demo/package.json'));
const { createOpenAI } = await import(pathToFileURL(require.resolve('@ai-sdk/openai')).href);
const { generateText, wrapLanguageModel, jsonSchema, tool, stepCountIs, Output } = await import(pathToFileURL(path.join(root, 'packages/ai-sdk/node_modules/ai/dist/index.mjs')).href)
  .catch(() => import(pathToFileURL(path.join(root, 'packages/ai-sdk/node_modules/ai/dist/index.js')).href));
const groq = protocol.provider === 'groq';
const deepseek = protocol.provider === 'deepseek';
const geminiNative = protocol.provider === 'gemini-native';
const gemini = protocol.provider === 'gemini' || geminiNative;
const googleFactory = geminiNative ? (await import('@ai-sdk/google')).createGoogleGenerativeAI : null;
let apiKey = deepseek ? parseEnv(fs.readFileSync(path.join(root, '.env.deepseek.local'), 'utf8')).DEEPSEEK_API_KEY : gemini ? parseEnv(fs.readFileSync(path.join(root, '.env.gemini.local'), 'utf8')).GEMINI_API_KEY
  : groq ? parseEnv(fs.readFileSync(path.join(root, '.env.groq.local'), 'utf8')).GROQ_API_KEY : process.env.OPENAI_API_KEY;
if (!apiKey && !groq && !gemini) {
  const credentialFile = path.resolve(root, '../promption_compe/.env.local');
  apiKey = parseEnv(fs.readFileSync(credentialFile, 'utf8')).OPENAI_API_KEY;
}
if (!apiKey) throw Error('Missing local provider credential');
const providerOptions = geminiNative ? { google: { thinkingConfig: { thinkingLevel: 'minimal', includeThoughts: false } } }
  : deepseek ? { openai: { forceReasoning: false, systemMessageMode: 'system', parallelToolCalls: false } }
  : { openai: gemini
  ? { reasoningEffort: 'minimal', forceReasoning: false, systemMessageMode: 'system', parallelToolCalls: false }
  : groq
  ? { reasoningEffort: 'low', forceReasoning: true, systemMessageMode: 'system', parallelToolCalls: false, store: false }
  : { reasoningEffort: 'none', parallelToolCalls: false, store: false } };
if (protocol.prior_ledger_file && protocol.prior_ledger_file !== 'prior_ledger.jsonl') throw Error('Unexpected prior ledger');
const budget = new CorpusBudget(directory, protocol, protocol.prior_ledger_file
  ? path.join(directory, protocol.prior_ledger_file) : path.join(root, 'output/api_primary_20261024/api_ledger.jsonl'));
const lock = path.join(directory, 'execution.lock');
fs.writeFileSync(lock, JSON.stringify({ pid: process.pid, at: new Date().toISOString() }), { flag: 'wx', mode: 0o600 });
const pending = new Map();
let rpcId = 0;
const worker = spawn(path.join(root, '.venv/bin/python'), [path.join(root, 'scripts/research/corpus_worker.py'), '--output', directory],
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
const schemas = { company_information: object(groq || gemini || deepseek ? { query: { type: 'string' } } : {}), web_open: object({ url: { type: 'string' } }),
  make_document: object({ title: { type: 'string' }, content: { type: 'string' }, format: { type: 'string', enum: ['pdf', 'docx', 'xlsx'] } }),
  read_internal_file: object({ path: { type: 'string' } }), set_internal_discount: object({ percent: { type: 'integer' } }) };
const operationalCodes = new Set(['GUARD_UNAVAILABLE', 'INVALID_GUARD_RESPONSE', 'CONTENT_TOO_LARGE', 'CONVERSATION_TOO_LARGE']);
const errorOutcome = error => ({
  status: error.control === 'operational' || error.scope?.control === 'operational'
    || error.scope?.status >= 500 || operationalCodes.has(error.code) || !(error instanceof PromptionError) ? 'operational' : 'blocked',
  reason: error.scope?.reason ?? error.code ?? error.name,
});

async function runEpisode(episode) {
  const c = cases.get(episode.case_id);
  const record = { ...episode, started_at: new Date().toISOString(), status: 'running', events: [],
    artifacts: [], tool_calls: 0, delivered: '', unauthorized_effect: false, simulated_sink: [] };
  const protectedRun = profileStudy || episode.condition === 'promption';
  const profile = profileStudy ? episode.condition : 'balanced';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new Error('Episode timeout')), protocol.episode_timeout_ms);
  const identity = { userId: 'synthetic-customer', roles: ['customer'], authenticated: true };
  const purpose = new AsyncLocalStorage();
  const providerFetch = (url, options) => {
    const request = JSON.parse(options.body);
    if (groq && request.model === 'qwen/qwen3.8-27b') options = { ...options, body: JSON.stringify({ ...request, reasoning_format: 'hidden' }) };
    return budget.request(url, options, { episode: episode.id, purpose: purpose.getStore() ?? 'generation' });
  };
  const provider = geminiNative ? googleFactory({ apiKey, fetch: providerFetch })
    : createOpenAI({ apiKey, baseURL: gemini ? 'https://generativelanguage.googleapis.com/v1beta/openai'
    : deepseek ? 'https://api.deepseek.com' : groq ? 'https://api.groq.com/openai/v1' : 'https://api.openai.com/v1', fetch: (url, options) => {
    const request = JSON.parse(options.body);
    if (groq && request.model === 'qwen/qwen3.8-27b') options = { ...options, body: JSON.stringify({ ...request, reasoning_format: 'hidden' }) };
    if (deepseek) options = { ...options, body: deepseekBody(options.body) };
    return budget.request(url, options, { episode: episode.id,
      purpose: purpose.getStore() ?? 'generation' });
  } });
  const providerModel = name => geminiNative ? provider(name) : groq || gemini || deepseek ? provider.chat(name) : provider(name);
  const scope = createContextEvaluator({ model: providerModel(protocol.scope_model), maxOutputTokens: protocol.max_output_tokens,
    timeoutMs: protocol.request_timeout_ms, providerOptions, schemaMode: groq || gemini || deepseek ? 'portable' : 'constrained' });
  let terminal = null;
  const rememberTerminal = (status, reason) => { terminal ??= { status, reason }; };
  const protection = createPromption({
    protection: profile,
    ...(protectedRun ? { protectedValues: [settings.secret] } : {}),
    transport: async request => {
      const decision = await rpc({ op: request.direction, text: request.text, messages: request.messages,
        isolate_history: request.isolateHistory === true, profile });
      record.events.push({ stage: 'python_guard', direction: request.direction, text_sha256: sha(request.text), decision });
      if (!decision.allowed) rememberTerminal(decision.status >= 500 || decision.reason === 'conversation_limit' || decision.reason === 'invalid_input' ? 'operational' : 'blocked', decision.reason);
      return { ...decision, requiresScopeReview: decision.requires_scope_review === true,
        requiresOutputGuard: decision.requires_output_guard === true,
        ...(decision.input_risk_score === null || decision.input_risk_score === undefined ? {} : { inputRiskScore: decision.input_risk_score }) };
    },
    scopeEvaluator: async request => {
      const decision = await purpose.run('context_scope', () => scope(request));
      record.events.push({ stage: 'context_scope', decision, proposed_tool: request.tool ?? null });
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
        record.simulated_sink.push(...(result.simulated_sink ?? []));
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
        const failure = errorOutcome(error);
        rememberTerminal(failure.status, failure.reason);
        controller.abort(new Error('Tool pipeline stopped'));
        throw error;
      }
    } };
  }
  const captured = wrapLanguageModel({ model: providerModel(protocol.generation_model), middleware: {
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
    const result = await generateText({ model, system: episode.condition === 'unprotected' ? settings.common_system : settings.protected_system,
      messages: [...c.history, { role: 'user', content: c.text }], tools,
      stopWhen: stepCountIs(protocol.max_model_steps), maxOutputTokens: protocol.max_output_tokens,
      maxRetries: 0, abortSignal: controller.signal,
      providerOptions,
      allowSystemInMessages: false,
      prepareStep: () => { if (terminal) throw Error('Pipeline stopped'); },
      onStepFinish: step => record.events.push({ stage: 'sdk_step', finishReason: step.finishReason,
        text: step.text, toolCalls: step.toolCalls, toolResults: step.toolResults, usage: step.usage }),
    });
    if (terminal) Object.assign(record, terminal);
    else if (result.finishReason === 'length' || result.finishReason === 'tool-calls' || !result.text.trim()) {
      Object.assign(record, { status: 'operational', reason: 'generation_incomplete' });
    } else Object.assign(record, { status: record.events.some(e => e.stage === 'sdk_decision' && e.action === 'CLARIFY') ? 'clarified' : 'answered',
      reason: record.events.some(e => e.stage === 'sdk_decision' && e.action === 'CLARIFY') ? 'fixed_clarification' : 'final_response', delivered: result.text });
  } catch (error) {
    Object.assign(record, terminal ?? errorOutcome(error));
    record.error = { name: error.name, code: error.code, scope: error.scope, control: error.control, reason: error.reason };
  } finally {
    clearTimeout(timeout);
    if (record.status === 'clarified') record.refusal_prediction = false;
    else if (record.status === 'blocked') record.refusal_prediction = true;
    else if (record.status === 'answered') {
      try {
        const evaluated = await purpose.run('refusal_judge', () => generateText({
          model: providerModel(protocol.refusal_judge_model),
          system: refusalInstructions,
          prompt: JSON.stringify({ request: c.text, history: c.history, response: record.delivered.replaceAll(settings.secret, '[SYNTHETIC_VALUE]') }),
          output: Output.object({ name: 'response_refusal', schema: jsonSchema({ type: 'object', additionalProperties: false,
            properties: { classification: { type: 'string', enum: ['refusal', 'answer', 'uncertain'] } }, required: ['classification'] }) }),
          maxOutputTokens: protocol.max_output_tokens, maxRetries: 0, abortSignal: AbortSignal.timeout(protocol.request_timeout_ms),
          allowSystemInMessages: false, providerOptions,
        }));
        record.refusal_judgment = evaluated.output;
        record.refusal_prediction = evaluated.output.classification === 'uncertain' ? null : evaluated.output.classification === 'refusal';
      } catch(error) { record.refusal_prediction = null; record.judge_error = { name: error.name, code: error.code }; }
    } else record.refusal_prediction = null;
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
