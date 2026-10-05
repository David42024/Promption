"""Model provenance and non-destructive preservation of previous experiments."""
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from promption.utils.config import load_config


def selected_backend(config: dict | None = None) -> tuple[str, Path]:
    model = (config or load_config())["model"]
    lightweight = model.get("use_lightweight_ml", False)
    return ("tfidf_logistic_regression" if lightweight else "embeddings_random_forest",
            Path(model["lightweight_classifier_path" if lightweight else "classifier_path"]))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_provenance(path: Path, backend: str) -> dict:
    result = {"backend": backend, "artifact": path.name, "available": path.is_file()}
    if result["available"]:
        result["sha256"] = file_sha256(path)
        manifest = path.with_suffix(".metadata.json")
        if manifest.is_file():
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            if metadata.get("sha256") == result["sha256"]:
                result["training"] = metadata
    return result


def preserve_records(config: dict | None = None) -> Path:
    """Copy models and current results before training or replacing benchmark output."""
    config = config or load_config()
    results = Path(config["paths"]["results"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    destination = results / "backups" / f"pre_run_{stamp}_{uuid.uuid4().hex[:8]}"
    destination.mkdir(parents=True)
    sources = [(path, Path("results") / path.name) for path in results.iterdir() if path.is_file()]
    plots = Path(config["paths"]["plots"])
    if plots.exists():
        sources.extend((path, Path("plots") / path.relative_to(plots))
                       for path in plots.rglob("*") if path.is_file())
    for key in ("classifier_path", "lightweight_classifier_path"):
        model = Path(config["model"][key])
        sources.extend((path, Path("models") / path.name)
                       for path in (model, model.with_suffix(".metadata.json")) if path.is_file())
    records = []
    for source, relative in sources:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append({"file": relative.as_posix(), "sha256": file_sha256(target)})
    (destination / "manifest.json").write_text(json.dumps({
        "created_at": stamp,
        "description": "Previous artifacts preserved unchanged; unlabeled results retain unknown provenance.",
        "files": records,
    }, indent=2), encoding="utf-8")
    return destination
