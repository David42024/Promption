import { timingSafeEqual } from 'node:crypto';

export function trustedAIRequest(request) {
  const expected = process.env.CHAT_SERVICE_TOKEN;
  if (!expected) return false;
  const actual = Buffer.from(request.headers.get('x-chat-service-token') || '');
  const required = Buffer.from(expected);
  return actual.length === required.length && timingSafeEqual(actual, required);
}
