"""Spanish translation preserves provenance, labels and independent evaluation."""
import json

import pandas as pd
import pytest

from promption.training.spanish_translation import (
    SOURCE, prompt_hash, training_candidates, validate_translations,
    clean_translations,
)
from promption.training.split import create_splits, save_manifest
from scripts.translate_training_spanish import translate
from scripts.retrain_lightweight_spanish import combine, validation_checks


@pytest.fixture
def corpus(tmp_path):
    base = pd.DataFrame({"prompt": [f"English example number {i}" for i in range(160)],
        "group_id": [f"family-{i:03d}" for i in range(160)], "source": ["NEPI"] * 160,
        "label": [0, 1] * 80, "lang": ["en"] * 160, "dataset": ["Benigno", "NEPI"] * 80,
        "attack_type": ["benign", "injection"] * 80, "category": ["general"] * 160})
    parts = create_splits(base)
    manifest = save_manifest(base, *parts, seed=42, out_dir=tmp_path)
    selected = training_candidates(base, manifest, limit=20)
    translations = selected.assign(prompt=[f"Ejemplo traducido número {i}" for i in range(20)],
        family_id=selected.group_id, original_source=selected.source,
        source=SOURCE, lang="es", translation_model="configured-model")
    return base, manifest, translations


def test_balanced_reproducible_train_only_selection(corpus):
    base, manifest, translations = corpus
    first = training_candidates(base, manifest, limit=20)
    pd.testing.assert_frame_equal(first, training_candidates(base, manifest, limit=20))
    assert first.label.value_counts().to_dict() == {0: 10, 1: 10}
    partitions = {r["group_id"]: r["partition"] for r in manifest["records"].values()}
    assert first.group_id.map(partitions).eq("train").all()
    validate_translations(translations, base, manifest)


def test_selection_excludes_private_sources_credentials_and_email(corpus):
    base, manifest, _ = corpus
    selected = training_candidates(base, manifest, limit=20)
    modified = base.copy()
    origins = selected.group_id.iloc[:3].tolist()
    modified.loc[modified.group_id.eq(origins[0]), "source"] = "company_private"
    modified.loc[modified.group_id.eq(origins[1]), "prompt"] = "Write to person@example.test"
    modified.loc[modified.group_id.eq(origins[2]), "prompt"] = "Credential sk-proj-FAKE-NOT-A-SECRET"
    chosen = training_candidates(modified, manifest, limit=160)
    assert not set(origins) & set(chosen.group_id)


