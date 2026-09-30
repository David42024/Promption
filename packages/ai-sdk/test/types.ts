import { createPromption, createFilterApiTransport, createScopeEvaluator } from '../src/index.js';
import { wrapLanguageModel, generateText, streamText, tool, jsonSchema } from 'ai';

declare const baseModel: Parameters<typeof wrapLanguageModel>[0]['model'];
const identity = { userId: 'server-user', roles: ['customer'], authenticated: true };
const protection = createPromption({ baseUrl: 'http://localhost:8000', apiKey: 'server-only' });
const model = wrapLanguageModel({ model: baseModel, middleware: protection.middleware({ identity }) });
void generateText({ model, prompt: 'Hola' });
void streamText({ model, prompt: 'Hola' });
const catalog = tool({ inputSchema: jsonSchema<{ query: string }>({ type: 'object' }), execute: async input => input.query });
const protectedCatalog = protection.protectTool(catalog, { name: 'catalog', identity });
void generateText({ model, prompt: 'Consulta', tools: { catalog: protectedCatalog } });
void createFilterApiTransport({ baseUrl: 'http://localhost:8000', apiKey: 'server-only' });
const scoped = createPromption({ baseUrl: 'http://localhost:8000', apiKey: 'server-only',
  scopeEvaluator: createScopeEvaluator({ model: baseModel }) });
void generateText({ model: wrapLanguageModel({ model: baseModel, middleware: scoped.middleware({ identity }) }),
  system: 'Only answer shop questions', prompt: 'What products are available?' });
void scoped.checkScope('Question', { identity, systemPrompt: 'Only answer shop questions' });
