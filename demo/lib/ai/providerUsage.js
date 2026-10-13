export function providerUsage(usage) {
  const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  const promptTokens = number(usage?.inputTokens?.total ?? usage?.inputTokens ?? usage?.promptTokens);
  const completionTokens = number(usage?.outputTokens?.total ?? usage?.outputTokens ?? usage?.completionTokens);
  const totalTokens = number(usage?.totalTokens) ?? (promptTokens !== null && completionTokens !== null ? promptTokens + completionTokens : null);
  const reasoningTokens = number(usage?.outputTokens?.reasoning ?? usage?.outputTokenDetails?.reasoningTokens ?? usage?.reasoningTokens);
  return { promptTokens, completionTokens, totalTokens, reasoningTokens,
    hasUsage: [promptTokens, completionTokens, totalTokens, reasoningTokens].some(value => value !== null) };
}
