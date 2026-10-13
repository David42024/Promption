"""Spanish augmentation must teach the classifier without moving held-out families."""
import numpy as np
import pandas as pd
import pytest

from promption.training.spanish_corpus import SOURCE, build_spanish_corpus
from promption.training.split import create_splits


def test_corpus_balanced_authored_families_and_no_credential_values():
    first = build_spanish_corpus()
    pd.testing.assert_frame_equal(first, build_spanish_corpus())
    assert len(first) == first.prompt.nunique() == 960
    assert first.label.value_counts().to_dict() == {1: 480, 0: 480}
    assert first.family_id.nunique() == 80
    assert first.groupby("family_id").label.nunique().eq(1).all()
    assert first.groupby("family_id").size().eq(12).all()
    assert first.lang.eq("es").all()
    assert not first.prompt.str.contains(r"sk-proj-|gsk_|pk-live-", regex=True).any()


def test_spanish_train_only_does_not_move_existing_holdouts():
    base = pd.DataFrame({"prompt": [f"existing {i}" for i in range(160)],
                         "group_id": [f"group-{i}" for i in range(160)],
                         "label": [0, 1] * 80, "lang": ["en"] * 80 + ["es"] * 80,
                         "source": ["public"] * 152 + ["translated_es"] * 8})
    before = create_splits(base.copy())
    augmentation = build_spanish_corpus()
    augmentation["group_id"] = augmentation.family_id
    combined = pd.concat([base, augmentation], ignore_index=True)
    after = create_splits(combined)
    for old, new in zip(before, after):
        assert set(old) == {int(i) for i in new if i < len(base)}
    assert set(range(len(base), len(combined))).issubset(set(after[0]))
    groups = [set(combined.iloc[idx].group_id) for idx in after]
    assert all(not groups[i] & groups[j] for i in range(4) for j in range(i))
    assert len(set(np.concatenate(after))) == len(combined)


def test_augmentation_cannot_promote_an_existing_external_family():
    df = pd.DataFrame({"group_id": ["shared", "shared", "fresh"],
                       "source": ["translated_es", SOURCE, SOURCE],
                       "label": [1, 1, 0], "lang": ["en", "es", "es"]})
    train, val, test, external = create_splits(df)
    assert set(external) == {0, 1}
    assert set(train) == {2}
    assert not len(val) and not len(test)


def test_loader_preserves_authored_spanish_and_family_ids(tmp_path):
    from promption.training.dataset import load_raw_data
    corpus = build_spanish_corpus()
    corpus.to_csv(tmp_path / "spanish_augmentation.csv", index=False)
    loaded = load_raw_data(str(tmp_path))
    assert loaded.lang.eq("es").all()
    assert loaded.group_id.equals(loaded.family_id)
    assert set(loaded.prompt) == set(corpus.prompt)


@pytest.mark.parametrize("mutation", ["source", "label", "lang", "family", "schema"])
def test_loader_rejects_untraceable_or_invalid_augmentation(tmp_path, mutation):
    from promption.training.dataset import load_raw_data
    df = build_spanish_corpus()
    if mutation == "source":
        df.loc[0, "source"] = "translated_es"
    elif mutation == "label":
        df.loc[0, "label"] = 7
    elif mutation == "lang":
        df.loc[0, "lang"] = "en"
    elif mutation == "family":
        df.loc[0, "family_id"] = ""
    else:
        df = df.drop(columns="family_id")
    df.to_csv(tmp_path / "spanish_augmentation.csv", index=False)
    with pytest.raises(ValueError, match="augmentation"):
        load_raw_data(str(tmp_path))


def test_report_evaluates_effective_threshold_not_classifier_default(monkeypatch):
    from promption.training.train_lightweight import evaluate_model
    class Vectorizer:
        def transform(self, texts):
            return np.zeros((len(texts), 1))
    class Classifier:
        classes_ = np.asarray([1, 0])
        def predict_proba(self, features):
            return np.asarray([[.6, .4], [.2, .8]])
        def predict(self, features):
            raise AssertionError("Evaluation must use the deployed probability boundary")
    monkeypatch.setattr("promption.training.train_lightweight.joblib.dump", lambda *args: None)
    data = pd.DataFrame({"prompt": ["attack", "benign"]})
    result = evaluate_model(Vectorizer(), Classifier(), data, [1, 0], threshold=.66)
    assert result["decision_threshold"] == .66
    assert result["recall"] == 0
    result = evaluate_model(Vectorizer(), Classifier(), data, [1, 0], threshold=.5)
    assert result["recall"] == 1


