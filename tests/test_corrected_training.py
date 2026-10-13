import hashlib

import pandas as pd
import pytest

from promption.training.reviewed_dataset import load_reviewed_dataset, connect_families, reserve_test_cases
from promption.training.dataset import apply_label_overrides, apply_quarantine
from scripts.compare_corrected_training import validation_rank


def rows():
    return pd.DataFrame([
        dict(row_id="a", prompt="Original English text", label=1, lang="en", source="Custom", dataset="Custom", attack_type="injection", family_id="a", group_id="a", split_group="a", split="train", generation_method="original_corrected"),
        dict(row_id="b", prompt="Texto traducido", label=1, lang="es", source="Custom", dataset="Custom", attack_type="injection", family_id="b", group_id="b", split_group="b", split="test", generation_method="original_corrected", original_prompt_sha256=hashlib.sha256(b"Original English text").hexdigest()),
        dict(row_id="c", prompt="Consulta independiente", label=0, lang="es", source="Benigno", dataset="Benigno", attack_type="benign", family_id="c", group_id="c", split_group="c", split="validation", generation_method="original_corrected"),
    ])


def test_translation_link_cannot_cross_partitions():
    result, changed = connect_families(rows())
    assert changed == 1
    assert result.iloc[0].split == result.iloc[1].split == "test"
    assert result.iloc[0].group_id == result.iloc[1].group_id
    assert result.iloc[2].split == "val"
    assert result.groupby("group_id").split.nunique().eq(1).all()
    from promption.training.split import create_splits
    train, val, test, external = create_splits(result)
    assert len(train) == len(external) == 0
    assert list(val) == [2]
    assert list(test) == [0, 1]


def test_connected_declared_identifiers_are_transitive():
    data = rows()
    data.loc[1, "family_id"] = data.iloc[0].group_id
    data.loc[2, "split_group"] = data.iloc[1].group_id
    result, _ = connect_families(data)
    assert result.group_id.nunique() == 1
    assert result.split.eq("test").all()


def test_corrected_labels_are_not_overridden_by_legacy_files(tmp_path):
    data = rows()
    path = tmp_path / "corrected.csv"
    data.to_csv(path, index=False)
    corrected = load_reviewed_dataset(path)
    pd.DataFrame([dict(prompt_sha256=hashlib.sha256(b"Original English text").hexdigest(), label=0, dataset="Benigno", attack_type="benign")]).to_csv(tmp_path / "label_overrides.csv", index=False)
    pd.DataFrame({"prompt": ["Original English text"]}).to_csv(tmp_path / "quarantine.csv", index=False)
    assert apply_label_overrides(corrected, str(tmp_path)).label.tolist() == [1, 1, 0]
    assert len(apply_quarantine(corrected, str(tmp_path))) == 3


@pytest.mark.parametrize("column,value", [("label", 3), ("lang", "xx"), ("split", "unknown"), ("prompt", ""), ("group_id", "")])
def test_invalid_corrected_data_is_rejected(tmp_path, column, value):
    data = rows()
    data.loc[0, column] = value
    path = tmp_path / "invalid.csv"
    data.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_reviewed_dataset(path)


def test_selection_uses_both_original_validation_languages():
    metrics = {"es/original": {"f1": .8}, "en/original": {"f1": .6}, "es/all": {"f1": .99}, "en/all": {"f1": .99}}
    assert validation_rank(metrics) == (.7, .99)


def test_reservation_is_deterministic_preserves_families_and_validation():
    data = pd.DataFrame([dict(group_id=f"g-{i // 2}", label=(i // 2) % 2,
                              lang="es" if i % 2 else "en", split="train" if i < 16 else "val")
                         for i in range(20)])
    reserved, moved = reserve_test_cases(data, 3, seed=42)
    assert moved > 0
    assert reserved.groupby("group_id").split.nunique().eq(1).all()
    assert reserved.iloc[16:].split.eq("val").all()
    assert reserved[reserved.split.eq("test")].groupby("label").size().ge(3).all()
    assert reserve_test_cases(data, 3, seed=42)[0].equals(reserved)
    for label in (0, 1):
        assert data.loc[reserved.split.eq("test") & data.label.eq(label), "split"].eq("train").all()


def test_reservation_never_uses_validation_to_fill_a_shortfall():
    data = pd.DataFrame([dict(group_id="g-1", label=1, lang="es", split="val"),
                         dict(group_id="g-0", label=0, lang="es", split="train")])
    with pytest.raises(ValueError, match="without using validation"):
        reserve_test_cases(data, 1)
