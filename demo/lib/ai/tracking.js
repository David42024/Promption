export function createTrackingModel(baseModel, onInitiated) {
  if (!baseModel) return baseModel;
  return new Proxy(baseModel, {
    get(target, prop, receiver) {
      if (prop === 'doStream') {
        return async (options, ...rest) => {
          options?.abortSignal?.throwIfAborted?.();
          onInitiated?.();
          return target.doStream(options, ...rest);
        };
      }
      if (prop === 'doGenerate') {
        return async (options, ...rest) => {
          options?.abortSignal?.throwIfAborted?.();
          onInitiated?.();
          return target.doGenerate(options, ...rest);
        };
      }
      return Reflect.get(target, prop, receiver);
    },
  });
}
