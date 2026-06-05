"""v0.3.2 search parity benchmark: native DB-hybrid vs qmd.

Builds a controlled corpus (distinct topics + paraphrase queries + near-miss
distractors) so the comparison is meaningful, then measures recall@3 and MRR@10 for:
  - native  hybrid+rerank   (FTS5 + Qwen3-Embedding-0.6B + RRF + Qwen3-Reranker)
  - native  + qmd GGUF expansion (qmd-query-expansion-1.7B, when cached)
  - native  + chat expansion (EXPANDER_MODEL or PROD_EXPANDER_SPEC)
  - native  lex             (FTS5 BM25 only)
  - qmd     query           (BM25 + EmbeddingGemma-300M + expansion + Qwen3-Reranker)
  - qmd     search          (BM25 only)

Same doc-id space for both (markdown filename == record_id), so metrics align.
Requires: llama-cpp models in ~/.cache/incurator/models (wiki models ensure) and
the qmd binary with its models cached. Run:
    uv run --project backend python scripts/benchmarks/search_parity_bench.py
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# (id, title, body) — distinct topics with several lexical near-miss distractors
# (e.g. D31-D36) so vector + rerank quality matters, not just keyword overlap.
DOCS = [
    # biology
    ("D01", "Photosynthesis", "Plants convert sunlight into chemical energy stored as glucose using chlorophyll in the leaves."),
    ("D02", "Cellular respiration", "Mitochondria break down glucose with oxygen to produce ATP, the energy currency of the cell."),
    ("D03", "DNA replication", "DNA polymerase copies the double helix so each daughter cell receives an identical genome."),
    ("D04", "Protein folding", "A polypeptide chain folds into a three-dimensional shape that determines its biological function."),
    ("D05", "Immune response", "White blood cells recognize antigens and produce antibodies to neutralize invading pathogens."),
    # deep learning
    ("D06", "Transformer attention", "Self-attention lets each token weigh every other token, capturing long-range dependencies in sequences."),
    ("D07", "Residual networks", "Skip connections add the input back to the output of a block, easing optimization of very deep networks."),
    ("D08", "Gradient descent", "Parameters are updated in the direction opposite the loss gradient to minimize training error."),
    ("D09", "Batch normalization", "Normalizing layer activations per mini-batch stabilizes and speeds up neural network training."),
    ("D10", "Dropout regularization", "Randomly zeroing units during training prevents co-adaptation and reduces overfitting."),
    # distributed systems
    ("D11", "Raft consensus", "A leader replicates a log to followers; entries commit once a majority of the cluster acknowledges them."),
    ("D12", "Two-phase commit", "A coordinator asks all participants to prepare, then tells them to commit or abort atomically."),
    ("D13", "Vector clocks", "Each process keeps a counter vector so events can be partially ordered across a distributed system."),
    ("D14", "Consistent hashing", "Keys and nodes map onto a ring so adding or removing a node moves only a small fraction of keys."),
    # databases / IR
    ("D15", "B-tree index", "A balanced tree keeps data sorted so lookups, inserts, and range scans run in logarithmic time."),
    ("D16", "SQLite FTS5", "The full-text search extension builds an inverted index and ranks matches with the BM25 algorithm."),
    ("D17", "Reciprocal rank fusion", "RRF merges several ranked lists by summing one over k plus rank, needing no score normalization."),
    ("D18", "Vector cosine similarity", "Nearest-neighbour retrieval compares embedding vectors by the cosine of the angle between them."),
    ("D19", "Write-ahead logging", "Changes are appended to a log before the main store so the database can recover after a crash."),
    ("D20", "Cross-encoder reranking", "A model scores each query-passage pair jointly to reorder candidates by fine-grained relevance."),
    # earth / climate
    ("D21", "Carbon cycle", "Carbon moves between atmosphere, oceans, and living things through respiration, photosynthesis, and combustion."),
    ("D22", "Greenhouse effect", "Atmospheric gases trap outgoing infrared radiation, warming the planet's surface."),
    ("D23", "Plate tectonics", "Earth's lithosphere is broken into plates that drift, causing earthquakes and mountain building."),
    ("D24", "Water cycle", "Water evaporates, condenses into clouds, and returns as precipitation in a continuous loop."),
    # physics
    ("D25", "Special relativity", "Time dilation and length contraction arise because the speed of light is constant for all observers."),
    ("D26", "Quantum entanglement", "Two particles share a joint state so measuring one instantly constrains the other's outcome."),
    ("D27", "Thermodynamics second law", "The entropy of an isolated system never decreases, setting the arrow of time."),
    # economics
    ("D28", "Supply and demand", "Prices settle where the quantity buyers want equals the quantity sellers offer in a market."),
    ("D29", "Inflation", "A sustained rise in the general price level reduces the purchasing power of money over time."),
    ("D30", "Comparative advantage", "Nations gain from trade by specializing in goods they produce at lower opportunity cost."),
    # lexical near-miss distractors (share words with queries but wrong topic)
    ("D31", "Energy drinks", "Caffeinated energy drinks give a short-term boost but are unrelated to cellular metabolism."),
    ("D32", "Attention in classrooms", "Teachers use activities to hold student attention, a topic in education, not machine learning."),
    ("D33", "Mountain climbing", "Climbers ascend deep mountain networks of trails; unrelated to neural network depth."),
    ("D34", "Political consensus", "Reaching consensus among voters differs entirely from distributed system agreement protocols."),
    ("D35", "Library book ranking", "A library ranks popular books by checkout counts, unrelated to search index ranking."),
    ("D36", "Greenhouse gardening", "A glass greenhouse helps gardeners grow plants; not the atmospheric greenhouse effect."),
]

DOCS = DOCS + [
    ("D37", "Compiler register allocation", "Register allocation assigns program variables to limited CPU registers while minimizing spills to memory."),
    ("D38", "Garbage collection", "A runtime garbage collector reclaims unreachable heap objects so programs avoid manual memory deallocation."),
    ("D39", "Deadlock prevention", "Systems prevent deadlock by breaking mutual exclusion, hold-and-wait, no-preemption, or circular wait conditions."),
    ("D40", "Cache coherence", "Coherence protocols keep replicated cache lines consistent across CPU cores after reads and writes."),
    ("D41", "Database isolation levels", "Isolation levels control which concurrent transaction anomalies are allowed, from read committed to serializable."),
    ("D42", "Serializable transactions", "Serializable isolation makes concurrent transactions behave as if they executed one at a time."),
    ("D43", "Event sourcing", "Event sourcing stores immutable domain events and reconstructs current state by replaying the event log."),
    ("D44", "CQRS", "Command query responsibility segregation separates write-side commands from read-side query models."),
    ("D45", "Kalman filter", "A Kalman filter recursively estimates hidden state by combining a motion model with noisy measurements."),
    ("D46", "Particle filter", "A particle filter represents belief with weighted samples for nonlinear or non-Gaussian state estimation."),
    ("D47", "Bayesian inference", "Bayesian inference updates prior beliefs into posterior probabilities after observing evidence."),
    ("D48", "Maximum likelihood", "Maximum likelihood chooses parameters that make the observed data most probable under a statistical model."),
    ("D49", "Fourier transform", "The Fourier transform decomposes a signal into frequency components using sinusoidal basis functions."),
    ("D50", "Convolution theorem", "The convolution theorem says convolution in time corresponds to multiplication in the frequency domain."),
    ("D51", "PID control", "A PID controller combines proportional, integral, and derivative terms to reduce tracking error."),
    ("D52", "Model predictive control", "Model predictive control solves a finite-horizon optimization problem repeatedly to choose control actions."),
    ("D53", "Bloom filter", "A Bloom filter is a probabilistic set structure that can report false positives but never false negatives."),
    ("D54", "Count-min sketch", "A count-min sketch estimates item frequencies in a stream using multiple hashed counters."),
    ("D55", "Merkle tree", "A Merkle tree hashes leaves and internal nodes so a small proof can verify membership in a data set."),
    ("D56", "CRDT", "Conflict-free replicated data types merge concurrent updates without coordination and converge across replicas."),
    ("D57", "Memory leak", "A memory leak occurs when allocated objects remain reachable or unreleased even though the program no longer needs them."),
    ("D58", "Traffic deadlock", "Cars blocking an intersection create traffic deadlock, unrelated to operating-system resource cycles."),
    ("D59", "Noise measurement", "A microphone can measure noisy signals, but this does not estimate hidden dynamical state."),
    ("D60", "Frequency marketplace", "Advertisers buy radio frequency slots in a market; unrelated to Fourier signal decomposition."),
    ("D61", "Tree membership club", "A membership club for tree climbers shares words with Merkle tree membership but not cryptographic proofs."),
    ("D62", "Sketch drawing", "Artists use sketches to plan images; unrelated to streaming frequency estimation."),
    ("D63", "Command leadership", "Military command responsibility differs from CQRS command-query separation."),
    ("D64", "Predictive maintenance", "Maintenance teams forecast equipment failure; not model predictive control of dynamical systems."),
]

# (query, set of relevant ids) — ground truth by topical relevance. Several queries
# are paraphrases whose relevant doc shares few/no keywords (vector/rerank needed),
# and several share keywords with a distractor (precision test).
QUERIES = [
    ("how do cells make energy from sugar", {"D02"}),
    ("what helps train very deep neural networks", {"D07", "D09"}),
    ("mechanism that lets a model focus on relevant words", {"D06"}),
    ("how do distributed nodes agree on a value", {"D11", "D12"}),
    ("combining multiple ranked result lists into one", {"D17"}),
    ("data structure for fast sorted lookups and range queries", {"D15"}),
    ("comparing embeddings for semantic search", {"D18"}),
    ("why is the planet getting warmer", {"D22"}),
    ("how plants capture light to make food", {"D01"}),
    ("keyword ranking with an inverted index", {"D16"}),
    ("preventing a neural network from overfitting", {"D10"}),
    ("reorder search candidates by joint relevance scoring", {"D20"}),
    ("how does a database recover after a crash", {"D19"}),
    ("spreading keys evenly across servers when nodes change", {"D14"}),
    ("why does time slow down at high speed", {"D25"}),
    ("two particles whose measurements are correlated", {"D26"}),
    ("what raises the cost of living over the years", {"D29"}),
    ("how the body fights infection", {"D05"}),
    ("why do prices go up when something is scarce", {"D28"}),
    ("how a shape of a protein decides what it does", {"D04"}),
]

QUERIES = QUERIES + [
    ("placing variables into scarce processor storage locations", {"D37"}),
    ("automatically freeing heap objects nobody can reach anymore", {"D38"}),
    ("avoiding circular resource waits in an operating system", {"D39"}),
    ("keeping per-core copies of the same memory line consistent", {"D40"}),
    ("what prevents dirty reads and phantom anomalies", {"D41", "D42"}),
    ("rebuilding application state from an append-only history of facts", {"D43"}),
    ("separating writes from read models in an application architecture", {"D44"}),
    ("estimating a hidden state from a model and noisy observations", {"D45"}),
    ("tracking nonlinear uncertainty with weighted random samples", {"D46"}),
    ("turning a prior belief into a posterior after evidence", {"D47"}),
    ("choosing parameters that best explain the observed sample", {"D48"}),
    ("breaking a waveform into its spectral components", {"D49"}),
    ("why filtering can be multiplication after changing domains", {"D50"}),
    ("control loop that uses present past and anticipated error terms", {"D51"}),
    ("choosing actions by repeatedly solving a short horizon control optimization", {"D52"}),
    ("space efficient membership test that may lie only one way", {"D53"}),
    ("estimating stream item counts with hashed counters", {"D54"}),
    ("verifying an item belongs to a hashed tree with a compact proof", {"D55"}),
    ("replicated data structure that converges without coordination", {"D56"}),
    ("why memory keeps growing after objects are no longer useful", {"D57"}),
]

ADVERSARIAL_DOCS = [
    ("A01", "Studio pigment blending", "Acrylic oil paint color mixing guide ratios: combine primary colors red blue yellow, blend small amounts, add white for tints and black for shades."),
    ("A02", "Industrial paint mixer maintenance", "A factory paint mix machine needs blade cleaning, solvent flushing, and motor inspection after each batch."),
    ("A03", "Concrete admixture ratios", "Construction crews mix aggregate, cement, and water for slabs; this is not about canvas color blending."),
    ("A04", "Palette inventory", "An art studio tracks brushes, easels, and palettes but gives no instructions for pigment combinations."),

    ("A05", "Browser email access", "Webmail client email browser access lets users read, compose, and manage an online email inbox through Gmail, Outlook, Yahoo Mail, or ProtonMail."),
    ("A06", "Postal sorting workflow", "Mail carriers sort envelopes and parcels by delivery route before loading trucks."),
    ("A07", "Spider web structure", "Orb-weaver webs catch insects through sticky silk strands and radial threads."),
    ("A08", "Email server DNS records", "MX, SPF, DKIM, and DMARC records configure mail delivery and authentication but not browser inbox usage."),

    ("A09", "Programming file input output", "File I/O input output operations open, read, write, append, flush, and close streams in Python, Java, or C."),
    ("A10", "Office filing cabinet", "Paper files are organized in folders and drawers with labels for administrative retrieval."),
    ("A11", "IO psychology overview", "Industrial-organizational psychology studies workplace hiring, assessment, and motivation."),
    ("A12", "Binary serialization", "Serialization stores structured objects as bytes, but this note does not cover opening files or stream modes."),

    ("A13", "Progressive strength training", "Build up strength with progressive overload: gradually increase weight, reps, or sets, eat adequate protein, and rest between sessions."),
    ("A14", "Urban building construction", "A contractor builds up additional floors on a mixed-use tower with steel beams and concrete slabs."),
    ("A15", "Sediment accumulation", "River deltas build up layers of silt over years of deposition."),
    ("A16", "Fundraising runway", "A startup builds up cash reserves before hiring more employees."),

    ("A17", "Damaged hair repair", "Fix hair by repairing damaged dry frizzy strands with keratin masks, argan oil, split-end trims, heat protectant, and gentle styling."),
    ("A18", "Salon scheduling", "A salon appointment system books stylists, chairs, and customer reminders."),
    ("A19", "Photo retouching flyaways", "Portrait editors remove stray hairs in Photoshop using clone and healing tools."),
    ("A20", "Bathroom drain clog", "Hair can clog a shower drain and may require a snake or enzymatic cleaner."),

    ("A21", "Photography exposure meter", "A handheld incident reflected light meter measures exposure by ISO, aperture, and shutter speed for photography lighting."),
    ("A22", "Electric utility meter", "A smart electricity meter records kilowatt-hour consumption for billing."),
    ("A23", "Light fixture installation", "An electrician installs ceiling lights, switches, and dimmers according to wiring code."),
    ("A24", "Parking meter display", "A street parking meter has a backlit display and accepts card payments."),

    ("A25", "Garden soil acidity test", "Soil pH test kit method: mix garden soil with distilled water, add indicator solution, compare color, or insert a calibrated meter probe."),
    ("A26", "Soil erosion control", "Mulch, terraces, and cover crops reduce topsoil loss on slopes."),
    ("A27", "Pool water pH", "Swimming pool pH is adjusted with acid or soda ash to protect swimmers and equipment."),
    ("A28", "Lab pH electrode care", "A glass pH electrode must be stored in solution and calibrated before laboratory measurements."),

    ("A29", "Brand mark design process", "Create a brand logo by researching audience and values, sketching concepts, choosing typography and color, and testing scalability in black and white."),
    ("A30", "Product brand guidelines", "A brand style guide documents tone, spacing, color tokens, and approved lockups after the logo already exists."),
    ("A31", "Livestock branding iron", "Ranchers use a heated brand mark to identify cattle ownership."),
    ("A32", "Team logo trivia", "Sports fans rank famous logos by popularity and merchandise sales."),
]

ADVERSARIAL_QUERIES = [
    ("paint mix", {"A01"}),
    ("web mail", {"A05"}),
    ("io file", {"A09"}),
    ("build up", {"A13"}),
    ("fix hair", {"A17"}),
    ("light meter", {"A21"}),
    ("how to test soil ph", {"A25"}),
    ("how to create a brand logo", {"A29"}),
]

K = 3


def _active_docs() -> list[tuple[str, str, str]]:
    import os

    scenario = os.environ.get("BENCH_SCENARIO", "standard").strip().lower()
    if scenario == "adversarial":
        return ADVERSARIAL_DOCS
    return DOCS


def _active_queries() -> list[tuple[str, set[str]]]:
    import os

    scenario = os.environ.get("BENCH_SCENARIO", "standard").strip().lower()
    base = ADVERSARIAL_QUERIES if scenario == "adversarial" else QUERIES
    offset = int(os.environ.get("BENCH_QUERY_OFFSET", "0"))
    limit_raw = os.environ.get("BENCH_QUERY_LIMIT", "").strip()
    selected = base[offset:]
    if limit_raw:
        selected = selected[:int(limit_raw)]
    return selected


def _recall_mrr(results: dict[str, list[str]]) -> tuple[float, float, float]:
    recalls, rrs, recall10 = [], [], []
    queries = _active_queries()
    for q, relevant in queries:
        ranked = results.get(q, [])
        recalls.append(len(set(ranked[:K]) & relevant) / len(relevant))
        recall10.append(len(set(ranked[:10]) & relevant) / len(relevant))
        rr = 0.0
        for i, doc in enumerate(ranked, 1):
            if doc in relevant:
                rr = 1.0 / i
                break
        rrs.append(rr)
    n = len(queries)
    return sum(recalls) / n, sum(rrs) / n, sum(recall10) / n


def _qmd_expander_path() -> Path:
    return Path.home() / ".cache/qmd/models/hf_tobil_qmd-query-expansion-1.7B-q4_k_m.gguf"


def run_native(expander_kind: str = "none") -> dict[str, list[str]]:
    import os

    from curator import db
    from curator.retrieval import embedding, providers
    from curator.retrieval import engine as _eng
    from curator.retrieval.engine import HybridEngine

    # allow experimenting with the rerank blend (default 0.7 cross-encoder-led)
    _eng._RERANK_ALPHA = float(os.environ.get("RERANK_ALPHA", "0.7"))

    tmp = Path(tempfile.mkdtemp(prefix="parity-native-"))
    dbp = tmp / "state.sqlite"
    db.init_db(dbp)
    for did, title, body in _active_docs():
        db.upsert_search_document(
            dbp, record_type="knowledge_unit", record_id=did, title=title,
            body=body, content_hash=did, dependency_hash=did,
        )
    embedding.materialize_chunks(dbp)
    import curator.constants as c
    scfg = {
        "embedding": f"{c.DEFAULT_EMBED_PROVIDER}::{c.DEFAULT_EMBED_MODEL}",
        "embedding_dim": c.DEFAULT_EMBED_DIM, "embedding_gguf_file": c.DEFAULT_EMBED_GGUF_FILE,
        "rerank": True, "reranker": f"{c.DEFAULT_RERANK_PROVIDER}::{c.DEFAULT_RERANK_MODEL}",
        "reranker_gguf_file": c.DEFAULT_RERANK_GGUF_FILE,
        "fuse_cap": int(os.environ.get("FUSE_CAP", "12")),
    }
    embedder = providers.build_embedder(scfg)
    embedding.embed_corpus(dbp, embedder)
    reranker = providers.build_reranker(scfg)
    expander = None
    if expander_kind == "chat":
        from curator.retrieval.query_expander import build_query_expander
        exp_model = os.environ.get("EXPANDER_MODEL", "qwen2.5:0.5b")
        if exp_model:
            exp_cfg = {
                "search": {"query_expansion": True},
                "llm": {"primary": f"ollama::{exp_model}", "fallback": "",
                        "ollama": {"host": c.DEFAULT_OLLAMA_HOST}},
            }
            expander = build_query_expander(exp_cfg, want_hyde=True)
    elif expander_kind == "prod":
        from curator.retrieval.query_expander import build_query_expander
        spec = os.environ.get("PROD_EXPANDER_SPEC", "").strip()
        if spec:
            expander = build_query_expander(
                {"search": {"query_expansion": True}, "llm": {"primary": spec, "fallback": ""}},
                want_hyde=True,
            )
    elif expander_kind == "qmd":
        from curator.retrieval.query_expander import LlamaCppExpander
        path = Path(os.environ.get("QMD_EXPANDER_GGUF", str(_qmd_expander_path())))
        if path.exists():
            expander = LlamaCppExpander("qmd-query-expansion-1.7b", str(path))

    engine_exp = HybridEngine(
        dbp,
        {
            **scfg,
            "query_expansion": bool(expander),
            "expansion_recovery_only": os.environ.get("EXPANSION_RECOVERY_ONLY", "1") != "0",
        },
        embedder=embedder,
        reranker=reranker,
        expander=expander,
    )

    results = {}
    for q, _ in _active_queries():
        eres = engine_exp.search(q, mode="hybrid", limit=10, rerank=True, want_hyde=True, persist=False)
        results[q] = [h.record_id for h in eres.hits]
    return results


def run_native_lex() -> dict[str, list[str]]:
    import os

    from curator import db
    from curator.retrieval import embedding
    from curator.retrieval import engine as _eng
    from curator.retrieval.engine import HybridEngine

    _eng._RERANK_ALPHA = float(os.environ.get("RERANK_ALPHA", "0.7"))
    tmp = Path(tempfile.mkdtemp(prefix="parity-native-lex-"))
    dbp = tmp / "state.sqlite"
    db.init_db(dbp)
    for did, title, body in _active_docs():
        db.upsert_search_document(
            dbp, record_type="knowledge_unit", record_id=did, title=title,
            body=body, content_hash=did, dependency_hash=did,
        )
    embedding.materialize_chunks(dbp)
    engine = HybridEngine(dbp, {}, embedder=None, reranker=None)
    results = {}
    for q, _ in _active_queries():
        lres = engine.search(q, mode="lex", limit=10, rerank=False, persist=False)
        results[q] = [h.record_id for h in lres.hits]
    return results


def run_qmd() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    import os

    tmp = Path(tempfile.mkdtemp(prefix="parity-qmd-"))
    docs_dir = tmp / "docs"
    docs_dir.mkdir(parents=True)
    for did, title, body in _active_docs():
        (docs_dir / f"{did}.md").write_text(f"# {title}\n{body}\n", encoding="utf-8")

    # qmd's default index is GLOBAL (~/.qmd). Isolate fully via INDEX_PATH +
    # QMD_CONFIG_DIR so a pre-existing collection cannot pollute the benchmark.
    env = {**os.environ, "INDEX_PATH": str(tmp / "index.sqlite"), "QMD_CONFIG_DIR": str(tmp)}
    env_cwd = str(tmp)
    def _qmd(args: list[str]) -> str:
        return subprocess.run(["qmd", *args], cwd=env_cwd, env=env, capture_output=True, text=True).stdout

    # Absolute path: qmd resolves a relative collection path against its own cwd
    # notion, not the subprocess cwd, which silently indexes the wrong folder.
    _qmd(["collection", "add", str(docs_dir)])
    _qmd(["update"])
    _qmd(["embed"])

    def _ids(raw: str) -> list[str]:
        raw = _ANSI.sub("", raw)  # qmd mixes spinner/ANSI codes into stdout
        s, e = raw.find("["), raw.rfind("]")
        if s < 0 or e <= s:
            return []
        try:
            rows = json.loads(raw[s:e + 1])
        except Exception:
            return []
        out = []
        for r in rows:
            f = str(r.get("file") or r.get("path") or "")
            out.append(Path(f.split("/")[-1]).stem)
        return out

    query, search = {}, {}
    for q, _ in _active_queries():
        query[q] = _ids(_qmd(["query", q, "--json", "-n", "10"]))
        search[q] = _ids(_qmd(["search", q, "--json", "-n", "10"]))
    return query, search


def _run_subprocess_half(mode: str) -> dict[str, dict[str, list[str]]]:
    """Run one engine's half in a fresh process (native llama-cpp and qmd must not
    coexist in one process — loading both segfaults)."""
    import sys
    r = subprocess.run([sys.executable, __file__, mode], capture_output=True, text=True)
    raw = r.stdout
    s, e = raw.find("{"), raw.rfind("}")
    if s < 0 or e <= s:
        raise RuntimeError(
            f"{mode} half produced no JSON (exit={r.returncode}).\n"
            f"stdout:\n{raw[-500:]}\nstderr:\n{r.stderr[-800:]}"
        )
    return json.loads(raw[s:e + 1])


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1].startswith("native"):
        _, _, kind = sys.argv[1].partition(":")
        kind = kind or "none"
        if kind == "lex":
            print(json.dumps({"lex": run_native_lex()}))
        else:
            print(json.dumps({kind: run_native(kind)}))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "qmd":
        query, search = run_qmd()
        print(json.dumps({"query": query, "search": search}))
        return

    print("Running native engine (Qwen3 embed+rerank) in isolated processes…")
    native_none = _run_subprocess_half("native:none")["none"]
    native_chat = None
    if __import__("os").environ.get("EXPANDER_MODEL", "qwen2.5:0.5b").strip():
        native_chat = _run_subprocess_half("native:chat")["chat"]
    native_qmd = None
    if __import__("os").environ.get("RUN_QMD_EXPANDER", "") == "1":
        native_qmd = _run_subprocess_half("native:qmd")["qmd"]
    native_lex = _run_subprocess_half("native:lex")["lex"]
    native_prod = None
    if __import__("os").environ.get("PROD_EXPANDER_SPEC", "").strip():
        native_prod = _run_subprocess_half("native:prod")["prod"]
    print("Running qmd (EmbeddingGemma + expansion + Qwen3 rerank) in isolated process…")
    q = _run_subprocess_half("qmd")

    rows = [
        ("native hybrid+rerank", native_none),
        *([("native +chat expansion", native_chat)] if native_chat is not None else []),
        *([("native +qmd-1.7B expansion", native_qmd)] if native_qmd is not None else []),
        *([("native +prod expansion", native_prod)] if native_prod is not None else []),
        ("native lex (FTS5)", native_lex),
        ("qmd query (full)", q["query"]),
        ("qmd search (BM25)", q["search"]),
    ]
    print(f"\n{'engine':<26}{'recall@'+str(K):<12}{'MRR@10':<10}{'recall@10':<10}")
    print("-" * 58)
    for name, res in rows:
        r, m, r10 = _recall_mrr(res)
        print(f"{name:<26}{r:<12.3f}{m:<10.3f}{r10:<10.3f}")

    scenario = __import__("os").environ.get("BENCH_SCENARIO", "standard").strip().lower()
    total_queries = len(ADVERSARIAL_QUERIES if scenario == "adversarial" else QUERIES)
    print(f"\nScenario: {scenario}")
    print(f"Corpus: {len(_active_docs())} docs · {len(_active_queries())}/{total_queries} queries · ground-truth topical relevance")
    print("Env controls: BENCH_SCENARIO, BENCH_QUERY_OFFSET, BENCH_QUERY_LIMIT, FUSE_CAP, EXPANDER_MODEL, PROD_EXPANDER_SPEC, RUN_QMD_EXPANDER")


if __name__ == "__main__":
    main()
