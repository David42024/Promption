export function deepseekBody(body) {
  const request = JSON.parse(body);
  delete request.store;
  delete request.reasoning_effort;
  request.thinking = { type: 'disabled' };
  if (request.response_format?.type === 'json_schema') {
    const schema = request.response_format.json_schema.schema;
    request.response_format = { type: 'json_object' };
    const instruction = '\nReturn only valid JSON conforming to this JSON schema: ' + JSON.stringify(schema);
    const system = request.messages.find(message => message.role === 'system');
    if (!system || typeof system.content !== 'string') throw Error('Structured evaluation requires a server system prompt');
    system.content += instruction;
  }
  for (const tool of request.tools ?? []) if (tool.function) delete tool.function.strict;
  return JSON.stringify(request);
}
