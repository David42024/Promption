import { test } from 'node:test';
import assert from 'node:assert/strict';
import { POST } from '../app/api/ai/turn/route.js';

function makeTurnRequest(body, headers = {}) {
  return new Request('http://localhost:3000/api/ai/turn', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-chat-service-token': 'test-chat-token',
      ...headers,
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      original_text: 'Consulta de tienda',
      user_id: 'u-1',
      roles: ['customer'],
      authenticated: true,
      messages: [
        { role: 'system', content: 'Asistente de tienda oficial.' },
        { role: 'user', content: 'Consulta de tienda' },
      ],
      tools: [],
      ...body,
    }),
  });
}

function makeScopeResponse(decision = 'in_scope', usage = { prompt_tokens: 15, completion_tokens: 15, total_tokens: 30 }) {
  return new Response(JSON.stringify({
    id: 'resp-scope',
    status: 'completed',
    created_at: Math.floor(Date.now() / 1000),
    output: [
      {
        id: 'msg-scope',
        type: 'message',
        role: 'assistant',
        content: [
          {
            type: 'output_text',
            text: JSON.stringify({ assessment: 'Valido', decision }),
            annotations: [],
          },
        ],
      },
    ],
    usage: usage ? {
      input_tokens: usage.input_tokens ?? usage.prompt_tokens ?? 15,
      output_tokens: usage.output_tokens ?? usage.completion_tokens ?? 15,
      total_tokens: usage.total_tokens ?? 30,
    } : null,
  }), { status: 200, headers: { 'content-type': 'application/json' } });
}

