import type { LanguageModelMiddleware, LanguageModel } from "ai";

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
export interface ScopeUsage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  reasoning_tokens?: number | null;
}
export interface KnownUsage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  reasoning_tokens: number | null;
}
export interface UsageCoverage {
  calls_total: number;
  calls_with_usage: number;
  calls_without_usage: number;
  is_complete: boolean;
  fields: {
    prompt_tokens: boolean;
    completion_tokens: boolean;
    total_tokens: boolean;
    reasoning_tokens: boolean;
  };
}
export interface ExecutionMetrics {
  provider_calls: number;
  generation_calls: number;
  scope_calls: number;
  failed_calls: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  reasoning_tokens: number | null;
  known_usage: KnownUsage;
  usage_coverage: UsageCoverage;
  [key: string]: unknown;
}
export interface ScopeDecision {
  classification: "IN_SCOPE" | "OUT_OF_SCOPE" | "UNCERTAIN";
  reason: string;
  allowed: boolean;
  status: number;
  usage?: ScopeUsage | null;
  model?: string | null;
  provider_calls?: number;
  reused?: boolean;
}
export interface ScopeRequest {
  text: string;
  systemPrompt: string;
  identity: Identity;
  messages?: ConversationMessage[];
  tool?: { name: string; input: unknown; description?: string };
  signal?: AbortSignal;
  providerOptions?: Record<string, unknown>;
}
export type ScopeEvaluator = (request: ScopeRequest) => Promise<Pick<ScopeDecision, "classification" | "reason"> & { usage?: ScopeUsage | null; allowed?: boolean; status?: number; provider_calls?: number; reused?: boolean }>;
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
  systemPrompt?: string;
  identity: Identity;
  originalText?: string;
  securityMessages?: ConversationMessage[];
  signal?: AbortSignal;
  context?: Record<string, unknown>;
  toolPolicies?: Record<string, ToolPolicy>;
  includeReasoning?: boolean;
}
export interface ProtectToolOptions {
  systemPrompt?: string;
  originalText?: string;
  name: string;
  securityMessages?: ConversationMessage[];
  identity: Identity;
  policy: ToolPolicy;
  signal?: AbortSignal;
}
export type PromptionOptions = (FilterApiOptions | { transport: GuardTransport }) & {
  scopeEvaluator?: ScopeEvaluator;
  maxTextChars?: number;
  maxConversationMessages?: number;
  maxConversationChars?: number;
  maxStreamBytes?: number;
  earlyOutputCheckChars?: number;
  onDecision?: (event: { direction: Direction; allowed: boolean; action?: string; userId: string; scope?: ScopeDecision }) => void;
};
export class PromptionError extends Error {
  code: string;
  status: number;
  direction?: Direction;
  scope?: ScopeDecision;
  constructor(code: string, options?: { status?: number; direction?: Direction; cause?: unknown });
}
export function createFilterApiTransport(options: FilterApiOptions): GuardTransport;
export function createGuardEndpointTransport(options: GuardEndpointOptions): GuardTransport;
export function createScopeEvaluator(options: { model: LanguageModel; timeoutMs?: number; maxOutputTokens?: number; providerOptions?: Record<string, unknown> }): ScopeEvaluator;
export function createPromption(options: PromptionOptions): {
  check(text: string, options: Omit<GuardRequest, "text">): Promise<string>;
  checkScope(text: string, options: Omit<ScopeRequest, "text">): Promise<ScopeDecision>;
  middleware(options: MiddlewareOptions): LanguageModelMiddleware;
  protectTool<T extends { execute?: (...args: any[]) => any }>(definition: T, options: ProtectToolOptions): T;
};
export class MetricsAggregator {
  generationCalls: number;
  scopeCalls: number;
  failedCalls: number;
  constructor();
  addCall(options?: {
    callType?: string;
    calls?: number;
    promptTokens?: number | null;
    completionTokens?: number | null;
    totalTokens?: number | null;
    reasoningTokens?: number | null;
    hasUsage?: boolean | null;
    failed?: boolean;
    eventId?: string | null;
    metadata?: Record<string, unknown>;
  }): boolean;
  summary(): {
    provider_calls: number;
    generation_calls: number;
    scope_calls: number;
    failed_calls: number;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
    reasoning_tokens: number | null;
    known_usage: KnownUsage;
    usage_coverage: UsageCoverage;
  };
}
