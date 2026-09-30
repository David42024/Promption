import type { LanguageModelMiddleware } from "ai";

export interface Identity {
  userId: string;
  roles: readonly string[];
  authenticated?: boolean;
}
export interface ConversationMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string;
}
export type Direction = "input" | "output";
export interface GuardRequest {
  text: string;
  direction: Direction;
  identity: Identity;
  signal?: AbortSignal;
  context?: Record<string, unknown>;
  messages?: ConversationMessage[];
}
export interface GuardResponse {
  allowed: boolean;
  text: string;
  action?: string;
  requiresOutputGuard?: boolean;
}
export type GuardTransport = (request: GuardRequest) => Promise<GuardResponse>;
export interface HttpOptions { fetch?: typeof globalThis.fetch; timeoutMs?: number; }
export interface FilterApiOptions extends HttpOptions {
  baseUrl: string;
  apiKey: string;
  tenantId?: string;
  useMl?: boolean;
}
export interface GuardEndpointOptions extends HttpOptions { url: string; token: string; }
export interface ToolPolicy { roles?: readonly string[]; }
export interface MiddlewareOptions {
  identity: Identity;
  originalText?: string;
  securityMessages?: ConversationMessage[];
  signal?: AbortSignal;
  context?: Record<string, unknown>;
  toolPolicies?: Record<string, ToolPolicy>;
  includeReasoning?: boolean;
}
export interface ProtectToolOptions {
  name: string;
  securityMessages?: ConversationMessage[];
  identity: Identity;
  policy?: ToolPolicy;
  signal?: AbortSignal;
}
export type PromptionOptions = (FilterApiOptions | { transport: GuardTransport }) & {
  maxTextChars?: number;
  maxConversationMessages?: number;
  maxConversationChars?: number;
  maxStreamBytes?: number;
  onDecision?: (event: { direction: Direction; allowed: boolean; action?: string; userId: string }) => void;
};
export class PromptionError extends Error {
  code: string;
  status: number;
  direction?: Direction;
  constructor(code: string, options?: { status?: number; direction?: Direction; cause?: unknown });
}
export function createFilterApiTransport(options: FilterApiOptions): GuardTransport;
export function createGuardEndpointTransport(options: GuardEndpointOptions): GuardTransport;
export function createPromption(options: PromptionOptions): {
  check(text: string, options: Omit<GuardRequest, "text">): Promise<string>;
  middleware(options: MiddlewareOptions): LanguageModelMiddleware;
  protectTool<T extends { execute?: (...args: any[]) => any }>(definition: T, options: ProtectToolOptions): T;
};
