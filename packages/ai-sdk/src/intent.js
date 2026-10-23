export const intentNames = ['social', 'public_information', 'document_creation', 'web_retrieval',
  'clarification', 'security_discussion', 'protected_information', 'instruction_override',
  'privilege_escalation', 'other', 'unknown'];
export const attacks = ['none', 'instruction_override', 'secret_extraction', 'system_prompt_extraction',
  'privilege_escalation', 'indirect_injection', 'unknown'];
export const relations = ['standalone', 'follow_up', 'quoted', 'unresolved'];
export const origins = ['none', 'user', 'tool', 'mixed'];

export function validateIntent(value) {
  if (!value || !intentNames.includes(value.name) || !attacks.includes(value.attack)
      || !relations.includes(value.relation) || !origins.includes(value.origin)
      || !Number.isFinite(value.confidence) || value.confidence < 0 || value.confidence > 1
      || !Array.isArray(value.evidence) || value.evidence.length > 8
      || value.evidence.some(index => !Number.isSafeInteger(index) || index < 0 || index >= 128)
      || new Set(value.evidence).size !== value.evidence.length
      || (value.attack === 'none' && value.origin !== 'none')
      || (!['none', 'unknown'].includes(value.attack) && value.origin === 'none')) {
    throw new TypeError('Invalid canonical intent assessment');
  }
  return { name: value.name, attack: value.attack, relation: value.relation,
    origin: value.origin, confidence: value.confidence, evidence: [...value.evidence] };
}
