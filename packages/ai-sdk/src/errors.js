export class PromptionError extends Error {
  constructor(code, { status = 403, direction, reason, control, cause } = {}) {
    super(`Promption: ${code}`, { cause });
    this.name = "PromptionError";
    this.code = code;
    this.status = status;
    this.direction = direction;
    this.reason = reason;
    this.control = control ?? (status >= 500 ? 'operational'
      : code === 'TOOL_ACCESS_DENIED' || reason === 'insufficient_scope' ? 'authorization'
        : reason === 'malicious_input' ? 'injection' : reason === 'sensitive_output' ? 'output' : undefined);
  }
}