function makeGenerationResponse(text = 'Hola desde la tienda', usage = { prompt_tokens: 15, completion_tokens: 15, total_tokens: 30 }) {
  const sseData = [
    'data: {"type":"response.output_item.added","output_index":0,"item":{"id":"msg-1","type":"message","role":"assistant","content":[]}}',
    `data: {"type":"response.output_text.delta","item_id":"msg-1","delta":${JSON.stringify(text)}}`,
    `data: {"type":"response.output_item.done","output_index":0,"item":{"id":"msg-1","type":"message","role":"assistant","content":[{"type":"output_text","text":${JSON.stringify(text)},"annotations":[]}]}}`,
    `data: {"type":"response.completed","response":{"usage":${JSON.stringify(usage ? { input_tokens: usage.input_tokens ?? usage.prompt_tokens ?? 15, output_tokens: usage.output_tokens ?? usage.completion_tokens ?? 15, total_tokens: usage.total_tokens ?? 30 } : null)}}}`,
    'data: [DONE]'
  ].join('\n\n') + '\n\n';
  return new Response(sseData, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

test('Reproduce Defect 2: POST aggregates scope 30 tokens and generation 30 tokens to total 60 tokens across 2 provider calls', async (t) => {
  const origEnv = { ...process.env };
  const origFetch = globalThis.fetch;
  process.env.CHAT_SERVICE_TOKEN = 'test-chat-token';
  process.env.CHAT_API_URL = 'http://127.0.0.1:8000';
  process.env.OPENAI_API_KEY = 'test-openai-key';
  process.env.OPENAI_MODEL = 'gpt-4o-mini';
  process.env.OPENAI_TOOL_MODEL = 'gpt-4o-mini';

  t.after(() => {
    process.env = origEnv;
    globalThis.fetch = origFetch;
  });

  let scopeFetchCount = 0;
  let genFetchCount = 0;

  globalThis.fetch = async (url, opts) => {
    const urlStr = String(url);
    // Filter API guard endpoint
    if (urlStr.includes('/api/v1/ai/guard')) {
      const gBody = opts?.body ? JSON.parse(opts.body) : {};
      return new Response(JSON.stringify({ allowed: true, text: gBody.text || 'Consulta de tienda', action: 'PASS', conversation_checked: true }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    // OpenAI API calls (scope generateText or generation streamText)
    const bodyStr = opts?.body ? String(opts.body) : '';
    if (bodyStr.includes('TRUSTED_APPLICATION_POLICY') || bodyStr.includes('scope_decision')) {
      scopeFetchCount++;
      return makeScopeResponse('in_scope', { prompt_tokens: 15, completion_tokens: 15, total_tokens: 30 });
    }

    genFetchCount++;
    return makeGenerationResponse('Hola desde la tienda', { prompt_tokens: 15, completion_tokens: 15, total_tokens: 30 });
  };

  const req = makeTurnRequest();
  const res = await POST(req);
  assert.equal(res.status, 200);
  const data = await res.json();

  assert.equal(data.provider_calls, 2);
  assert.equal(data.scope_calls, 1);
  assert.equal(data.generation_calls, 1);
  // Defect check: must be 60 tokens, not 30!
  assert.equal(data.usage.total_tokens, 60);
  assert.equal(data.usage.prompt_tokens, 30);
  assert.equal(data.usage.completion_tokens, 30);
  assert.equal(data.known_usage.total_tokens, 60);
  assert.equal(data.usage_coverage.is_complete, true);
  assert.equal(data.usage_coverage.calls_total, 2);
  assert.equal(data.usage_coverage.calls_with_usage, 2);
});

test('Scope with unknown usage leaves full total_tokens as null and identifies known subtotal', async (t) => {
  const origEnv = { ...process.env };
  const origFetch = globalThis.fetch;
  process.env.CHAT_SERVICE_TOKEN = 'test-chat-token';
  process.env.CHAT_API_URL = 'http://127.0.0.1:8000';
  process.env.OPENAI_API_KEY = 'test-openai-key';
  process.env.OPENAI_MODEL = 'gpt-4o-mini';
  process.env.OPENAI_TOOL_MODEL = 'gpt-4o-mini';

  t.after(() => {
    process.env = origEnv;
    globalThis.fetch = origFetch;
  });

  globalThis.fetch = async (url, opts) => {
    const urlStr = String(url);
    if (urlStr.includes('/api/v1/ai/guard')) {
      const gBody = opts?.body ? JSON.parse(opts.body) : {};
      return new Response(JSON.stringify({ allowed: true, text: gBody.text || 'Consulta de tienda', action: 'PASS', conversation_checked: true }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    const bodyStr = opts?.body ? String(opts.body) : '';
    if (bodyStr.includes('TRUSTED_APPLICATION_POLICY') || bodyStr.includes('scope_decision')) {
      // Scope returns null usage
      return makeScopeResponse('in_scope', null);
    }

    return makeGenerationResponse('Respuesta tienda', { prompt_tokens: 15, completion_tokens: 15, total_tokens: 30 });
  };

  const req = makeTurnRequest();
  const res = await POST(req);
  assert.equal(res.status, 200);
  const data = await res.json();

  assert.equal(data.provider_calls, 2);
  assert.equal(data.scope_calls, 1);
  assert.equal(data.generation_calls, 1);
  // Full total must be null because scope usage is unknown!
  assert.equal(data.usage.total_tokens, null);
  // Known subtotal must be 30
  assert.equal(data.known_usage.total_tokens, 30);
  assert.equal(data.usage_coverage.is_complete, false);
  assert.equal(data.usage_coverage.calls_without_usage, 1);
});

test('Scope failure before generation: generation is zero and partial scope metrics preserved', async (t) => {
  const origEnv = { ...process.env };
  const origFetch = globalThis.fetch;
  process.env.CHAT_SERVICE_TOKEN = 'test-chat-token';
  process.env.CHAT_API_URL = 'http://127.0.0.1:8000';
  process.env.OPENAI_API_KEY = 'test-openai-key';
  process.env.OPENAI_MODEL = 'gpt-4o-mini';
  process.env.OPENAI_TOOL_MODEL = 'gpt-4o-mini';

  t.after(() => {
    process.env = origEnv;
    globalThis.fetch = origFetch;
  });

  globalThis.fetch = async (url, opts) => {
    const urlStr = String(url);
    if (urlStr.includes('/api/v1/ai/guard')) {
      return new Response(JSON.stringify({ allowed: true, text: 'ok', action: 'PASS', conversation_checked: true }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    const bodyStr = opts?.body ? String(opts.body) : '';
    if (bodyStr.includes('TRUSTED_APPLICATION_POLICY') || bodyStr.includes('scope_decision')) {
      // Scope fails with 503
      return new Response(JSON.stringify({ error: 'Scope service unavailable' }), { status: 503, headers: { 'content-type': 'application/json' } });
    }
    assert.fail('Should not call generation model');
  };

  const req = makeTurnRequest();
  const res = await POST(req);
  assert.equal(res.status, 503);
  const data = await res.json();

  assert.equal(data.code, 'SCOPE_UNCERTAIN');
  assert.equal(data.scope_calls, 1);
  assert.equal(data.generation_calls, 0);
  assert.equal(data.provider_calls, 1);
});

test('Security block (CONTENT_BLOCKED) preserves code, status and prevents provider fallback', async (t) => {
  const origEnv = { ...process.env };
  const origFetch = globalThis.fetch;
  process.env.CHAT_SERVICE_TOKEN = 'test-chat-token';
  process.env.CHAT_API_URL = 'http://127.0.0.1:8000';
  process.env.OPENAI_API_KEY = 'test-openai-key';
  process.env.OPENAI_MODEL = 'gpt-4o-mini';
  process.env.OPENAI_TOOL_MODEL = 'gpt-4o-mini';

  t.after(() => {
    process.env = origEnv;
    globalThis.fetch = origFetch;
  });

  globalThis.fetch = async (url) => {
    const urlStr = String(url);
    if (urlStr.includes('/api/v1/ai/guard')) {
      return new Response(JSON.stringify({ allowed: false, text: '', action: 'BLOCK' }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    assert.fail('Should never reach model when input filter blocks');
  };

  const req = makeTurnRequest();
  const res = await POST(req);
  assert.equal(res.status, 403);
  const data = await res.json();
  assert.equal(data.code, 'CONTENT_BLOCKED');
  assert.equal(data.provider_calls, 0);
  assert.equal(data.generation_calls, 0);
  assert.equal(data.scope_calls, 0);
});
