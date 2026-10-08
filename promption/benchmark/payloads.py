from __future__ import annotations
"""Test payload loading.

Evaluation set = all malicious prompts (labelled 1) + all benign prompts (labelled 0).
The ``dataset`` column identifies the source collection: OWASP, BIANCA, Jailbreak,
GitHub, Custom (attacks) or Benigno (legit).
"""
from promption.training.dataset import apply_label_overrides, apply_quarantine, load_raw_data
from promption.training.split import calculate_manifest_hash
import json
from pathlib import Path
import pandas as pd
from promption.training.artifacts import selected_backend
from promption.utils.config import load_config
from promption.utils.logger import logger

def load_evaluation_set(data_dir: str | None = None, partition: str = "test",
                        allow_exploratory: bool = False, model_path: Path | None = None) -> pd.DataFrame:
    df = apply_quarantine(apply_label_overrides(load_raw_data(data_dir)))

    conf = load_config()
    manifest_path = Path(conf["paths"]["processed_data"]) / "split_manifest.json"
    if not manifest_path.exists():
        if not allow_exploratory:
            raise FileNotFoundError(
                "split_manifest.json no encontrado. Para evaluar un modelo independiente es obligatorio "
                "el manifiesto de particiones. Ejecuta primero la preparación o pasa allow_exploratory=True."
            )
        logger.warning("split_manifest.json no encontrado: ejecutando benchmark en modo exploratorio sobre el corpus completo.")
        return df[["prompt", "label", "dataset", "attack_type", "source"]].reset_index(drop=True)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest_hash = manifest.get("hash")
    if not manifest_hash and not allow_exploratory:
        raise ValueError(
            "Evaluación independiente bloqueada: split_manifest.json no contiene hash de integridad. "
            "Re-genera las particiones o usa allow_exploratory=True."
        )

    # Recalcular hash del contenido para certificar que records no fue alterado
    if not allow_exploratory:
        computed_hash = calculate_manifest_hash(manifest)
        if manifest_hash != computed_hash:
            raise ValueError(
                f"Evaluación independiente bloqueada: el contenido de split_manifest.json ha sido alterado "
                f"y no coincide con su hash de integridad declarada ({manifest_hash[:8]}... vs {computed_hash[:8]}...). "
                "Re-genera las particiones o usa allow_exploratory=True."
            )

    # Comprobar vínculo con el modelo activo efectivo
    if not allow_exploratory:
        target_model = Path(model_path) if model_path is not None else selected_backend(conf)[1]
        meta_path = target_model.with_suffix(".metadata.json")
        if not meta_path.is_file():
            raise ValueError(
                f"Evaluación independiente bloqueada: no se encontraron metadatos ({meta_path.name}) "
                f"para certificar el holdout con el manifiesto actual ({manifest.get('hash', '')[:8]}...). "
                "Re-entrena el modelo o usa allow_exploratory=True."
            )
        try:
            with open(meta_path, "r", encoding="utf-8") as mf:
                model_meta = json.load(mf)
        except (json.JSONDecodeError, OSError) as err:
            raise ValueError(
                f"Evaluación independiente bloqueada: metadatos corruptos o ilegibles en {meta_path.name} ({err}). "
                "Re-entrena el modelo o usa allow_exploratory=True."
            )

        m_hash = model_meta.get("manifest_hash")
        if not m_hash:
            raise ValueError(
                f"Evaluación independiente bloqueada: el modelo ({target_model.name}) no registra manifest_hash. "
                "Re-entrena el modelo para vincularlo al manifiesto o usa allow_exploratory=True."
            )
        if m_hash != manifest.get("hash"):
            raise ValueError(
                f"Evaluación independiente bloqueada: discrepancia entre el modelo ({m_hash[:8]}...) "
                f"y split_manifest.json ({manifest.get('hash', '')[:8]}...). "
                "Re-entrena el modelo o usa allow_exploratory=True."
            )

    group_to_part = {v["group_id"]: v["partition"] for v in manifest["records"].values()}
    df["partition"] = df["group_id"].map(group_to_part)

    if partition == "all":
        if not allow_exploratory:
            raise ValueError("La partición 'all' solo se permite en modo exploratorio explícito (allow_exploratory=True).")
        eval_mask = df["partition"].notna()
    elif partition in ("test", "external", "val"):
        eval_mask = df["partition"] == partition
    else:
        raise ValueError(f"Partición no válida: {partition}. Opciones: 'test', 'external', 'val', 'all'")

    df = df[eval_mask].reset_index(drop=True)
    logger.info("Loaded %d samples for benchmark from '%s' partition.", len(df), partition)
    df = df[["prompt", "label", "dataset", "attack_type", "source"]].reset_index(drop=True)
    return df


def summary(df):
    rows = []
    for (label, dataset), grp in df.groupby(["label", "dataset"]):
        rows.append({"label": label, "dataset": dataset, "count": len(grp)})
    out = {}
    for r in rows:
        out.setdefault(r["dataset"], {})[r["label"]] = r["count"]
    return out
