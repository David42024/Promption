"""Windowing and adapter contracts; no downloaded model or accuracy claims."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from promption.filter.exceptions import MLInferenceError, MLModelLoadError
from promption.filter.small_model import SmallModelFilter


def test_all_tokens_including_tail_are_covered_in_bounded_batches():
    windows, batches = [], []
    def predict(batch):
        batches.append(len(batch))
        windows.extend(batch)
        return [.98 if 24 in window else .02 for window in batch]
    detector = SmallModelFilter(lambda _: range(25), predict, window_tokens=6, overlap_tokens=2, batch_size=2)
    result = detector.analyze("long document")
    assert set(range(25)) == {token for window in windows for token in window}
    assert max(batches) <= 2
    assert result.blocked and result.probability == .98


def test_overlap_captures_pattern_across_first_window_boundary():
    def predict(batch):
        return [.99 if "456" in "".join(window) else .01 for window in batch]
    detector = SmallModelFilter(list, predict, window_tokens=6, overlap_tokens=3)
    assert detector.analyze("0123456789").blocked


@pytest.mark.parametrize("probabilities", [[float("nan")], [float("inf")], [1.1], [-.1], [[.5, .5]], []])
def test_malformed_predictions_fail_closed(probabilities):
    with pytest.raises(MLInferenceError):
        SmallModelFilter(list, lambda _: probabilities).analyze("hola")


def test_limit_is_error_without_scoring_a_truncated_prefix():
    def predict(_):
        pytest.fail("Over-limit input must not be scored partially")
    detector = SmallModelFilter(list, predict, window_tokens=4, overlap_tokens=0, max_windows=2)
    with pytest.raises(MLInferenceError, match="limit"):
        detector.analyze("123456789")


@pytest.mark.parametrize("options", [{"threshold": 0}, {"threshold": 1}, {"threshold": True},
    {"overlap_tokens": 510}, {"overlap_tokens": -1}, {"batch_size": 0}, {"max_windows": False}])
def test_invalid_window_configuration(options):
    with pytest.raises(ValueError):
        SmallModelFilter(list, lambda _: [.1], **options)


def test_empty_input_and_exact_threshold():
    detector = SmallModelFilter(list, lambda windows: [.9] * len(windows))
    assert detector.analyze("").blocked
    assert detector.is_loaded and detector.is_trained()


def test_factory_uses_local_safe_weights_and_explicit_label_mapping(monkeypatch):
    from contextlib import nullcontext
    class Tensor:
        def __init__(self, values):
            self.values = np.asarray(values)
        def to(self, device):
            return self
        def cpu(self):
            return self
        def numpy(self):
            return self.values
        def __len__(self):
            return len(self.values)
        def __getitem__(self, index):
            return Tensor(self.values[index])
        def sum(self, dim):
            return Tensor(self.values.sum(axis=dim))
    def softmax(tensor, dim):
        values = np.exp(tensor.values - tensor.values.max(axis=dim, keepdims=True))
        return Tensor(values / values.sum(axis=dim, keepdims=True))
    torch = SimpleNamespace(tensor=Tensor, ones=lambda shape, **_: Tensor(np.ones(shape)),
                            long=int, no_grad=nullcontext, softmax=softmax)
    monkeypatch.setitem(sys.modules, "torch", torch)
    calls = []
    class Tokenizer:
        model_max_length = 512
        model_input_names = ["input_ids", "attention_mask"]
        def encode(self, text, **kwargs):
            assert kwargs == {"add_special_tokens": False, "truncation": False}
            return [1] * len(text)
        def num_special_tokens_to_add(self, pair):
            return 2
        def prepare_for_model(self, window, **kwargs):
            assert kwargs["truncation"] is False
            return {"input_ids": [0] + window + [0]}
        def pad(self, batch, **kwargs):
            return {"input_ids": torch.ones((len(batch), 8), dtype=torch.long)}
    class Model:
        config = SimpleNamespace(id2label={0: "MALICIOUS", 1: "BENIGN"}, num_labels=2,
                                 max_position_embeddings=512)
        def to(self, device):
            assert device == "cpu"
        def eval(self):
            pass
        def __call__(self, **inputs):
            return SimpleNamespace(logits=torch.tensor([[5., -5.]] * len(inputs["input_ids"])))
    def loader(value):
        def load(path, **kwargs):
            calls.append((path, kwargs))
            return value
        return SimpleNamespace(from_pretrained=load)
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoTokenizer=loader(Tokenizer()), AutoModelForSequenceClassification=loader(Model())))
    detector = SmallModelFilter.from_pretrained("/tmp/synthetic-weights", revision="fixed-revision")
    assert detector.analyze("hola").blocked
    assert detector.window_tokens == 510
    assert all(options["local_files_only"] and not options["trust_remote_code"] for _, options in calls)
    assert calls[1][1]["use_safetensors"] is True
    assert all(options["revision"] == "fixed-revision" for _, options in calls)
    with pytest.raises(MLModelLoadError):
        SmallModelFilter.from_pretrained("/tmp/synthetic-weights", positive_labels=("UNKNOWN",))
