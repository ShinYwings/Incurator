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
import sqlite3
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
    """Read-only compiler-audit result (SCHEMA §20.5, SYSTEM_BEHAVIOR §26.5).

    The release-blocking findings (``release_blocking``) gate the staged
    generation publish (§26.3) and make ``wiki lint`` exit non-zero (§26.5).
    ``unsupported_claims`` (active ``unchecked``/``uncertain`` units) is reported
    for visibility but is not release-blocking — those units are excluded from
    serving, not wrong. ``broad_fallback_plan_c`` is RECORDED and assigned to
    Plan C (community-report/graph-derived fallback, §20.5 assertion 2); Plan B
    surfaces it rather than removing it.
    """

    unsupported_claims: list[str] = field(default_factory=list)
    failed_claims: list[str] = field(default_factory=list)
    stale_claims: list[str] = field(default_factory=list)
    dangling_supports: list[str] = field(default_factory=list)
    formula_inconsistencies: list[str] = field(default_factory=list)
    staged_leftovers: list[str] = field(default_factory=list)
    duplicate_candidates: list[list[str]] = field(default_factory=list)
    broad_fallback_plan_c: list[dict] = field(default_factory=list)

    @property
    def release_blocking(self) -> list[str]:
        """Findings that fail `wiki lint` / block a release (§20.5, §26.5).

        Excludes claims that are already excluded from serving
        (``unchecked``/``uncertain``/``failed``/``stale``). They remain audit
        telemetry, but they are not structural breaks in the served DAG.
        """
        return sorted(
            set(self.dangling_supports)
            | set(self.formula_inconsistencies)
            | set(self.staged_leftovers)
        )

    @property
    def publish_blocking(self) -> list[str]:
        """Findings that block a staged generation publish (§26.3).

        Same structural boundary as ``release_blocking``: a generation publishes
        its sound VERIFIED served set even when failed/stale claims exist,
        because those are excluded from serving (``list_serving_units``). Only
        structural breaks of the served set block the publish.
        """
        return self.release_blocking

    @property
    def ok(self) -> bool:
        """Strict integrity: every active source-supported unit is verified and
        consistent (no unchecked/uncertain/failed/stale/dangling). Used by tests
        and reporting; the publish gate keys on ``release_blocking`` instead."""
        return not (
            self.unsupported_claims
            or self.dangling_supports
            or self.formula_inconsistencies
            or self.staged_leftovers
        )


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


def _load_unit(
    db_path: Path, unit_id: str, *, conn: sqlite3.Connection | None = None
) -> dict | None:
    with db._maybe_conn(db_path, conn) as conn:
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
    db_path: Path, declared: list[str], span_texts: dict[str, str] | None,
    *, conn: sqlite3.Connection | None = None,
) -> dict[str, tuple[str, str]]:
    """Map cited span id -> (text, content_hash). Uses full `span_texts` when
    provided (compile path), else the stored preview (short gold spans). Pass
    ``conn`` so the read joins a caller's transaction (no second connection
    inside an open publish gate)."""
    out: dict[str, tuple[str, str]] = {}
    with db._maybe_conn(db_path, conn) as conn:
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


def _set_semantic_hash(
    db_path: Path, unit_id: str, value: str, *, conn: sqlite3.Connection | None = None
) -> None:
    with db._maybe_conn(db_path, conn) as c:
        c.execute(
            "UPDATE knowledge_units SET semantic_hash = ? WHERE id = ?",
            (value, unit_id),
        )


