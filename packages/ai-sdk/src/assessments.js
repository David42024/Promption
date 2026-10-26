const controls = ['injection', 'scope', 'authorization'];
const states = ['allowed', 'denied', 'uncertain', 'not_evaluated', 'error'];

export const emptyAssessments = () => Object.fromEntries(controls.map(control => [control,
  { state: 'not_evaluated', reason: 'not_evaluated', source: control, evaluations: [] }]));

export function assess(prior, control, state, reason, source) {
  if (!controls.includes(control) || !states.includes(state)) throw new TypeError('Invalid assessment');
  const result = structuredClone(prior ?? emptyAssessments());
  const item = { state, reason, source };
  result[control] = { ...item, evaluations: [...result[control].evaluations, item] };
  return result;
}

export function validateAssessments(value) {
  if (!value || typeof value !== 'object' || controls.some(control => {
    const item = value[control];
    return !item || !states.includes(item.state) || !Array.isArray(item.evaluations)
      || item.evaluations.length > 128 || [item, ...item.evaluations].some(e =>
        !states.includes(e.state) || !/^[a-z][a-z0-9_]{0,63}$/.test(e.reason)
          || !/^[a-z][a-z0-9_]{0,63}$/.test(e.source));
  })) throw new TypeError('Invalid assessment response');
  return Object.fromEntries(controls.map(control => [control, structuredClone(value[control])]));
}

export function scopeAssessments(decision) {
  let result = emptyAssessments();
  if (decision.control === 'operational') return assess(result, 'scope', 'error', decision.reason, 'scope_evaluator');
  if (decision.intent) result = assess(result, 'injection', decision.intent.attack === 'none' ? 'allowed'
    : decision.intent.attack === 'unknown' ? 'uncertain' : 'denied',
  decision.intent.attack === 'none' ? 'no_attack_detected' : decision.intent.attack, 'context_evaluator');
  return assess(result, 'scope', decision.allowed ? 'allowed' : decision.classification === 'OUT_OF_SCOPE' ? 'denied' : 'uncertain',
    decision.reason, 'scope_evaluator');
}
