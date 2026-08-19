# Briefing: Does the Knowledge System Deliver What It Promises?

Date: 2026-08-06 | master @ `02faa0a` (v0.46.0)

## Why this audit exists

The user asked directly: did we ever check the system against `about.md` /
`README.md` — its stated *purpose* — and did we ever ask what questions a user
would actually pose, then judge whether the knowledge system serves them and
whether the content it returns is any good?

**We had not.** The two prior Arenas audited code-vs-spec and storage
artifacts. Both are infrastructure audits. Neither asked whether the product
does what it exists to do.

## The claims under test (`docs/philosophy/about.md`)

> §4.3 "**Prior Knowledge Utilization**: The agent retrieves a bounded,
> traceable evidence pack selected from the refined live DAG."

> §5.2 "**High-Fidelity Knowledge Grounding (Quality)**: Agent response quality
> and contextual understanding improve because a project-specific Curation lens
> selects bounded evidence from the compiled DAG. The agent doesn't get lost in
> massive datasets, providing hallucination-free answers by leveraging only the
> **refined essence** of curated knowledge."

> §4 "the Curator applies the workspace Knowledge Requirement Specification
> (`curate.yml`) as a **dynamic retrieval lens** over the live DAG."

> §5.6 "**Persona**: the Global Persona … defines the identity of the Curator …
> The Artist Persona (`curate.yml`) overlays workspace-specific context."

The system's whole justification is that L2/L3/L4 refinement makes answers
better and cheaper than raw retrieval. That is a testable claim.

## Measured, already established — do NOT re-derive, DO explain

Four questions were run through `wiki plugin context fetch` against the live
vault. **Q1 and Q2 are questions the user genuinely asked**, recovered from
`.curator/sessions.json`. Raw packs are in this folder as `q1.json`–`q4.json`.

| # | question | route | L4 | L3 | L1 spans | items | sufficiency |
|---|---|---|---|---|---|---|---|
| Q1 | "ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?" (real) | `local` | **0** | **0** | 30 | 39 | partial |
| Q2 | "Kruppa Equation의 제약 조건과 한계는?" (real) | `local` | **0** | **0** | 15 | 19 | partial |
| Q3 | "2D GS가 3D보다 표면 재구성에 유리한 이유를 **여러 논문을 종합해서** 설명해줘" | `local` | **0** | **0** | 26 | 35 | partial |
| Q4 | "How does kernel fusion reduce bottlenecks in Gaussian Splatting pipelines?" | `local` | **0** | **0** | 42 | 58 | partial |

**The vault contains 233 live L3 community reports and 4 L4 synthesis nodes.
Not one of them was served to any of the four questions.** Every pack is
entities + raw L1 spans + flat search hits. Every route decision was `local`
with reason `"entity/fact question"` — including Q3, which explicitly asks for
a cross-paper synthesis.

Every pack self-reports `sufficiency: partial`.

Content-quality signals already counted: Q2 has 7 of 19 items under 40
characters; Q3 and Q4 each carry 3 bibliography-style items; Q4 has 0 items
containing LaTeX despite being about kernel/formula material. Positively, Q1
and Q2 do surface real LaTeX spans (11 and 5), so the formula indexing работает
— reaching them is the issue, not storing them.

**Side observation:** `wiki plugin context fetch` printed a plain-text warning
about the dead source #32 to **stdout on a JSON command**, corrupting the
payload (both Q3 and Q4 needed the prefix stripped before parsing).

## Ground Rules

1. **Read-only.** No code, doc, config, vault, or DB mutation. DB only via
   `?mode=ro`. You MAY run additional `wiki plugin context fetch` queries — that
   is normal read-path use — but run few and say which you ran.
2. Evidence you measured yourself, plus `file:line`. No assertions.
3. Check existing tests before filing.
4. Severity: P0 serving wrong/misleading knowledge; P1 the product fails its
   stated purpose for a real user question; P2 contract/quality gap; P3 drift.
5. Max 6 findings. Depth over breadth.
6. **The question is not "does the code match the spec."** It is "does the user
   get good knowledge for a real question, and if not, why."

## Inspector Domains

1. `intent_vs_behavior` — Take each about.md claim above and rule it TRUE,
   FALSE, or UNVERIFIABLE against the measured packs. Where false, locate the
   precise mechanism. Also check `docs/README.md` and `ABOUT_KR.md` for claims
   that diverge from the English source.
2. `router_and_layers` — Why did all four route `local`, including an explicit
   synthesis request? Read the router. Is the classifier wrong, is the taxonomy
   wrong, or is `local`'s contract wrong? What exactly would have to change for
   a real user question to reach the 233 L3 reports? Judge whether the intended
   L4→L3→L2→L1 descent is a routing fix or a route-contract fix.
3. `content_quality` — Judge the ACTUAL content in the packs. Are the entity
   descriptions useful or tautological ("A method using 2D Gaussian Splatting")?
   Are the L1 spans substantive or fragments? Why is `sufficiency` always
   `partial` — what would make it `sufficient`? Would this pack let a competent
   agent answer the question well? Quote real items.
4. `curation_lens_persona` — Do `curate.yml` (Artist persona / KRS) and the
   vault persona actually influence retrieval? Trace from the settings file to
   the query. A prior audit found the sidechat always passes the vault ROOT as
   `workspace_path`. Verify or refute, and determine whether §4 and §5.6 of
   about.md are implemented at all on the surfaces a user actually uses.

## Debate Protocol

Write `01_proposal_<domain>.md` here. Red-teamers then write
`02_critique_<domain>.md` attempting to refute each finding. Only survivors
reach synthesis.
