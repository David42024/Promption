export class PromptionError extends Error {
  constructor(code, { status = 403, direction, cause } = {}) {
    super(`Promption: ${code}`, { cause });
    this.name = "PromptionError";
    this.code = code;
    this.status = status;
    this.direction = direction;
  }
}
