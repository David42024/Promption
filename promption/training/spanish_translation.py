"""Traceable Spanish translations of training families, excluding all holdouts."""
import hashlib
import re

import pandas as pd

from promption.training.split import calculate_manifest_hash

SOURCE = "translated_train_es_v1"
PROVENANCE = ("original_prompt_sha256", "original_source", "translation_model")
PUBLIC_SOURCES = {"NEPI", "Shomi28", "deepset", "jailbreak_llms", "builtin", "owasp_top10"}
SENSITIVE = re.compile(r"sk-proj-|gsk_|pk-live-|AIza[\w-]{20,}|Bearer\s+[\w.-]{24,}|"
                       r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}|(?<!\d)\d{10,}(?!\d)")


def prompt_hash(text):
    return hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()


def training_candidates(base, manifest, limit=1000, seed=42, max_chars=1500):
    """Select balanced English training examples deterministically across sources."""
    if calculate_manifest_hash(manifest) != manifest.get("hash"):
        raise ValueError("Invalid source split manifest")
    groups = {v["group_id"]: v["partition"] for v in manifest["records"].values()}
    eligible = base[base.group_id.map(groups).eq("train") & base.lang.eq("en")
                    & base.prompt.str.len().le(max_chars) & base.source.isin(PUBLIC_SOURCES)
                    & ~base.prompt.map(lambda t: bool(SENSITIVE.search(t)))].copy()
    eligible["original_prompt_sha256"] = eligible.prompt.map(prompt_hash)
    eligible = eligible.sort_values("original_prompt_sha256").drop_duplicates("original_prompt_sha256")
    selections = []
    for label in (0, 1):
        pool = eligible[eligible.label.eq(label)].copy()
        pool = pool.sample(frac=1, random_state=seed)
        pool["source_rank"] = pool.groupby("source").cumcount()
        pool = pool.sort_values("source_rank", kind="stable")
        selections.append(pool.head(limit // 2 + (label == 0 and limit % 2)))
    return pd.concat(selections).drop(columns="source_rank").reset_index(drop=True)


def validate_translations(translations, base, manifest=None):
    """Reject missing origins, relabeling, detached families and holdout translations."""
    required = {"prompt", "label", "source", "lang", "family_id", "group_id", *PROVENANCE}
    if not required.issubset(translations.columns):
        raise ValueError("Translation provenance columns are missing")
    if (translations[list(required)].isna().any().any()
            or not translations.source.eq(SOURCE).all()
            or not translations.lang.eq("es").all()
            or not translations.label.isin([0, 1]).all()
            or translations.prompt.str.strip().eq("").any()
            or translations.translation_model.str.strip().eq("").any()
            or translations.original_prompt_sha256.duplicated().any()):
        raise ValueError("Invalid translation provenance or duplicate origins")
    origins = base.assign(original_prompt_sha256=base.prompt.map(prompt_hash))
    origins = origins.set_index("original_prompt_sha256")
    if not origins.index.is_unique:
        raise ValueError("Ambiguous translation origins")
    if manifest is not None:
        if calculate_manifest_hash(manifest) != manifest.get("hash"):
            raise ValueError("Invalid translation split manifest")
        partitions = {v["group_id"]: v["partition"] for v in manifest["records"].values()}
    for row in translations.itertuples():
        if row.original_prompt_sha256 not in origins.index:
            raise ValueError("Translation has no original prompt")
        original = origins.loc[row.original_prompt_sha256]
        if (row.family_id != original.group_id or row.group_id != original.group_id
                or row.label != original.label or row.original_source != original.source
                or original.lang != "en" or row.prompt.strip() == original.prompt.strip()):
            raise ValueError("Translation changed its original label or family")
        if manifest is not None and partitions.get(row.group_id) != "train":
            raise ValueError("Translation of a holdout family is forbidden")
    return translations


def clean_translations(translations, base, manifest):
    """Exclude equivalent duplicates and any translated text already present in the corpus."""
    validate_translations(translations, base, manifest)
    ambiguous = set(translations.groupby("prompt").label.nunique().loc[lambda n: n.gt(1)].index)
    overlapping = translations.prompt.isin(base.prompt)
    usable = translations.loc[~overlapping & ~translations.prompt.isin(ambiguous)]
    clean = usable.drop_duplicates("prompt", keep="first").reset_index(drop=True)
    rejected = translations.loc[~translations.original_prompt_sha256.isin(clean.original_prompt_sha256)]
    return clean, {"received": len(translations), "retained": len(clean),
        "overlapping_original_texts": int(overlapping.sum()), "ambiguous_texts": len(ambiguous),
        "equivalent_duplicates": int(usable.prompt.duplicated().sum()),
        "excluded_origin_hashes": rejected.original_prompt_sha256.tolist()}
