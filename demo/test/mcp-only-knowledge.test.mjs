import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

async function loadRoute(relative, prelude = '') {
  const source = await readFile(new URL(relative, import.meta.url), 'utf8');
  return import(`data:text/javascript;base64,${Buffer.from(prelude + source.replace(/^import .*;\r?\n/gm, '')).toString('base64')}`);
}

test('Legacy document listing and content access are disabled without reading files', async () => {
  const { GET } = await loadRoute('../app/api/docs/route.js');
  for (const path of ['/api/docs', '/api/docs?id=confidencial']) {
    const response = await GET(new Request(`http://localhost${path}`));
    assert.equal(response.status, 410);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const result = await response.json();
    assert.equal(result.code, 'DOCUMENT_VIEWER_DISABLED');
    assert.equal(result.body, undefined);
    assert.equal(result.docs, undefined);
  }
});

test('Chat forwards no Markdown document capabilities for authenticated users', async () => {
  const { POST } = await loadRoute('../app/api/chat/route.js', `
    const randomUUID = () => '11111111-1111-1111-1111-111111111111';
    const cookies = () => ({ get: () => undefined, set: () => {} });
    const GUEST_USER = {};
    const readSessionToken = () => ({ id: 'a', name: 'Admin', roles: ['admin'], authenticated: true });
  `);
  const originalFetch = globalThis.fetch;
  let payload;
  globalThis.fetch = async (_url, options) => {
    payload = JSON.parse(options.body);
    return Response.json({ reply: 'Respuesta mediante MCP', audit: [{ tool: 'getCatalogSummary', allowed: true }] });
  };
  try {
    const result = await POST(new Request('http://localhost/api/chat', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text: 'Consulta catálogo' }),
    }));
    assert.equal(result.status, 200);
    assert.deepEqual(payload.context.documents, []);
    assert.deepEqual(payload.user.roles, ['admin']);
    assert.equal((await result.json()).audit[0].tool, 'getCatalogSummary');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
