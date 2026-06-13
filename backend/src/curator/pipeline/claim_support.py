"""Deterministic claim-level support validation (Plan B, v0.8.0, P4).

Implements the SYSTEM_BEHAVIOR §26.1 structural gate: a deterministic
verdict (`verified | failed | uncertain`) on whether a knowledge unit's cited
source spans minimally support it, plus the read-only compiler audit and the
source-mutation reconciliation that retires stale units.

The gate is deliberately NOT a lookup against the gold fixtures (that would
overfit — the fixtures are the test-time release oracle that scores this gate).
It operates structurally on the cited span text:

- Formula claims: every LaTeX formula in the claim must be structurally present
  in some cited span, compared as an ordered token sequence. A claim formula may
  be a contiguous sub-formula of a larger span formula, but operation direction
  and grouping remain binding (`a^b` != `b^a`; `a-b` != `b-a`).
- Text claims: the claim's salient content terms must intersect a cited span
  above the support threshold; zero/low overlap is the F6 wrong-real-span case.

A `verified` verdict means "faithfully grounded in the L1 span as parsed"; the
source-fidelity gap for lossy PDF sources is closed by P5 selective recovery,
which an `uncertain` formula verdict routes into (SYSTEM_BEHAVIOR §26.2).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import db

__all__ = [
    "AuditReport",
    "normalize_claim",
    "semantic_hash",
    "validate_claim_support",
    "run_compiler_audit",
    "reconcile_source",
]

# Verdict thresholds on term coverage = |claim_terms ∩ span_terms| / |claim_terms|.
_SUPPORT_VERIFY = 0.5   # >= → structurally supported
_SUPPORT_FAIL = 0.25    # <  → no minimal support (F6)

# Function words excluded from salient-term overlap. Content words (e.g.
# "computes", "gradient") are intentionally kept.
_STOPWORDS = frozenset({
    "the", "and", "for", "are", "was", "were", "been", "being", "with", "from",
    "into", "than", "then", "that", "this", "these", "those", "its", "it", "is",
    "as", "of", "to", "in", "on", "by", "or", "an", "be", "but", "not", "no",
    "can", "may", "will", "each", "per", "via", "between", "across", "during",
    "where", "when", "which", "while", "also", "such", "their", "they", "them",
    "a", "any", "all", "both", "so", "if", "out", "up", "we", "you", "our",
})

_LATEX_RE = re.compile(
    r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$",
    re.DOTALL,
)
_TERM_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9]{2,}")
_FORMULA_TOKEN_RE = re.compile(r"\\[a-zA-Z]+|\\.|[^\s\\]")


@dataclass
class AuditReport:
    """Read-only compiler-audit result (SCHEMA §20.5, SYSTEM_BEHAVIOR §26.5)."""

    unsupported_claims: list[str] = field(default_factory=list)
    failed_claims: list[str] = field(default_factory=list)
    stale_claims: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.unsupported_claims or self.failed_claims or self.stale_claims)


def _extract_latex(text: str) -> list[str]:
    """Return the inner LaTeX of every inline `$...$` or display `$$...$$`."""
    return [m.group(1) if m.group(1) is not None else m.group(2)
            for m in _LATEX_RE.finditer(text)]


def _formula_tokens(latex: str) -> tuple[str, ...]:
    """Normalize LaTeX to an ordered token sequence preserving structure.

    Whitespace and spacing macros (`\\,`/`\\!`/`\\;`/`\\quad`/`~`) are ignored.
    Commands, operators, operands, and grouping braces retain their exact order
    so exponent, subtraction, division, and function-argument binding cannot
    silently reverse.
    """
    s = re.sub(r"\\[,;:!>]", " ", latex)
    s = re.sub(r"\\(quad|qquad)\b", " ", s)
    s = s.replace("~", " ")
    return tuple(_FORMULA_TOKEN_RE.findall(s))


def _is_formula_subsequence(
    claim_tokens: tuple[str, ...], span_tokens: tuple[str, ...]
) -> bool:
    """Whether claim tokens occur contiguously and in order in a span formula."""
    size = len(claim_tokens)
    if size == 0 or size > len(span_tokens):
        return False
    return any(
        span_tokens[start:start + size] == claim_tokens
        for start in range(len(span_tokens) - size + 1)
    )


def _content_terms(text: str) -> set[str]:
    """Salient prose terms (len>=3, minus stopwords), LaTeX regions removed."""
    no_latex = _LATEX_RE.sub(" ", text)
    return {t for t in (w.lower() for w in _TERM_RE.findall(no_latex))
            if t not in _STOPWORDS}


def _term_coverage(claim_terms: set[str], span_terms: set[str]) -> float:
    if not claim_terms:
        return 0.0
    return len(claim_terms & span_terms) / len(claim_terms)


def normalize_claim(statement: str) -> str:
    """Deterministic normalization of a claim statement: salient terms sorted,
    plus normalized ordered formula tokens. Stable across whitespace/wording noise.
    Used only to propose reconciliation candidates (SCHEMA §20.1), never to
    auto-merge materially different claims."""
    terms = sorted(_content_terms(statement))
    formulas = sorted(
        json.dumps(_formula_tokens(f), separators=(",", ":"))
        for f in _extract_latex(statement)
    )
    return "terms:" + " ".join(terms) + "|formulas:" + " ".join(formulas)


def semantic_hash(statement: str) -> str:
    """16-hex deterministic fingerprint of the normalized claim."""
    return hashlib.sha256(normalize_claim(statement).encode("utf-8")).hexdigest()[:16]


def _statement_for_stable_id(statement: str) -> str:
    """Normalize whitespace only for safe stable-id reuse."""
    return " ".join(statement.split())


def _load_unit(db_path: Path, unit_id: str) -> dict | None:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, statement, source_span_ids FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["source_span_ids"] = json.loads(data.get("source_span_ids") or "[]")
    return data


def _load_spans(
    db_path: Path, declared: list[str], span_texts: dict[str, str] | None
) -> dict[str, tuple[str, str]]:
    """Map cited span id -> (text, content_hash). Uses full `span_texts` when
    provided (compile path), else the stored preview (short gold spans)."""
    out: dict[str, tuple[str, str]] = {}
    with db.connect(db_path) as conn:
        for sid in declared:
            row = conn.execute(
                "SELECT text_preview, content_hash FROM source_spans WHERE id = ?",
                (sid,),
            ).fetchone()
            if row is None:
                continue
            text = (span_texts or {}).get(sid) or row["text_preview"] or ""
            out[sid] = (text, row["content_hash"])
    return out


def _set_semantic_hash(db_path: Path, unit_id: str, value: str) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE knowledge_units SET semantic_hash = ? WHERE id = ?",
            (value, unit_id),
        )


def _clear_claim_supports(db_path: Path, unit_id: str) -> None:
    """Remove prior/proposed support rows before writing one fresh verdict."""
    with db.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM claim_supports WHERE knowledge_unit_id = ?",
            (unit_id,),
        )


def validate_claim_support(
    db_path: Path,
    unit_id: str,
    *,
    span_texts: dict[str, str] | None = None,
    client: object | None = None,
) -> str:
    """Run the deterministic structural gate on one knowledge unit.

    Writes `claim_supports` rows and sets the unit's `support_status`,
    `formula_status`, and `semantic_hash`. Returns the verdict
    (`verified | failed | uncertain`). `client` is reserved for secondary
    calibrated model validation of `uncertain` text claims; with no client an
    `uncertain` unit stays `unchecked` (never promoted).
    """
    unit = _load_unit(db_path, unit_id)
    if unit is None:
        raise ValueError(f"unknown knowledge unit: {unit_id}")

    statement: str = unit["statement"]
    declared: list[str] = unit["source_span_ids"]
    spans = _load_spans(db_path, declared, span_texts)
    _set_semantic_hash(db_path, unit_id, semantic_hash(statement))
    _clear_claim_supports(db_path, unit_id)

    claim_terms = _content_terms(statement)
    claim_formulas = [_formula_tokens(f) for f in _extract_latex(statement)]
    has_formula = bool(claim_formulas)

    best_id: str | None = None
    best_score: tuple[int, float] = (-1, -1.0)
    max_cov = 0.0
    span_formulas: set[tuple[str, ...]] = set()
    for sid, (text, _chash) in spans.items():
        cov = _term_coverage(claim_terms, _content_terms(text))
        max_cov = max(max_cov, cov)
        local_span_formulas = [_formula_tokens(f) for f in _extract_latex(text)]
        span_formulas.update(local_span_formulas)
        formula_matches = sum(
            1
            for formula in claim_formulas
            if any(
                _is_formula_subsequence(formula, span_formula)
                for span_formula in local_span_formulas
            )
        )
        score = (formula_matches, cov)
        if best_id is None or score > best_score:
            best_id, best_score = sid, score

    formula_ok = all(
        any(_is_formula_subsequence(formula, span_formula) for span_formula in span_formulas)
        for formula in claim_formulas
    )

    # --- verdict (SYSTEM_BEHAVIOR §26.1 trichotomy) ---
    if not spans:
        verdict = "failed"
        reason = "claim cites no resolvable source span; does not minimally support the claim"
        formula_status = "missing" if has_formula else "not_applicable"
    elif has_formula and formula_ok and not claim_terms:
        # Formula-only atomic units are supported by the ordered structural
        # match itself; there is no prose overlap to score.
        verdict = "verified"
        reason = ""
        formula_status = "preserved_in_text"
    elif not claim_terms and not has_formula:
        verdict = "failed"
        reason = "claim has no salient text or formula to validate"
        formula_status = "not_applicable"
    elif claim_terms and max_cov < _SUPPORT_FAIL:
        verdict = "failed"
        reason = "the cited span does not minimally support the claim (no salient term overlap)"
        formula_status = (
            "preserved_in_text"
            if formula_ok
            else ("missing" if has_formula else "not_applicable")
        )
    elif has_formula and not formula_ok:
        # Right topic, but the formula is absent/altered in the span: route to
        # P5 selective recovery rather than hard-fail (could be parse loss).
        verdict = "uncertain"
        reason = "central formula not structurally present in the cited span (possible parse loss or alteration)"
        formula_status = "uncertain"
    elif max_cov >= _SUPPORT_VERIFY:
        verdict = "verified"
        reason = ""
        formula_status = "preserved_in_text" if has_formula else "not_applicable"
    else:
        # Ambiguous textual support: secondary calibrated model adjudicates.
        verdict = "uncertain"
        reason = "ambiguous textual support; escalate to calibrated model validation"
        formula_status = "not_applicable"

    # --- persist support rows + unit status ---
    if verdict == "verified":
        assert best_id is not None  # verified ⇒ spans non-empty ⇒ best_id set
        db.upsert_claim_support(
            db_path, knowledge_unit_id=unit_id, source_span_id=best_id,
            support_role="primary", support_status="verified",
            evidence_hash=spans[best_id][1],
        )
        for sid, (_t, chash) in spans.items():
            if sid != best_id:
                db.upsert_claim_support(
                    db_path, knowledge_unit_id=unit_id, source_span_id=sid,
                    support_role="contextual", support_status="verified",
                    evidence_hash=chash,
                )
        db.set_unit_support_status(db_path, unit_id, "verified")
    elif verdict == "failed":
        target = best_id or (declared[0] if declared else None)
        if target and target in spans:
            db.upsert_claim_support(
                db_path, knowledge_unit_id=unit_id, source_span_id=target,
                support_role="primary", support_status="failed",
                evidence_hash=spans[target][1], support_reason=reason,
            )
        db.set_unit_support_status(db_path, unit_id, "failed", reason)
    else:  # uncertain — not promoted; left unchecked with an audit-visible note
        if best_id:
            db.upsert_claim_support(
                db_path, knowledge_unit_id=unit_id, source_span_id=best_id,
                support_role="primary", support_status="unchecked",
                evidence_hash=spans[best_id][1], support_reason=reason,
            )

    db.set_unit_formula_status(db_path, unit_id, formula_status)
    return verdict


def run_compiler_audit(db_path: Path) -> AuditReport:
    """Read-only compiler audit (SCHEMA §20.5, SYSTEM_BEHAVIOR §26.5).

    Re-checks evidence freshness (marking hash-drifted support stale), then
    reports active source-supported units that lack verified minimal support.
    """
    db.refresh_support_freshness(db_path)
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, support_status FROM knowledge_units "
            "WHERE retired_at IS NULL AND truth_status = 'source_supported'"
        ).fetchall()
    unsupported = [r["id"] for r in rows if r["support_status"] != "verified"]
    failed = [r["id"] for r in rows if r["support_status"] == "failed"]
    stale = [r["id"] for r in rows if r["support_status"] == "stale"]
    return AuditReport(unsupported_claims=unsupported, failed_claims=failed,
                       stale_claims=stale)


def _reuse_verified_candidate(
    db_path: Path, old_id: str, candidate_id: str
) -> None:
    """Move a verified semantic-match candidate onto the prior stable id."""
    with db.connect(db_path) as conn:
        candidate = conn.execute(
            "SELECT * FROM knowledge_units WHERE id = ?", (candidate_id,)
        ).fetchone()
        if candidate is None:
            return
        fields = (
            "unit_type", "canonical_name", "statement", "source_span_ids",
            "source_id", "confidence", "truth_status", "prompt_run_id",
            "semantic_hash", "support_status", "support_reason",
            "formula_status", "generation_id",
        )
        assignments = ", ".join(f"{field} = ?" for field in fields)
        conn.execute(
            f"UPDATE knowledge_units SET {assignments}, updated_at = ? WHERE id = ?",
            tuple(candidate[field] for field in fields) + (candidate["updated_at"], old_id),
        )
        conn.execute("DELETE FROM claim_supports WHERE knowledge_unit_id = ?", (old_id,))
        conn.execute(
            """
            INSERT INTO claim_supports
                (knowledge_unit_id, source_span_id, support_role, support_status,
                 support_reason, evidence_hash, validator_trace_id, created_at, updated_at)
            SELECT ?, source_span_id, support_role, support_status, support_reason,
                   evidence_hash, validator_trace_id, created_at, updated_at
              FROM claim_supports
             WHERE knowledge_unit_id = ?
            """,
            (old_id, candidate_id),
        )
    db.retire_knowledge_unit(db_path, candidate_id)


def reconcile_source(
    db_path: Path,
    source_id: int,
    *,
    current_span_ids: list[str] | None = None,
    candidate_unit_ids: list[str] | None = None,
) -> list[str]:
    """Reconcile active units after source edit/delete/split.

    Units citing spans outside `current_span_ids` retire unless a newly
    extracted, verified candidate has the same whitespace-normalized statement.
    Such a candidate revalidates the old stable id, then retires its temporary
    id. Semantic hashes only propose candidates and never authorize reuse by
    themselves. Returns every id retired by reconciliation.
    """
    with db.connect(db_path) as conn:
        existing = {
            str(r[0]) for r in conn.execute(
                "SELECT id FROM source_spans WHERE source_id = ?", (source_id,)
            ).fetchall()
        }
        current = set(current_span_ids) if current_span_ids is not None else existing
        units = [
            dict(row) for row in conn.execute(
                "SELECT id, statement, source_span_ids, semantic_hash, support_status "
                "FROM knowledge_units WHERE source_id = ? AND retired_at IS NULL",
                (source_id,),
            ).fetchall()
        ]

    candidate_ids = set(candidate_unit_ids or [])
    candidates = {
        str(unit["id"]): unit
        for unit in units
        if str(unit["id"]) in candidate_ids
        and unit["support_status"] == "verified"
        and unit.get("semantic_hash")
    }
    retired: list[str] = []
    for u in units:
        unit_id = str(u["id"])
        if unit_id in candidate_ids:
            continue
        cited = json.loads(u["source_span_ids"] or "[]")
        if all(sid in current for sid in cited):
            continue

        match = next(
            (
                candidate_id
                for candidate_id, candidate in candidates.items()
                if candidate["semantic_hash"] == u.get("semantic_hash")
                and _statement_for_stable_id(candidate["statement"])
                == _statement_for_stable_id(u["statement"])
            ),
            None,
        )
        if match:
            _reuse_verified_candidate(db_path, unit_id, match)
            retired.append(match)
            candidates.pop(match)
            continue

        db.retire_knowledge_unit(db_path, unit_id)
        retired.append(unit_id)
    return retired