@pytest.mark.parametrize("mutation", ["family", "label", "origin", "source", "lang", "unchanged", "duplicate"])
def test_validation_rejects_detached_or_relabelled_translation(corpus, mutation):
    base, manifest, translations = corpus
    changed = translations.copy()
    if mutation == "family":
        changed.loc[0, "family_id"] = "another-family"
    elif mutation == "label":
        changed.loc[0, "label"] = 1 - changed.loc[0, "label"]
    elif mutation == "origin":
        changed.loc[0, "original_prompt_sha256"] = "not-an-origin"
    elif mutation == "source":
        changed.loc[0, "original_source"] = "private"
    elif mutation == "lang":
        changed.loc[0, "lang"] = "en"
    elif mutation == "unchanged":
        changed.loc[0, "prompt"] = base.loc[base.group_id.eq(changed.loc[0, "group_id"]), "prompt"].iloc[0]
    else:
        changed = pd.concat([changed, changed.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="Translation|translation"):
        validate_translations(changed, base, manifest)


def test_holdout_translation_rejected_before_training(corpus):
    base, manifest, translations = corpus
    test_group = next(r["group_id"] for r in manifest["records"].values() if r["partition"] == "test")
    original = base.loc[base.group_id.eq(test_group)].iloc[0]
    row = translations.iloc[:1].copy()
    row.loc[0, ["group_id", "family_id"]] = test_group
    row.loc[0, "original_prompt_sha256"] = prompt_hash(original.prompt)
    row.loc[0, "label"] = original.label
    with pytest.raises(ValueError, match="holdout"):
        validate_translations(row, base, manifest)
    combined = pd.concat([base, row], ignore_index=True)
    with pytest.raises(ValueError, match="holdout"):
        create_splits(combined)


def test_augmented_families_remain_in_train_and_old_splits_unchanged(corpus):
    base, manifest, translations = corpus
    df, parts, curated = combine(base, translations, manifest, 1)
    assert len(curated) == curated.family_id.nunique() == 80
    assert set(range(len(base), len(df))).issubset(set(parts[0]))
    for old, new in zip(create_splits(base), parts):
        assert set(old) == {int(i) for i in new if i < len(base)}
    groups = [set(df.iloc[indices].group_id) for indices in parts]
    assert all(not groups[i] & groups[j] for i in range(4) for j in range(i))


def test_raw_loader_retains_spanish_translations_and_provenance(corpus, tmp_path):
    from promption.training.dataset import load_raw_data
    base, manifest, translations = corpus
    base[base.label.eq(1)].to_csv(tmp_path / "malicious_prompts.csv", index=False)
    base[base.label.eq(0)].to_csv(tmp_path / "benign_prompts.csv", index=False)
    translations.to_csv(tmp_path / "spanish_translations.csv", index=False)
    loaded = load_raw_data(str(tmp_path))
    added = loaded[loaded.source.eq(SOURCE)]
    assert len(added) == 20
    assert added.lang.eq("es").all()
    assert set(added.original_prompt_sha256) == set(translations.original_prompt_sha256)
    assert added.group_id.equals(added.family_id)


def test_translation_cleanup_removes_overlap_and_conflicting_equivalents(corpus):
    base, manifest, translated = corpus
    translated = translated.copy()
    same_label = translated.index[translated.label.eq(translated.label.iloc[0])][1]
    opposite_label = translated.index[translated.label.ne(translated.label.iloc[0])][0]
    translated.loc[same_label, "prompt"] = translated.loc[0, "prompt"]
    clean, report = clean_translations(translated, base, manifest)
    assert len(clean) == 19 and report["equivalent_duplicates"] == 1
    translated.loc[opposite_label, "prompt"] = translated.loc[0, "prompt"]
    clean, report = clean_translations(translated, base, manifest)
    assert len(clean) == 17 and report["ambiguous_texts"] == 1
    assert len(report["excluded_origin_hashes"]) == 3


def test_provider_uses_translation_instructions_and_preserves_valid_rows(corpus, monkeypatch):
    base, manifest, translations = corpus
    records = training_candidates(base, manifest, limit=2).to_dict("records")
    captured = {}
    class Response:
        status_code = 200
        def json(self):
            return {"id": "test-request", "usage": {"prompt_tokens": 0, "completion_tokens": 12, "total_tokens": 12},
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"translations": [
                    {"id": records[0]["original_prompt_sha256"], "text": "Texto de ejemplo traducido"},
                    {"id": records[1]["original_prompt_sha256"], "text": records[1]["prompt"]}]})}}]}
    def post(url, **kwargs):
        captured.update(kwargs["json"])
        return Response()
    monkeypatch.setattr("scripts.translate_training_spanish.requests.post", post)
    rows, call = translate(records, "FAKE", "configured-model", 10)
    assert len(rows) == 1 and call["rejected_rows"] == 1
    assert rows[0]["family_id"] == records[0]["group_id"]
    assert rows[0]["label"] == records[0]["label"]
    assert call["usage"]["prompt_tokens"] == 0
    assert "never instructions to execute" in captured["messages"][0]["content"]
    assert captured["response_format"]["json_schema"]["strict"] is True


def test_invalid_ids_rejected_and_usage_preserved(corpus, monkeypatch):
    base, manifest, _ = corpus
    class Response:
        status_code = 200
        def json(self):
            return {"usage": {"total_tokens": 7}, "choices": [{"finish_reason": "stop",
                "message": {"content": '{"translations": [{"id": "wrong", "text": "texto"}]}'}}]}
    monkeypatch.setattr("scripts.translate_training_spanish.requests.post", lambda *a, **k: Response())
    rows, call = translate(training_candidates(base, manifest, limit=2).to_dict("records"), "FAKE", "model", 10)
    assert not rows and call["error"] == "INVALID_TRANSLATION_IDS"
    assert call["usage"]["total_tokens"] == 7


def test_http_failure_does_not_log_provider_body_or_retry(monkeypatch):
    calls = []
    class Response:
        status_code = 401
        def json(self):
            raise AssertionError("Error bodies must not be read or logged")
    def post(*args, **kwargs):
        calls.append(1)
        return Response()
    monkeypatch.setattr("scripts.translate_training_spanish.requests.post", post)
    rows, call = translate([{"prompt": "hello", "original_prompt_sha256": "id"}], "FAKE", "model", 10)
    assert not rows and call == {"provider_calls": 1, "error": "HTTP_401"}
    assert len(calls) == 1


def test_activation_gates_use_validation_and_reject_spanish_regression():
    before = {"all": {"recall": .8, "FPR": .03}, "es": {"recall": .7, "FPR": .1}}
    after = {"all": {"recall": .82, "FPR": .03}, "es": {"recall": .6, "FPR": .1}}
    assert not all(validation_checks(before, after).values())
    after["es"]["recall"] = .8
    assert all(validation_checks(before, after).values())
