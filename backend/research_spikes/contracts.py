"""Plan E research-only artifact contracts.

This module deliberately has no production import path. It validates immutable
research inputs and candidate dossiers before comparative spikes are allowed.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REQUIRED_DOSSIER_FIELDS = {
    "candidate_id",
    "name",
    "version_checked",
    "candidate_family",
    "target",
    "primary_sources",
    "official_implementations",
    "mechanism",
    "assumptions",
    "claimed_benefit",
    "reported_benchmark_scope",
    "falsifiable_hypothesis",
    "controls",
    "spike",
    "metrics",
    "risks",
    "evidence_against_adoption",
    "preliminary_decision",
    "confidence",
    "rejection_section",
    "downstream_owner",
}
REQUIRED_RISKS = {"provenance", "update_delete", "cost_latency", "dependency"}
DECISIONS = {"adopt-contract", "benchmark-later", "reject-default"}
DOWNSTREAM_OWNERS = {"plan-d2", "program-2", "program-3"}
ALLOWED_TARGET_KINDS = {"failure-atlas", "architecture-neutral-control"}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dossier(dossier: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_DOSSIER_FIELDS - dossier.keys())
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")

    target = dossier.get("target")
    if not isinstance(target, dict) or target.get("kind") not in ALLOWED_TARGET_KINDS:
        errors.append("target must declare failure-atlas or architecture-neutral-control")
    elif target["kind"] == "failure-atlas" and not target.get("failure_ids"):
        errors.append("failure-atlas target requires failure_ids")
    elif not str(target.get("question", "")).strip():
        errors.append("target requires a scoped question")

    sources = dossier.get("primary_sources")
    if not isinstance(sources, list) or not sources:
        errors.append("at least one primary source is required")
    else:
        for source in sources:
            if not all(str(source.get(key, "")).strip() for key in ("title", "url", "claim_boundary")):
                errors.append("every primary source needs title, url, and claim_boundary")

    if not dossier.get("controls"):
        errors.append("at least one simple control is required")
    if not dossier.get("metrics"):
        errors.append("at least one metric is required")
    if not str(dossier.get("falsifiable_hypothesis", "")).strip():
        errors.append("falsifiable_hypothesis must be non-empty")
    if not str(dossier.get("spike", {}).get("independent_variable", "")).strip():
        errors.append("spike.independent_variable must isolate the mechanism")

    risks = dossier.get("risks")
    if not isinstance(risks, dict) or not REQUIRED_RISKS.issubset(risks):
        errors.append("risks must cover provenance, update_delete, cost_latency, dependency")
    if not str(dossier.get("evidence_against_adoption", "")).strip():
        errors.append("evidence_against_adoption must be non-empty")
    if not str(dossier.get("rejection_section", "")).strip():
        errors.append("rejection_section must be non-empty")
    if dossier.get("preliminary_decision") not in DECISIONS:
        errors.append("preliminary_decision is invalid")
    if dossier.get("downstream_owner") not in DOWNSTREAM_OWNERS:
        errors.append("downstream_owner is invalid")
    return errors


def sqlite_readonly_summary(path: Path) -> dict[str, Any]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        schema_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
            if not table.startswith("search_documents_fts")
        }
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "schema_version": schema_row[0] if schema_row else None,
        "table_counts": counts,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
