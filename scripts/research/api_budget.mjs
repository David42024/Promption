import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export const sha = value => crypto.createHash('sha256').update(value).digest('hex');
export const lines = file => fs.existsSync(file) ? fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(JSON.parse) : [];

export class BudgetStop extends Error {
  constructor(code) { super(code); this.name = 'BudgetStop'; this.code = code; }
}

export class ApiBudget {
  constructor(directory, protocol, fetchImpl = fetch) {
    if (protocol.budget_usd !== 2 || protocol.max_api_calls > 600) throw Error('Unexpected authorization bounds');
    this.directory = directory;
    this.protocol = protocol;
    this.fetchImpl = fetchImpl;
    this.file = path.join(directory, 'api_ledger.jsonl');
    this.reservations = new Map();
    this.calls = 0;
    this.stopped = false;
    for (const entry of lines(this.file)) {
      if (entry.kind === 'reserved') { this.calls = Math.max(this.calls, entry.call); this.reservations.set(entry.call, entry.reserved_usd); }
      if (entry.kind === 'settled') this.reservations.set(entry.call, entry.charged_upper_usd);
    }
  }
  total() { return [...this.reservations.values()].reduce((a, b) => a + b, 0); }
  append(value) { fs.appendFileSync(this.file, JSON.stringify({ ...value, at: new Date().toISOString() }) + '\n', { mode: 0o600 }); }
  async request(url, options, context) {
    const endpoint = new URL(url);
    if (endpoint.origin !== 'https://api.openai.com' || endpoint.pathname !== '/v1/responses') throw Error('Unexpected API endpoint');
    const body = typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString();
    const request = JSON.parse(body);
    const rates = this.protocol.rates_usd_per_million[request.model];
    if (!rates || request.store !== false || request.max_output_tokens !== this.protocol.max_output_tokens
        || request.reasoning?.effort !== 'none' || request.tools?.some(t => t.type !== 'function')) throw Error('Unexpected API request configuration');
    const reserve = ((Buffer.byteLength(body) + 4000) * rates.input + this.protocol.max_output_tokens * rates.output) / 1e6;
    if (this.stopped || this.calls >= this.protocol.max_api_calls || this.total() + reserve > this.protocol.budget_usd) {
      this.stopped = true;
      throw new BudgetStop('BUDGET_OR_CALL_LIMIT');
    }
    const call = ++this.calls;
    this.reservations.set(call, reserve);
    fs.writeFileSync(path.join(this.directory, 'requests', `${call}.json`), body, { mode: 0o600 });
    this.append({ kind: 'reserved', call, reserved_usd: reserve, model: request.model,
      request_sha256: sha(body), episode: context.episode, purpose: context.purpose });
    let charged = reserve;
    const entry = { kind: 'settled', call, episode: context.episode, purpose: context.purpose };
    try {
      const response = await this.fetchImpl(url, { ...options, redirect: 'error',
        signal: AbortSignal.any([...(options.signal ? [options.signal] : []), AbortSignal.timeout(this.protocol.request_timeout_ms)]) });
      entry.http_status = response.status;
      const payload = await response.clone().json();
      if (Number.isSafeInteger(payload.usage?.input_tokens) && Number.isSafeInteger(payload.usage?.output_tokens)) {
        charged = (payload.usage.input_tokens * rates.input + payload.usage.output_tokens * rates.output) / 1e6;
        entry.usage = payload.usage;
        entry.response_id = payload.id;
        entry.actual_model = payload.model;
        if (charged > reserve || payload.model !== request.model) this.stopped = true;
      } else {
        entry.usage_missing = true;
        this.stopped = true;
      }
      const saved = response.ok ? payload : { http_status: response.status,
        error: { code: payload.error?.code, type: payload.error?.type } };
      fs.writeFileSync(path.join(this.directory, 'api_responses', `${call}.json`), JSON.stringify(saved), { mode: 0o600 });
      return response;
    } catch (error) {
      entry.error_name = error.name;
      this.stopped = true;
      throw error;
    } finally {
      this.reservations.set(call, charged);
      this.append({ ...entry, charged_upper_usd: charged });
    }
  }
}
