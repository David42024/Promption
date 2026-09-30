import { test } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MarkdownMessage, { safeMarkdownUrl } from "../app/chat/MarkdownMessage.mjs";

const render = text => renderToStaticMarkup(React.createElement(MarkdownMessage, { text }));

test("chat renders headings, emphasis, nested lists, quotes and fenced code", () => {
  const html = render("## Catálogo\n\n**Disponible** y *nuevo*\n\n1. Portátiles\n   - Gaming\n\n> Envío público\n\n```js\nconst stock = '<script>';\n```\n\nUsa `SKU`.\n\n---");
  for (const fragment of ["<h2>Catálogo</h2>", "<strong>Disponible</strong>", "<em>nuevo</em>",
    "<ol>", "<ul>", "<blockquote>", '<code class="language-js">', "&lt;script&gt;", "<code>SKU</code>", "<hr/>"]) {
    assert.ok(html.includes(fragment), fragment);
  }
});

test("GFM tables scroll and task lists are disabled", () => {
  const html = render("| Producto | Cantidad |\n| --- | ---: |\n| Portátil | 3 |\n\n- [x] Revisado\n- [ ] Pendiente\n\n~~Anterior~~");
  for (const fragment of ['class="chat-markdown-table"', 'aria-label="Tabla del mensaje"',
    "<table>", "<thead>", "<td>Portátil</td>", '<input type="checkbox" disabled=""', "<del>Anterior</del>"]) {
    assert.ok(html.includes(fragment), fragment);
  }
});

test("safe links and GFM autolinks keep external navigation isolated", () => {
  const html = render("[Iniciar sesión](/login)\n\n[Referencia](https://example.org/docs)\n\nhttps://example.org/help");
  assert.ok(html.includes('<a href="/login">Iniciar sesión</a>'));
  assert.equal((html.match(/rel="noopener noreferrer"/g) || []).length, 2);
  assert.equal((html.match(/referrerPolicy="no-referrer"/g) || []).length, 2);
  assert.equal((html.match(/target="_blank"/g) || []).length, 2);
});

for (const url of ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>alert(1)</script>",
  "vbscript:msgbox(1)", "file:///etc/passwd", "blob:https://example.org/id", "//example.org/pixel",
  "/\\example.org/pixel", "https://user:password@example.org", "java\nscript:alert(1)",
  "https://example.org/\u0000bad", "mailto:someone@example.org"]) {
  test(`URL policy rejects ${JSON.stringify(url)}`, () => assert.equal(safeMarkdownUrl(url), ""));
}

for (const payload of [
  '[Ataque](javascript:alert%281%29)', '[Ataque](JaVaScRiPt:alert%281%29)',
  '[Ataque](javascript&#58;alert%281%29)', '[Ataque](data:text/html;base64,PHNjcmlwdD4=)',
  '<script>alert(document.cookie)</script>', '<img src=x onerror="alert(1)">',
  '<svg onload="alert(1)"><a href="javascript:alert(1)">Ataque</a></svg>',
  '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
  '<form action="https://example.org"><input name="password"></form>',
  '<a href="https://example.org" onclick="alert(1)" style="background:url(https://example.org/pixel)">Ataque</a>',
  '<style>body { display:none }</style>',
]) {
  test(`untrusted Markdown cannot create active HTML: ${payload.slice(0, 45)}`, () => {
    const html = render(payload);
    assert.doesNotMatch(html, /<(script|iframe|svg|img|form|style)\b/i);
    assert.doesNotMatch(html, /\s(?:onerror|onclick|onload|srcdoc|style)=/i);
    assert.doesNotMatch(html, /href="(?:javascript|data|vbscript):/i);
  });
}

test("Markdown images become explicit links and never fetch tracking pixels", () => {
  const html = render('![Gráfico](https://example.org/pixel?value=private)');
  assert.doesNotMatch(html, /<img\b|\ssrc=/i);
  assert.ok(html.includes('href="https://example.org/pixel?value=private"'));
  assert.ok(html.includes('🖼️ Gráfico'));
});

test("dangerous image URLs keep only their readable alternative text", () => {
  const html = render('![Gráfico](javascript:alert%281%29)');
  assert.ok(html.includes('🖼️ Gráfico'));
  assert.doesNotMatch(html, /<a\b|<img\b|href=/);
});

test("plain text, line breaks and partial Markdown remain readable", () => {
  const html = render('Hola\nSegunda línea\n\n**incompleto');
  assert.ok(html.includes('Hola\nSegunda línea'));
  assert.ok(html.includes('**incompleto'));
  assert.equal(render(undefined), '<div class="chat-markdown"></div>');
});

test("untrusted IDs from GFM footnotes cannot clobber document properties", () => {
  const html = render('Nota[^location]\n\n[^location]: Texto público');
  assert.doesNotMatch(html, /\bid="(?:location|__proto__|constructor)"/);
  assert.ok(html.includes('Texto público'));
});
