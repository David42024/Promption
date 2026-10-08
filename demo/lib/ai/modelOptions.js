/**
 * Centralized model options and provider configurations for @ai-sdk/openai.
 * Resolves reasoningEffort and tool options consistently across generation and scope evaluation.
 */

const REASONING_MODELS = /^(?:o[13](?:-mini|-preview)?|gpt-5(?:-(?:nano|mini))?(?:-\d{4}-\d{2}-\d{2})?)$/i;
const VALID_REASONING_EFFORTS = new Set(['low', 'medium', 'high', 'minimal']);

/**
 * Returns true if the model architecture supports reasoning effort options.
 * @param {string} [modelId]
 * @returns {boolean}
 */
export function isReasoningModel(modelId) {
  if (!modelId || typeof modelId !== 'string') return false;
  return REASONING_MODELS.test(modelId.trim());
}

/**
 * Validates a reasoning effort value. Throws TypeError if invalid.
 * @param {string} effort
 * @returns {string}
 */
export function validateReasoningEffort(effort) {
  if (typeof effort !== 'string' || !VALID_REASONING_EFFORTS.has(effort.toLowerCase())) {
    throw new TypeError(`Nivel de reasoningEffort no admitido: "${effort}". Valores válidos: low, medium, high, minimal.`);
  }
  return effort.toLowerCase();
}

/**
 * Resolves providerOptions for OpenAI models.
 * Applies reasoningEffort ONLY to models that support it, preventing API errors on standard models.
 * Preserves tool calling options (parallelToolCalls, maxToolCalls).
 *
 * @param {string} modelId
 * @param {object} [overrides]
 * @param {string} [overrides.reasoningEffort]
 * @param {boolean} [overrides.parallelToolCalls]
 * @param {number} [overrides.maxToolCalls]
 * @returns {{ openai?: Record<string, any> }}
 */
export function getModelProviderOptions(modelId, overrides = {}) {
  const options = {};

  if (isReasoningModel(modelId)) {
    const rawEffort = overrides.reasoningEffort || process.env.OPENAI_REASONING_EFFORT || 'minimal';
    options.reasoningEffort = validateReasoningEffort(rawEffort);
  }

  if (typeof overrides.parallelToolCalls === 'boolean') {
    options.parallelToolCalls = overrides.parallelToolCalls;
  }

  if (Number.isInteger(overrides.maxToolCalls)) {
    options.maxToolCalls = overrides.maxToolCalls;
  }

  return Object.keys(options).length > 0 ? { openai: options } : {};
}

/**
 * Validates environment configuration on startup.
 * @param {object} [env]
 */
export function validateModelConfiguration(env = process.env) {
  if (env.OPENAI_REASONING_EFFORT) {
    validateReasoningEffort(env.OPENAI_REASONING_EFFORT);
  }
}
