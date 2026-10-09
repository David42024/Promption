import { createTrackingModel } from "../../../../lib/ai/tracking.js";
import { createOpenAI } from '@ai-sdk/openai';
import { createScopeEvaluator } from '@promption/ai-sdk';
import { trustedAIRequest } from '../../../../lib/ai/trusted.js';
import { getModelProviderOptions, validateModelConfiguration } from '../../../../lib/ai/modelOptions.js';

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
  const requestId = request.headers.get('x-request-id') || body?.request_id || crypto.randomUUID();
  if (request.signal?.aborted) {
    return Response.json({
      classification: 'UNCERTAIN',
      reason: 'scope_unavailable',
      allowed: false,
      model: process.env.OPENAI_MODEL || null,
      provider_calls: 0,
      usage: null,
      request_id: requestId,
    }, { status: 499, headers: { 'x-request-id': requestId } });
  }
  let callInitiated = false;
  try {
    const provider = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const modelId = process.env.OPENAI_MODEL;
    const trackingModel = createTrackingModel(provider(modelId), () => { callInitiated = true; });
    const evaluate = createScopeEvaluator({
      model: trackingModel,
      providerOptions: getModelProviderOptions(modelId),
    });
    const decision = await evaluate({ text: body.text, systemPrompt: body.system_prompt,
      messages: body.messages, tool: body.tool, signal: request.signal,
      identity: { userId: body.identity?.user_id || 'anonymous', roles: body.identity?.roles || [],
        authenticated: body.identity?.authenticated === true } });
    return Response.json({
      ...decision,
      model: modelId,
      provider_calls: 1,
      request_id: requestId,
    }, { headers: { 'x-request-id': requestId } });
  } catch (error) {
    console.error('[ai/scope] evaluation failed', {
      name: typeof error?.name === 'string' ? error.name : 'UnknownError',
      code: typeof error?.code === 'string' ? error.code.slice(0, 80) : undefined,
      statusCode: Number.isInteger(error?.statusCode) ? error.statusCode : undefined,
      causeName: typeof error?.cause?.name === 'string' ? error.cause.name : undefined,
    });
    return Response.json({
      classification: 'UNCERTAIN',
      reason: 'scope_unavailable',
      allowed: false,
      model: process.env.OPENAI_MODEL || null,
      provider_calls: callInitiated ? 1 : 0,
      usage: null,
      request_id: requestId,
    }, { status: error instanceof TypeError ? 400 : 503, headers: { 'x-request-id': requestId } });
  }
}
