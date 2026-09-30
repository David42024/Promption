import { PromptionError } from './errors.js';

const serialize = value => typeof value === 'string' ? value : JSON.stringify(value);
const textOf = message => typeof message.content === 'string' ? message.content
  : (message.content ?? []).filter(part => part.type === 'text').map(part => part.text).join('\n');

function evidence(prompt) {
  const messages = [];
  for (const message of prompt) {
    if (message.role === 'system') continue;
    if (message.role === 'user' || message.role === 'assistant') {
      const content = textOf(message);
      if (content) messages.push({ role: message.role, content });
    }
    if (message.role === 'tool' || message.role === 'assistant') {
      for (const part of Array.isArray(message.content) ? message.content : []) {
        if (part.type !== 'tool-result') continue;
        const output = part.output ?? part.result;
        const content = serialize(output?.value ?? output);
        if (typeof content !== 'string') throw new PromptionError('INVALID_TOOL_CONTENT');
        messages.push({ role: 'tool', content, tool_name: part.toolName });
      }
    }
  }
  return messages;
}

function key(message) {
  let content = message.content;
  try { content = JSON.stringify(JSON.parse(content)); } catch {}
  return JSON.stringify([message.role, message.tool_name ?? '', content]);
}

export function conversationEvidence(prompt, retained = [], limits = {}) {
  const actual = evidence(prompt);
  const messages = retained.map(message => ({ ...message }));
  if (!messages.length) messages.push(...actual);
  else {
    const lastUser = actual.filter(message => message.role === 'user').at(-1);
    if (lastUser && key(lastUser) !== key(messages.filter(message => message.role === 'user').at(-1) ?? {})) {
      messages.push(lastUser);
    }
    const counts = new Map();
    for (const message of retained.filter(message => message.role === 'tool')) {
      counts.set(key(message), (counts.get(key(message)) ?? 0) + 1);
    }
    for (const message of actual.filter(message => message.role === 'tool')) {
      const remaining = counts.get(key(message)) ?? 0;
      if (remaining) counts.set(key(message), remaining - 1);
      else messages.push(message);
    }
  }
  if (messages.length > (limits.maxMessages ?? 128)) throw new PromptionError('CONVERSATION_TOO_LARGE');
  let characters = 0;
  for (const message of messages) {
    if (!['user', 'assistant', 'tool'].includes(message.role) || typeof message.content !== 'string') {
      throw new TypeError('Conversation evidence must have an untrusted origin and text');
    }
    characters += message.content.length;
  }
  if (characters > (limits.maxChars ?? 100000)) throw new PromptionError('CONVERSATION_TOO_LARGE');
  return messages;
}
