export function createTrackingModel(baseModel, onInitiated, onUsage) {
  if (!baseModel) return baseModel;
  return new Proxy(baseModel, {
    get(target, prop, receiver) {
      if (prop === 'doStream') {
        return async (options, ...rest) => {
          options?.abortSignal?.throwIfAborted?.();
          onInitiated?.();
          const result = await target.doStream(options, ...rest);
          if (!onUsage || !result.stream) return result;
          return { ...result, stream: result.stream.pipeThrough(new TransformStream({
            transform(chunk, controller) {
              if (chunk.type === 'finish') onUsage(chunk.usage);
              controller.enqueue(chunk);
            },
          })) };
        };
      }
      if (prop === 'doGenerate') {
        return async (options, ...rest) => {
          options?.abortSignal?.throwIfAborted?.();
          onInitiated?.();
          const result = await target.doGenerate(options, ...rest);
          onUsage?.(result.usage);
          return result;
        };
      }
      return Reflect.get(target, prop, receiver);
    },
  });
}
