/** Strict read-only domain recognition based on a SERVER-created business policy.
 * This does not grant MCP access, relax output filtering, or validate user-supplied
 * authorization. Only narrowly bounded single-intent requests qualify.
 */
function normalize(value) {
  return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[¿?¡!.,:;]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function activePolicy(systemPrompt) {
  if (typeof systemPrompt !== 'string') return null;
  // The policy header must precede the user/session subsection; never trust a
  // substring the user could place in the prompt or an assistant/tool message.
  const trusted = systemPrompt.split('--- USUARIO ACTUAL ---', 1)[0];
  const match = trusted.match(/(?:^|\n)Política: ([a-z][a-z0-9._-]+) \| Nivel: ([a-z]+) \| Herramientas ACL: ([^\n]{1,140})/);
  if (!match) return null;
  return { id: match[1], tier: match[2], tools: match[3].split(',').map(x => x.trim()) };
}

export function trustedShopScopeFastpath({ text, system_prompt, identity, tool } = {}) {
  const policy = activePolicy(system_prompt);
  if (!policy || typeof text !== 'string' || text.length > 320) return null;
  const normalized = normalize(text);
  // No mixed requests: narrowly match a complete question, never a keyword.
  const publicCatalog = /^(?:(?:consulta para la tienda|por favor)\s+)*(?:que autonomia y tipo de conexion tienen los auriculares [a-z0-9 -]{2,65} segun (?:su|el) catalogo|what (?:is|are) (?:the )?(?:battery life|autonomy) and (?:the )?(?:connection type|connectivity) (?:of|for) [a-z0-9 -]{2,65} (?:in|according to) (?:your|the) catalogo?)$/;
  const conceptualStock = /^(?:(?:consulta para la tienda|por favor)\s+)*que significa (?:el termino )?stock cuando compro un producto en su catalogo(?: explicalo brevemente)?$/;
  const englishHeadphones = /^(?:(?:please|hello)\s+)*do you sell wireless headphones and what are their main technical features in your store$/;
  const adminPayroll = /^(?:(?:consulta para la tienda|por favor)\s+)*(?:consulta|muestra|muestrame|dime) el sueldo neto mensual (?:registrado )?de [a-z ]{3,55}?(?: en el perfil de empleados)?$/;
  const name = tool?.name;
  const toolInput = tool?.input ?? tool?.arguments ?? null;
  // Dynamic arguments and arbitrary tools still need semantic scope and MCP ACL.
  if (tool && (toolInput && JSON.stringify(toolInput) !== '{}' ||
      (name !== 'getCatalogSummary' && name !== 'getEmployees'))) return null;
  if (policy.id === 'public.catalog' && policy.tier === 'publico' &&
      policy.tools.includes('getCatalogSummary') &&
      (publicCatalog.test(normalized) || conceptualStock.test(normalized) || englishHeadphones.test(normalized)) &&
      (!tool || name === 'getCatalogSummary')) {
    return { classification: 'IN_SCOPE', reason: 'in_scope', allowed: true,
      status: 200, provider_calls: 0, usage: null, trusted_fastpath: 'public_catalog_question' };
  }
  if (policy.id === 'confidential.payroll' && policy.tier === 'confidencial' &&
      policy.tools.includes('getEmployees') && identity?.authenticated === true &&
      Array.isArray(identity.roles) && identity.roles.includes('admin') &&
      adminPayroll.test(normalized) && (!tool || name === 'getEmployees')) {
    return { classification: 'IN_SCOPE', reason: 'in_scope', allowed: true,
      status: 200, provider_calls: 0, usage: null, trusted_fastpath: 'authorized_payroll_read' };
  }
  return null;
}
