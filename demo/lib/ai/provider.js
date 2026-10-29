import { createDeepSeek } from '@ai-sdk/deepseek';
import { createOpenAI } from '@ai-sdk/openai';
import { getModelProviderOptions } from './modelOptions.js';

export function getChatModelConfiguration(env = process.env, { requireTools = true } = {}) {
  const provider = (env.AI_PROVIDER || 'openai').trim().toLowerCase();
  if (!['openai', 'deepseek'].includes(provider)) throw new TypeError('Proveedor de IA no admitido');
  const prefix = provider === 'deepseek' ? 'DEEPSEEK' : 'OPENAI';
  const apiKey = env[`${prefix}_API_KEY`];
  const model = env[`${prefix}_MODEL`];
  const toolModel = env[`${prefix}_TOOL_MODEL`] || (!requireTools ? model : undefined);
  if (![apiKey, model, toolModel].every(value => typeof value === 'string' && value.trim())) {
    throw new TypeError('Configuración del proveedor de IA incompleta');
  }
  const baseURL = provider === 'deepseek' ? env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com' : undefined;
  return { provider, apiKey, baseURL, model, toolModel };
}

export function createChatProvider(config, options = {}) {
  return config.provider === 'deepseek'
    ? createDeepSeek({ apiKey: config.apiKey, baseURL: config.baseURL, ...options })
    : createOpenAI({ apiKey: config.apiKey, ...options });
}

export function getChatProviderOptions(config, modelId, overrides = {}) {
  return config.provider === 'deepseek'
    ? { deepseek: { thinking: { type: 'disabled' } } }
    : getModelProviderOptions(modelId, overrides);
}