def test_embedding_cache_checks_text_order_model_and_prefix(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from promption.training import train as forest
    calls = []
    class Encoder:
        def __init__(self, model):
            calls.append(model)
        def encode(self, texts, **kwargs):
            return np.asarray([[len(t), i] for i, t in enumerate(texts)], dtype=np.float32)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Encoder))
    config = {"model": {"embedding_prefix": "query: "}}
    monkeypatch.setattr(forest, "load_config", lambda: config)
    df = pd.DataFrame({"prompt": ["hola", "secreto"]})
    path = tmp_path / "vectors.npy"
    first = forest.embed_dataset(df, "encoder-a", path)
    np.testing.assert_array_equal(first, forest.embed_dataset(df, "encoder-a", path))
    assert calls == ["encoder-a"]
    forest.embed_dataset(df.iloc[::-1], "encoder-a", path)
    forest.embed_dataset(df, "encoder-b", path)
    config["model"]["embedding_prefix"] = ""
    forest.embed_dataset(df, "encoder-b", path)
    assert len(calls) == 4


def test_embedding_cache_does_not_accept_unidentified_legacy_array(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from promption.training import train as forest
    class Encoder:
        def __init__(self, name):
            pass
        def encode(self, texts, **kwargs):
            return np.ones((len(texts), 3), dtype=np.float32)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Encoder))
    monkeypatch.setattr(forest, "load_config", lambda: {"model": {"embedding_prefix": "query: "}})
    path = tmp_path / "legacy.npy"
    np.save(path, np.zeros((2, 3)))
    assert forest.embed_dataset(pd.DataFrame({"prompt": ["a", "b"]}), "encoder", path).all()


def test_embedding_revision_invalidates_cache_and_is_used_for_loading(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from promption.training import train as forest
    revisions = []
    class Encoder:
        def __init__(self, name, revision):
            revisions.append(revision)
        def encode(self, texts, **kwargs):
            return np.ones((len(texts), 3), dtype=np.float32)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Encoder))
    config = {"model": {"embedding_prefix": "query: ", "embedding_revision": "revision-a"}}
    monkeypatch.setattr(forest, "load_config", lambda: config)
    frame = pd.DataFrame({"prompt": ["hola"]})
    path = tmp_path / "vectors.npy"
    forest.embed_dataset(frame, "encoder", path)
    forest.embed_dataset(frame, "encoder", path)
    config["model"]["embedding_revision"] = "revision-b"
    forest.embed_dataset(frame, "encoder", path)
    assert revisions == ["revision-a", "revision-b"]


def test_retraining_preserves_every_existing_family(tmp_path):
    from scripts.retrain_spanish_model import augment_preserving_holdouts
    from promption.training.split import save_manifest
    base = pd.DataFrame({"prompt": [f"old {i}" for i in range(60)],
                         "group_id": [f"g-{i}" for i in range(60)],
                         "label": [0, 1] * 30, "source": ["public"] * 60,
                         "lang": ["es"] * 60})
    manifest = save_manifest(base, *create_splits(base), seed=42, out_dir=tmp_path)
    combined, partitions, augmentation = augment_preserving_holdouts(base, manifest)
    assert len(combined) == 1020
    assert len(augmentation) == 960
    assert set(partitions[0]) >= set(range(60, 1020))
    bad = dict(manifest)
    bad["records"] = {i: {**v, "partition": "external"} for i, v in manifest["records"].items()}
    with pytest.raises(ValueError, match="evaluation family"):
        augment_preserving_holdouts(base, bad)


def test_validation_tuning_rejects_recall_gain_with_excess_false_positives(tmp_path, monkeypatch):
    from scripts import retrain_spanish_model as retraining
    fitted = []
    class Classifier:
        classes_ = np.asarray([0, 1])
        def __init__(self, **kwargs):
            pass
        def fit(self, vectors, labels):
            fitted.append(vectors.copy())
        def predict_proba(self, vectors):
            return np.tile([.1, .9], (len(vectors), 1))
    monkeypatch.setattr(retraining, "RandomForestClassifier", Classifier)
    train_vectors = np.asarray([[100], [101]])
    baseline = {"all": {"recall": .5, "FPR": 0}, "es": {"recall": .5}}
    config = {"model": {"n_trees": 4, "max_depth": 3, "min_samples_leaf": 1, "random_state": 42}}
    winner = retraining.tune_on_validation(train_vectors, np.asarray([0, 1]),
        np.asarray([[200], [201]]), np.asarray([0, 1]), np.asarray([0, 1]),
        np.asarray(["es", "es"]), baseline, .66, config, tmp_path)
    assert winner is None
    assert len(fitted) == 5
    assert all(np.array_equal(vectors, train_vectors) for vectors in fitted)
    import json
    report = json.loads((tmp_path / "validation_tuning.json").read_text())
    assert all(not candidate["eligible"] for candidate in report)
