"""Optional sequence classifiers with complete, overlapping token coverage."""
import math

import numpy as np

from .exceptions import MLError, MLInferenceError, MLModelLoadError
from .ml_filter import MLResult


class SmallModelFilter:
    """Adapt a fine-tuned classifier to the ensemble without granting permissions."""

    def __init__(self, encode, predict_windows, *, threshold=0.9, window_tokens=510,
                 overlap_tokens=128, batch_size=16, max_windows=256):
        if not callable(encode) or not callable(predict_windows):
            raise TypeError("A tokenizer and window scorer are required")
        if (isinstance(threshold, bool) or not math.isfinite(threshold)
                or not 0 < threshold < 1):
            raise ValueError("Threshold must be strictly between zero and one")
        for value in (window_tokens, batch_size, max_windows):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("Window size, batch size and window limit must be positive integers")
        if (not isinstance(overlap_tokens, int) or isinstance(overlap_tokens, bool)
                or not 0 <= overlap_tokens < window_tokens):
            raise ValueError("Overlap must be smaller than the token window")
        self.encode = encode
        self.predict_windows = predict_windows
        self.threshold = threshold
        self.window_tokens = window_tokens
        self.overlap_tokens = overlap_tokens
        self.batch_size = batch_size
        self.max_windows = max_windows

    def analyze(self, text: str) -> MLResult:
        try:
            if not isinstance(text, str):
                raise ValueError("Text is required")
            tokens = list(self.encode(text))
            stride = self.window_tokens - self.overlap_tokens
            count = 1 + max(0, math.ceil((len(tokens) - self.window_tokens) / stride))
            if count > self.max_windows:
                raise MLInferenceError("Classifier token window limit exceeded")
            maximum = 0.0
            for offset in range(0, count, self.batch_size):
                windows = [tokens[index * stride:index * stride + self.window_tokens]
                           for index in range(offset, min(count, offset + self.batch_size))]
                probabilities = np.asarray(self.predict_windows(windows), dtype=float)
                if (probabilities.shape != (len(windows),) or not np.isfinite(probabilities).all()
                        or (probabilities < 0).any() or (probabilities > 1).any()):
                    raise MLInferenceError("Invalid classifier probabilities")
                maximum = max(maximum, float(probabilities.max()))
            return MLResult(maximum >= self.threshold, maximum, self.threshold, layer="small_model")
        except MLError:
            raise
        except Exception as exc:
            raise MLInferenceError("Small classifier inference failed") from exc

    def is_trained(self) -> bool:
        return True

    @property
    def is_loaded(self) -> bool:
        return True

    @classmethod
    def from_pretrained(cls, model_path_or_id, *, positive_labels=("MALICIOUS",),
                        threshold=0.9, revision=None, local_files_only=True, device="cpu",
                        max_tokens=512, overlap_tokens=128, batch_size=16, max_windows=256):
        """Load official Transformers locally by default; no remote code or implicit label index."""
        if (not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 2
                or not positive_labels or isinstance(positive_labels, str)
                or not all(isinstance(label, str) for label in positive_labels)):
            raise ValueError("Explicit positive labels and a valid token capacity are required")
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            options = {"local_files_only": local_files_only, "trust_remote_code": False}
            if revision is not None:
                options["revision"] = revision
            tokenizer = AutoTokenizer.from_pretrained(model_path_or_id, **options)
            model = AutoModelForSequenceClassification.from_pretrained(model_path_or_id, use_safetensors=True, **options)
            capacities = [getattr(tokenizer, "model_max_length", max_tokens),
                          getattr(model.config, "max_position_embeddings", max_tokens)]
            if any(isinstance(capacity, int) and max_tokens > capacity for capacity in capacities):
                raise ValueError("Token window exceeds model capacity")
            labels = {str(label).casefold(): int(index) for index, label in model.config.id2label.items()}
            indices = sorted({labels[label.casefold()] for label in positive_labels})
            if any(index < 0 or index >= model.config.num_labels for index in indices):
                raise ValueError("Invalid classifier label mapping")
            special_tokens = tokenizer.num_special_tokens_to_add(pair=False)
            model.to(device)
            model.eval()

            def encode(text):
                return tokenizer.encode(text, add_special_tokens=False, truncation=False)

            def predict(windows):
                encoded = [tokenizer.prepare_for_model(window, add_special_tokens=True,
                           return_attention_mask=True, truncation=False) for window in windows]
                inputs = tokenizer.pad(encoded, padding=True, return_tensors="pt")
                inputs = {key: value.to(device) for key, value in inputs.items()
                          if key in tokenizer.model_input_names}
                with torch.no_grad():
                    probabilities = torch.softmax(model(**inputs).logits, dim=-1)
                return probabilities[:, indices].sum(dim=-1).cpu().numpy()

            return cls(encode, predict, threshold=threshold, window_tokens=max_tokens - special_tokens,
                       overlap_tokens=overlap_tokens, batch_size=batch_size, max_windows=max_windows)
        except Exception as exc:
            raise MLModelLoadError("Small classifier could not be loaded; verify local weights and label mapping") from exc
