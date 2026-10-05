import { createOpenAI } from '@ai-sdk/openai';
import { createScopeEvaluator } from '@promption/ai-sdk';
import { trustedAIRequest } from '../../../../lib/ai/trusted.js';

export const runtime = 'nodejs';
export const maxDuration = 60;

export async function POST(request) {
  if (!trustedAIRequest(request)) return Response.json({ error: 'No autorizado' }, { status: 401 });
  if (!process.env.OPENAI_API_KEY || !process.env.OPENAI_MODEL) {
    return Response.json({ error: 'Evaluación de alcance no configurada' }, { status: 503 });
  }
  let body;
  try { body = await request.json(); }
  catch { return Response.json({ error: 'JSON inválido' }, { status: 400 }); }
  try {
    const provider = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const evaluate = createScopeEvaluator({ model: provider(process.env.OPENAI_MODEL) });
    const decision = await evaluate({ text: body.text, systemPrompt: body.system_prompt,
      messages: body.messages, tool: body.tool, signal: request.signal,
      identity: { userId: body.identity?.user_id || 'anonymous', roles: body.identity?.roles || [],
        authenticated: body.identity?.authenticated === true } });
    return Response.json(decision);
  } catch (error) {
    console.error('[ai/scope] evaluation failed', {
      name: typeof error?.name === 'string' ? error.name : 'UnknownError',
      code: typeof error?.code === 'string' ? error.code.slice(0, 80) : undefined,
      statusCode: Number.isInteger(error?.statusCode) ? error.statusCode : undefined,
      causeName: typeof error?.cause?.name === 'string' ? error.cause.name : undefined,
    });
    return Response.json({ classification: 'UNCERTAIN', reason: 'scope_unavailable', allowed: false },
      { status: error instanceof TypeError ? 400 : 503 });
  }
}
