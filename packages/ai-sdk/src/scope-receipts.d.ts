import type { ScopeRequest, ScopeEvaluator } from './index.js';

export interface ScopeReceiptBinding {
  request_id: string;
  tenant_id: string;
  conversation_id: string;
}
export interface ScopeReceiptOptions {
  receipts?: unknown;
  binding?: ScopeReceiptBinding;
  model: string;
  secret?: string;
  requestId?: string;
  onReceipt?: (receipt: string) => void;
}
export function issueScopeReceipt(request: ScopeRequest, binding: ScopeReceiptBinding,
  model: string, secret: string, now?: number): string | null;
export function verifyScopeReceipt(receipt: unknown, request: ScopeRequest, binding: ScopeReceiptBinding,
  model: string, secret: string, now?: number): boolean;
export function withScopeReceipts(evaluate: ScopeEvaluator, options: ScopeReceiptOptions): ScopeEvaluator;
