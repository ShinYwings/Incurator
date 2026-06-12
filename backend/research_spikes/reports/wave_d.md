# Plan E Wave D Report

Date: 2026-06-12
Status: Completed; awaiting PM review before Wave E/P7

## Scope

Wave D (Plan E P6) isolated formula-loss boundaries and compared:

- parser-only formula output;
- current extraction, including the existing raw-text fallback;
- confidence-gated selective recovery on proven-loss regions;
- whole-corpus heavy recovery as a separately costed rejected-default control.

The committed synthetic corpus contains text-layer loss, downstream
distillation loss, image-only loss, an ambiguous visual formula, an intact
no-recovery case, source-page update cases, and an inaccessible holdout.
Formula strings are deterministic oracle labels. No provider, vision model,
model judge, production state, testbed state, network call, or holdout was used.

This spike evaluates the recovery contract, not a particular VLM's recognition
quality. It does not authorize production formula-recovery code or dependencies.

## Exact Loss Boundary

| Case | Parser loss | Raw-fallback recovery | Current-extraction loss | Distillation loss |
|---|---:|---:|---:|---:|
| FR01 text layer + distillation | 1 | 1 | 0 | 1 |
| FR02 image-only | 2 | 0 | 2 | 0 |
| FR03 ambiguous visual | 1 | 0 | 1 | 0 |
| FR04 intact | 0 | 0 | 0 | 0 |

FR01 proves two separate boundaries. Parser-only output omits
`h_{k+1} = h_k + F_k(h_k)`, while the current raw-text fallback restores it in
current extraction. The same formula is then absent from current distillation.
Selective visual recovery is therefore not a complete answer to formula loss:
formula-preserving distillation remains a separate Program-2 requirement.

FR02 and FR03 prove the residual extraction boundary. Their formulas exist only
in image regions, so neither parser-only output nor current extraction can
recover them from the text layer.

## Policy Results

| Policy | Formula recall |
|---|---:|
| Parser-only | 0.33 |
| Current extraction | 0.50 |
| Selective recovery | 0.83 |

Current extraction beats parser-only because raw-text fallback restores the
text-layer omission in FR01. Selective recovery adds the two exact FR02 formulas
to current extraction, improving recall from `0.50` to `0.83`.

The remaining missed formula is FR03. Its synthetic recovery candidate confuses
`Z` with `2`, producing a recovery-candidate error rate of `0.33`. Because its
confidence is `0.42`, below the frozen `0.80` acceptance threshold, it remains
an explicitly `uncertain` recovery record with source locator and page hash and
does not enter observed formulas. Accepted-recovery error rate is therefore
`0.00`.

| Safety metric | Result |
|---|---:|
| Raw-evidence preservation | 1.00 |
| Hallucinated replacement rate | 0.00 |
| Recovery-candidate error rate | 0.33 |
| Accepted-recovery error rate | 0.00 |

Recovered content is always a separate record. It never overwrites parser,
raw-text, or current-extraction evidence. A wrong uncertain candidate is still
reported so the aggregate cannot hide recognition error.

## Cost

| Policy | Processed pages | Cost units |
|---|---:|---:|
| Selective proven-loss recovery | 2 | 20 |
| Whole-corpus heavy recovery | 14 | 140 |

Selective recovery processes only FR02 and FR03, the two measured fixtures with
proven loss regions and recovery candidates. Whole-corpus recovery processes
every page even for FR01, where current extraction already has both formulas,
and FR04, where no loss exists. Under the frozen per-page proxy, whole-corpus
processing costs `7x` more.

The cost units are hand-computable proxies, not measured VLM latency or money.
A real provider benchmark remains required before any mechanism decision.

## Update Behavior

Recovered output binds to the exact source-page hash:

| Update | Page changed | Recovery invalidated | Selective reprocessed pages | Whole-corpus reprocessed pages |
|---|---:|---:|---:|---:|
| FU01 formula page edit | yes | yes | 1 | 5 |
| FU02 unrelated edit; formula page unchanged | no | no | 0 | 5 |

Invalidation accuracy is `1.00`; stale recovered output is never served. The
selective policy reprocesses one changed page across both updates, compared with
ten pages for whole-corpus processing. This is a page-hash contract result, not
proof of production dependency-closure invalidation.

## Scoped Decision Posture

### Selective Formula Recovery

`benchmark-later`; adopt only the provenance and gating invariants as downstream
contract candidates.

- Contract candidate: recovery may run only after a proven extraction-loss
  signal identifies a bounded source region.
- Contract candidate: recovered content must remain separate from raw/parser
  evidence and carry confidence, exact source locator, and source-page hash.
- Contract candidate: low-confidence recovery must remain explicitly uncertain
  and must not silently enter accepted formula evidence.
- Contract candidate: source-page hash changes must invalidate recovered output;
  unchanged formula pages should not trigger heavy reprocessing.
- Evidence: selective recovery improved formula recall from `0.50` to `0.83`,
  preserved raw evidence, accepted no wrong candidate, and cost `20` versus
  `140` proxy units for whole-corpus recovery.
- Downstream owner: Program 2 (`B_math_extraction_distillation.md`).
- Revisit trigger: benchmark a concrete provider/model on real, licensed,
  proven-loss pages; measure recognition quality, latency, money, dependency
  footprint, and deletion/update behavior; then run the untouched holdout.

### Formula-Preserving Distillation

`adopt-contract` candidate, pending P7 holdout/provenance audit.

- Contract candidate: a formula present in authoritative extraction must not be
  silently removed by downstream distillation; formula recall must be measured
  at both extraction and distillation boundaries.
- Evidence: FR01 is complete in current extraction but loses one of two formulas
  in current distillation. Visual recovery of parser-loss regions does not fix
  that downstream loss.
- Downstream owner: Program 2.

## Rejected Defaults

- Whole-corpus VLM or heavy visual recovery as the default extraction path.
- Any recovery that overwrites raw/parser evidence.
- Treating a recovered candidate as accepted without an explicit confidence
  state and source locator.
- Treating selective visual recovery as a fix for downstream distillation loss.
- Reprocessing an entire source when the bound formula page is unchanged.
- Interpreting deterministic synthetic recovery output as proof of a specific
  model's formula-recognition quality.

## Limitations

- Formula fixtures and recovery candidates are synthetic deterministic oracle
  labels. No VLM was executed, so real recognition quality, latency, cost,
  provider behavior, and dependency impact remain unmeasured.
- The confidence threshold is frozen for this spike but not calibrated against a
  representative formula distribution.
- Current extraction and distillation outputs are modeled from observed system
  boundaries; the runner does not invoke production PDF parsing or LLM
  distillation.
- Page-hash invalidation is enforced by construction over update fixtures; live
  dependency closure and delete behavior remain for Program 2 and P7 audit.
- The untouched holdout remains inaccessible until P7.