def _clear_claim_supports(
    db_path: Path, unit_id: str, *, preserve_formula: bool = False,
    has_formula: bool = False, declared: list[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Remove prior/proposed support rows before writing one fresh verdict.

    When ``preserve_formula`` is True, a ``formula`` role row created by
    ``recover_formula`` survives a re-validation cycle — but ONLY while it stays
    relevant: the claim must still carry a formula (``has_formula``) and the
    support's span must still be declared (in ``declared``). A formula support
    for a claim that lost its formula, or that points at a span the claim no
    longer cites, is stale and is cleared too (would otherwise linger / dangle —
    SCHEMA §20.5 #3).
    """
    with db._maybe_conn(db_path, conn) as c:
        if not preserve_formula or not has_formula:
            c.execute(
                "DELETE FROM claim_supports WHERE knowledge_unit_id = ?",
                (unit_id,),
            )
            return
        kept = list(declared or [])
        if kept:
            placeholders = ",".join("?" for _ in kept)
            c.execute(
                "DELETE FROM claim_supports "
                "WHERE knowledge_unit_id = ? "
                "AND (support_role != 'formula' OR source_span_id NOT IN "
                f"({placeholders}))",
                (unit_id, *kept),
            )
        else:
            # No declared spans → every formula support is dangling.
            c.execute(
                "DELETE FROM claim_supports WHERE knowledge_unit_id = ?",
                (unit_id,),
            )


def validate_claim_support(
    db_path: Path,
    unit_id: str,
    *,
    span_texts: dict[str, str] | None = None,
    client: object | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Run the deterministic structural gate on one knowledge unit.

    Writes `claim_supports` rows and sets the unit's `support_status`,
    `formula_status`, and `semantic_hash`. Returns the verdict
    (`verified | failed | uncertain`). `client` is reserved for secondary
    calibrated model validation of `uncertain` text claims; with no client an
    `uncertain` unit stays `unchecked` (never promoted).

    Pass ``conn`` to run every write inside a caller's transaction, so a re-publish
    that validates units rolls back cleanly if the publish gate later fails
    (SYSTEM_BEHAVIOR §26.3) and never mutates the prior authoritative state.
    """
    unit = _load_unit(db_path, unit_id, conn=conn)
    if unit is None:
        raise ValueError(f"unknown knowledge unit: {unit_id}")

    statement: str = unit["statement"]
    declared: list[str] = unit["source_span_ids"]
    spans = _load_spans(db_path, declared, span_texts, conn=conn)

    claim_terms = _content_terms(statement)
    claim_formulas = [_formula_tokens(f) for f in _extract_latex(statement)]
    has_formula = bool(claim_formulas)

    _set_semantic_hash(db_path, unit_id, semantic_hash(statement), conn=conn)
    # Preserve a recovered formula link only while it stays relevant: the claim
    # still has a formula and the support's span is still declared (§20.5 #3).
    _clear_claim_supports(
        db_path, unit_id, preserve_formula=True,
        has_formula=has_formula, declared=declared, conn=conn,
    )

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
        formula_status = (
            "preserved_in_text" if has_formula and formula_ok else "not_applicable"
        )

    # --- persist support rows + unit status ---
    if verdict == "verified":
        assert best_id is not None  # verified ⇒ spans non-empty ⇒ best_id set
        db.upsert_claim_support(
            db_path, knowledge_unit_id=unit_id, source_span_id=best_id,
            support_role="primary", support_status="verified",
            evidence_hash=spans[best_id][1], conn=conn,
        )
        for sid, (_t, chash) in spans.items():
            if sid != best_id:
                db.upsert_claim_support(
                    db_path, knowledge_unit_id=unit_id, source_span_id=sid,
                    support_role="contextual", support_status="verified",
                    evidence_hash=chash, conn=conn,
                )
        db.set_unit_support_status(db_path, unit_id, "verified", conn=conn)
    elif verdict == "failed":
        target = best_id or (declared[0] if declared else None)
        if target and target in spans:
            db.upsert_claim_support(
                db_path, knowledge_unit_id=unit_id, source_span_id=target,
                support_role="primary", support_status="failed",
                evidence_hash=spans[target][1], support_reason=reason, conn=conn,
            )
        db.set_unit_support_status(db_path, unit_id, "failed", reason, conn=conn)
    else:  # uncertain — not promoted; left unchecked with an audit-visible note
        if best_id:
            db.upsert_claim_support(
                db_path, knowledge_unit_id=unit_id, source_span_id=best_id,
                support_role="primary", support_status="unchecked",
                evidence_hash=spans[best_id][1], support_reason=reason, conn=conn,
            )

    db.set_unit_formula_status(db_path, unit_id, formula_status, conn=conn)
    return verdict


def _broad_fallback_findings(db_path: Path) -> list[dict]:
    """Detect generated claims that grounded to the entire upstream span pool —
    the ``or span_ids`` broad fallback (Failure Atlas F6).

    These are community-report / graph-derived artifacts (synthesis nodes and
    community reports), NOT Plan-B-owned source-pair/L2 claims, so per SCHEMA
    §20.5 assertion 2 they are RECORDED and assigned to Plan C rather than
    removed by Plan B. The signature is exact: the claim cites the full union of
    its upstream artifacts' spans (>1 span), which is what the fallback produces
    when an item declares no spans of its own.
    """
    findings: list[dict] = []
    reports = {r["id"]: r for r in db.list_community_reports(db_path)}
    for node in db.list_synthesis_nodes(db_path):
        cited = set(node.get("source_span_ids") or [])
        upstream: set[str] = set()
        for rid in node.get("community_report_ids") or []:
            rep = reports.get(rid)
            if rep:
                upstream.update(rep.get("source_span_ids") or [])
        if len(cited) > 1 and cited == upstream:
            findings.append({"id": node["id"], "type": "synthesis_node", "owner": "plan_c"})
    for rep in reports.values():
        cited = set(rep.get("source_span_ids") or [])
        upstream = set()
        for eid in rep.get("entity_ids") or []:
            ent = db.get_graph_entity(db_path, eid)
            if ent:
                upstream.update(ent.get("source_span_ids") or [])
        if len(cited) > 1 and upstream and cited == upstream:
            findings.append({"id": rep["id"], "type": "community_report", "owner": "plan_c"})
    return findings


def run_compiler_audit(
    db_path: Path, *, conn: sqlite3.Connection | None = None
) -> AuditReport:
    """Read-only compiler audit (SCHEMA §20.5, SYSTEM_BEHAVIOR §26.5).

    Re-checks evidence freshness (marking hash-drifted support stale), then
    asserts the §20.5 invariants on the live DB: verified minimal support,
    no dangling support rows (assertion 3), one authoritative generation per
    scope (assertion 4), formula-status consistency (assertion 5), and records
    broad-fallback findings for Plan C (assertion 2).

    Pass ``conn`` to audit a caller's UNCOMMITTED transaction state, so the
    publish gate (§26.3) checks the exact re-validated rows about to be
    published — not a pre-validation snapshot from a second connection (which
    would also block on the caller's write lock). The broad-fallback scan reads
    synthesis/report/graph tables the publish transaction never mutates, so it
    keeps its own read connection (same result either way).
    """
    db.refresh_support_freshness(db_path, conn=conn)
    with db._maybe_conn(db_path, conn) as conn:
        active = conn.execute(
            "SELECT id, support_status, formula_status, support_reason "
            "FROM knowledge_units "
            "WHERE retired_at IS NULL AND truth_status = 'source_supported'"
        ).fetchall()
        dangling = [
            r["uid"] for r in conn.execute(
                """
                SELECT DISTINCT cs.knowledge_unit_id AS uid
                FROM claim_supports cs
                LEFT JOIN source_spans ss ON ss.id = cs.source_span_id
                LEFT JOIN knowledge_units ku ON ku.id = cs.knowledge_unit_id
                WHERE ss.id IS NULL OR ku.id IS NULL OR ku.retired_at IS NOT NULL
                """
            ).fetchall()
        ]
        multi_auth = [
            f"source:{r['source_id']}" for r in conn.execute(
                "SELECT source_id, COUNT(*) AS c FROM compiler_generations "
                "WHERE status = 'authoritative' GROUP BY source_id HAVING c > 1"
            ).fetchall()
        ]
        units_with_formula = {
            r["uid"] for r in conn.execute(
                "SELECT DISTINCT knowledge_unit_id AS uid FROM claim_supports "
                "WHERE support_role = 'formula' AND support_status = 'verified'"
            ).fetchall()
        }
        # Active units sharing a semantic_hash are reconciliation candidates
        # (§20.1) — reported as a hint, not a release-blocking violation.
        dup_rows = conn.execute(
            "SELECT semantic_hash AS h, GROUP_CONCAT(id) AS ids "
            "FROM knowledge_units "
            "WHERE retired_at IS NULL AND semantic_hash IS NOT NULL AND semantic_hash != '' "
            "GROUP BY semantic_hash HAVING COUNT(*) > 1"
        ).fetchall()
    duplicate_candidates = [sorted(r["ids"].split(",")) for r in dup_rows]
    unsupported = [r["id"] for r in active if r["support_status"] != "verified"]
    failed = [r["id"] for r in active if r["support_status"] == "failed"]
    stale = [r["id"] for r in active if r["support_status"] == "stale"]
    formula_inconsistencies: list[str] = []
    for r in active:
        fs = r["formula_status"]
        if fs == "linked_evidence" and r["id"] not in units_with_formula:
            formula_inconsistencies.append(r["id"])
        elif fs == "omitted_incidental" and not (r["support_reason"] or "").strip():
            formula_inconsistencies.append(r["id"])
    return AuditReport(
        unsupported_claims=unsupported,
        failed_claims=failed,
        stale_claims=stale,
        dangling_supports=sorted(set(dangling)),
        formula_inconsistencies=formula_inconsistencies,
        staged_leftovers=sorted(multi_auth),
        duplicate_candidates=duplicate_candidates,
        broad_fallback_plan_c=_broad_fallback_findings(db_path),
    )


def _reuse_verified_candidate(
    db_path: Path, old_id: str, candidate_id: str, *,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Move a verified semantic-match candidate onto the prior stable id.
    Pass ``conn`` to run inside a caller's transaction (atomic publish)."""
    with db._maybe_conn(db_path, conn) as c:
        candidate = c.execute(
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
        c.execute(
            f"UPDATE knowledge_units SET {assignments}, updated_at = ? WHERE id = ?",
            tuple(candidate[field] for field in fields) + (candidate["updated_at"], old_id),
        )
        c.execute("DELETE FROM claim_supports WHERE knowledge_unit_id = ?", (old_id,))
        c.execute(
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
    db.retire_knowledge_unit(db_path, candidate_id, conn=conn)


def reconcile_source(
    db_path: Path,
    source_id: int,
    *,
    current_span_ids: list[str] | None = None,
    candidate_unit_ids: list[str] | None = None,
    generation_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[str]:
    """Reconcile active units after source edit/delete/split.

    A prior stable unit keeps its id when a newly extracted, verified candidate
    has the same whitespace-normalized statement (the candidate's data — incl.
    generation — is copied onto the stable id, the candidate retires). A prior
    unit whose span basis is UNCHANGED and which no candidate cites (an LLM
    omission, not an edit) is carried forward into ``generation_id`` so it keeps
    its id and survives the publish gate (§26.4: unchanged claims keep their
    ids). A prior unit is retired only when its span basis changed/disappeared OR
    a candidate supersedes it (cites its span with a different statement —
    materially different per §26.4). Semantic hashes only propose candidates and
    never authorize reuse by themselves. Returns every id retired by
    reconciliation.

    Pass ``conn`` to run every mutation inside a caller's transaction, so the
    whole reconcile + publish is atomic (SYSTEM_BEHAVIOR §26.3): any exception
    rolls the prior authoritative state back unchanged. ``generation_id`` is the
    staged generation being published (None for standalone reconciliation, where
    unchanged-basis units are simply left untouched).
    """
    with db._maybe_conn(db_path, conn) as c:
        existing = {
            str(r[0]) for r in c.execute(
                "SELECT id FROM source_spans WHERE source_id = ?", (source_id,)
            ).fetchall()
        }
        current = set(current_span_ids) if current_span_ids is not None else existing
        units = [
            dict(row) for row in c.execute(
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
    # Spans cited by any newly-extracted candidate. A prior unit whose span is
    # cited by a candidate is SUPERSEDED by the fresh extraction — not an
    # omission — so it must not be carried forward (which would duplicate it).
    candidate_spans = {
        sid
        for cand in candidates.values()
        for sid in json.loads(cand["source_span_ids"] or "[]")
    }
    retired: list[str] = []
    for u in units:
        unit_id = str(u["id"])
        if unit_id in candidate_ids:
            continue
        cited = json.loads(u["source_span_ids"] or "[]")
        spans_unchanged = all(sid in current for sid in cited)

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
            _reuse_verified_candidate(db_path, unit_id, match, conn=conn)
            retired.append(match)
            candidates.pop(match)
            continue

        if spans_unchanged and not any(sid in candidate_spans for sid in cited):
            # True omission: span basis unchanged and no candidate cites it, so
            # the LLM merely did not re-emit this claim (§26.4 keeps it). Carry
            # the prior stable unit into the generation being published so it
            # survives the publish gate with its id. Standalone reconciliation
            # (no generation) leaves it untouched, preserving the old behavior.
            if generation_id is not None:
                with db._maybe_conn(db_path, conn) as c:
                    c.execute(
                        "UPDATE knowledge_units SET generation_id = ?, updated_at = ? "
                        "WHERE id = ?",
                        (generation_id, db._now_iso(), unit_id),
                    )
            continue

        # Span basis changed/disappeared, or a candidate supersedes this claim
        # (cites its span with a materially different statement) → retire it.
        db.retire_knowledge_unit(db_path, unit_id, conn=conn)
        retired.append(unit_id)

    # F7 (§26.4): stale spans of the edited source are removed rather than left
    # lingering beside their replacements. Every active unit citing a stale span
    # was retired above, so the deletion cannot orphan an active claim.
    stale_spans = sorted(existing - current)
    if stale_spans:
        db.delete_source_spans(db_path, stale_spans, conn=conn)
    return retired
