/** Keep only explicitly visible text parts, never reasoning or tool payloads. */
export function finalContentText(content) {
  if (typeof content === 'string') return content.trim();
  if (!Array.isArray(content)) return '';
  return content.filter(part => part && ['text', 'output_text'].includes(part.type)
    && typeof part.text === 'string' && part.thought !== true
    && (part.channel === undefined || part.channel === 'final'))
    .map(part => part.text).join('').trim();
}
