function callKey(part) {
  if (part.type !== 'tool-call' || typeof part.toolCallId !== 'string'
      || typeof part.toolName !== 'string' || part.toolCallId.length > 256
      || part.toolName.length > 256) return;
  let input = part.input;
  if (typeof input === 'string') {
    try { input = JSON.parse(input); } catch { return; }
  }
  try {
    const canonical = JSON.stringify(input, (_key, value) => value && typeof value === 'object'
      && !Array.isArray(value) ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))) : value);
    if (canonical === undefined || canonical.length > 32768) return;
    return JSON.stringify([part.toolCallId, part.toolName, canonical]);
  } catch { return; }
}

export function createToolSignatureStore() {
  const signatures = new Map();
  return {
    remember(part) {
      const signature = part.providerMetadata?.google?.thoughtSignature;
      const key = callKey(part);
      if (!key || typeof signature !== 'string' || !signature.length || signature.length > 65536
          || !/^[A-Za-z0-9+/=_-]+$/.test(signature)) return;
      signatures.set(key, signature);
      if (signatures.size > 32) signatures.delete(signatures.keys().next().value);
    },
    restore(prompt, permitted) {
      return prompt.map(message => message.role !== 'assistant' || !Array.isArray(message.content) ? message
        : { ...message, content: message.content.map(part => {
          if (part.type !== 'tool-call') return part;
          const key = callKey(part);
          const signature = key && permitted(part.toolName) ? signatures.get(key) : undefined;
          const google = part.providerOptions?.google;
          if (!signature && !google?.thoughtSignature) return part;
          const { thoughtSignature, ...other } = google && typeof google === 'object' ? google : {};
          return { ...part, providerOptions: { ...part.providerOptions,
            google: { ...other, ...(signature ? { thoughtSignature: signature } : {}) } } };
        }) });
    },
  };
}
