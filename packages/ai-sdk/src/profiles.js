const profiles = Object.freeze({
  conversational: { inputUncertainty: 'review', scopeAmbiguity: 'clarify', reviewBlockThreshold: .85 },
  balanced: { inputUncertainty: 'review', scopeAmbiguity: 'clarify', reviewBlockThreshold: .75 },
  strict: { inputUncertainty: 'review', scopeAmbiguity: 'block', reviewBlockThreshold: .66 },
});

export function resolveProtection(value = {}) {
  if (typeof value === 'string') value = { profile: value };
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).some(key => !['profile', 'inputUncertainty', 'scopeAmbiguity', 'reviewBlockThreshold'].includes(key))) {
    throw new TypeError('Invalid protection settings');
  }
  const profile = value.profile === undefined ? 'balanced' : value.profile;
  if (typeof profile !== 'string' || !Object.hasOwn(profiles, profile)) throw new TypeError('Unknown protection profile');
  const result = { ...profiles[profile], ...value, profile };
  if (!['review', 'block'].includes(result.inputUncertainty)
      || !['clarify', 'block'].includes(result.scopeAmbiguity)) throw new TypeError('Invalid uncertainty action');
  if (typeof result.reviewBlockThreshold !== 'number' || !Number.isFinite(result.reviewBlockThreshold)
      || result.reviewBlockThreshold <= 0 || result.reviewBlockThreshold >= 1) throw new TypeError('Invalid review threshold');
  return Object.freeze(result);
}
