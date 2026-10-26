import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { CorpusBudget } from './corpus_budget.mjs';
import { sha } from './api_budget.mjs';
import { refusalInstructions } from './corpus_judge.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const directory = path.resolve(process.argv[2]);
if (!process.argv.includes('--allow-external')) throw Error('Explicit --allow-external required');
const protocol = JSON.parse(fs.readFileSync(path.join(directory, 'protocol.json')));
for (const [file, expected] of Object.entries(protocol.code_sha256)) {
  if (sha(fs.readFileSync(path.join(root, file))) !== expected) throw Error('Frozen code changed: ' + file);
}
if (protocol.prior_ledger_file !== 'prior_ledger.jsonl' || protocol.baseline_directory !== 'output/corpus_three_conditions_20261024') throw Error('Unexpected comparison');
const baseline = path.join(root, protocol.baseline_directory);
if (sha(fs.readFileSync(path.join(baseline, 'protocol.json'))) !== protocol.baseline_protocol_sha256) throw Error('Baseline changed');
if (fs.existsSync(path.join(directory, 'execution.lock'))) throw Error('Episode runner is still running');
const completed = fs.readdirSync(path.join(directory, 'episodes')).filter(name => name.endsWith('.json')).length;
if (completed !== 720) throw Error('Complete the new episodes first');
const lock = path.join(directory, 'baseline_rejudge.lock');
fs.writeFileSync(lock, JSON.stringify({ at: new Date().toISOString() }), { flag: 'wx', mode: 0o600 });
const cases = new Map(JSON.parse(fs.readFileSync(path.join(directory, 'cases_private.json'))).map(c => [c.id, c]));
const settings = JSON.parse(fs.readFileSync(path.join(directory, 'settings.json')));
const budget = new CorpusBudget(directory, protocol, path.join(directory, protocol.prior_ledger_file));
const require = createRequire(path.join(root, 'demo/package.json'));
const { createOpenAI } = await import(pathToFileURL(require.resolve('@ai-sdk/openai')).href);
const { generateText, jsonSchema, Output } = await import(pathToFileURL(path.join(root, 'packages/ai-sdk/node_modules/ai/dist/index.js')).href);
const apiKey = process.env.OPENAI_API_KEY ?? parseEnv(fs.readFileSync(path.join(root, '../promption_compe/.env.local'), 'utf8')).OPENAI_API_KEY;
if (!apiKey) throw Error('Missing local credential');
const records = fs.readdirSync(path.join(baseline, 'episodes')).filter(name => name.endsWith('_promption.json'))
  .map(name => JSON.parse(fs.readFileSync(path.join(baseline, 'episodes', name))))
  .filter(r => r.status === 'answered');
const pending = records.filter(r => !fs.existsSync(path.join(directory, 'baseline_judgments', r.id + '.json')));
let next = 0;
let completedThisRun = 0;
try {
  await Promise.all(Array.from({ length: 2 }, async () => {
    while (!budget.stopped && next < pending.length) {
      const record = pending[next++];
      const c = cases.get(record.case_id);
      const provider = createOpenAI({ apiKey, baseURL: 'https://api.openai.com/v1', fetch: (url, options) =>
        budget.request(url, options, { episode: record.id, purpose: 'baseline_refusal_rejudge' }) });
      const judgment = { id: record.id, case_id: record.case_id, baseline_episode_sha256:
        sha(fs.readFileSync(path.join(baseline, 'episodes', record.id + '.json'))), status: 'pending' };
      try {
        const response = await generateText({ model: provider(protocol.refusal_judge_model), system: refusalInstructions,
          prompt: JSON.stringify({ request: c.text, history: c.history, response: record.delivered.replaceAll(settings.secret, '[SYNTHETIC_VALUE]') }),
          output: Output.object({ name: 'response_refusal', schema: jsonSchema({ type: 'object', additionalProperties: false,
            properties: { classification: { type: 'string', enum: ['refusal', 'answer', 'uncertain'] } }, required: ['classification'] }) }),
          maxOutputTokens: protocol.max_output_tokens, maxRetries: 0, abortSignal: AbortSignal.timeout(protocol.request_timeout_ms),
          allowSystemInMessages: false, providerOptions: { openai: { reasoningEffort: 'none', store: false } } });
        judgment.classification = response.output.classification;
        judgment.refusal_prediction = response.output.classification === 'uncertain' ? null : response.output.classification === 'refusal';
        judgment.status = 'judged';
      } catch (error) { judgment.status = 'unclassified'; judgment.error_name = error.name; judgment.refusal_prediction = null; }
      fs.writeFileSync(path.join(directory, 'baseline_judgments', record.id + '.json'), JSON.stringify(judgment, null, 2), { mode: 0o600 });
      completedThisRun++;
      if (completedThisRun % 6 === 0) console.log(JSON.stringify({ baseline_rejudged: completedThisRun, remaining: pending.length - completedThisRun,
        accounted_upper_usd: +budget.total().toFixed(6), api_calls: budget.calls }));
    }
  }));
} finally {
  fs.rmSync(lock, { force: true });
  const summary = { baseline_answers_planned: records.length,
    baseline_answers_recorded: fs.readdirSync(path.join(directory, 'baseline_judgments')).filter(n => n.endsWith('.json')).length,
    accounted_upper_usd: budget.total(), api_calls: budget.calls, stopped: budget.stopped };
  fs.writeFileSync(path.join(directory, 'baseline_rejudge_summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary));
}
