export class PromptionError extends Error {
  constructor(code, { status = 403, direction, reason, policyId, cause } = {}) {
    super(`Promption: ${code}`, { cause });
    this.name = "PromptionError";
    this.code = code;
    this.status = status;
    this.direction = direction;
    this.reason = reason;
    this.policyId = typeof policyId === 'string' && /^[a-zA-Z0-9_.-]{1,96}$/.test(policyId) ? policyId : undefined;
  }
}
