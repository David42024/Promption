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

function mergeEvidence(retained, actual) {
  const left = retained.map(key), right = actual.map(key);
  const common = Array.from({ length: left.length + 1 }, () => new Uint16Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i--) {
    for (let j = right.length - 1; j >= 0; j--) {
      common[i][j] = left[i] === right[j] ? 1 + common[i + 1][j + 1]
        : Math.max(common[i + 1][j], common[i][j + 1]);
    }
  }
  const messages = [];
  let i = 0, j = 0;
  while (i < retained.length && j < actual.length) {
    if (left[i] === right[j]) { messages.push({ ...actual[j++] }); i++; }
    else if (common[i + 1][j] >= common[i][j + 1]) messages.push({ ...retained[i++] });
    else messages.push({ ...actual[j++] });
  }
  return messages.concat(retained.slice(i).map(message => ({ ...message })),
    actual.slice(j).map(message => ({ ...message })));
}

export function conversationEvidence(prompt, retained = [], limits = {}) {
  const actual = evidence(prompt);
  if (!Array.isArray(retained)) throw new TypeError('Retained conversation evidence must be an array');
  if (Math.max(retained.length, actual.length) > (limits.maxMessages ?? 128)) {
    throw new PromptionError('CONVERSATION_TOO_LARGE');
  }
  const messages = mergeEvidence(retained, actual);
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
