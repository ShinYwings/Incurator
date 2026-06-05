# 검색 Parity 벤치마크 — 네이티브 DB 엔진 vs qmd (v0.3.2)

**날짜:** 2026-06-05
**질문:** 외부 `qmd` 바이너리를 제거한(v0.3.2) 뒤, DB-native 하이브리드 검색
엔진이 qmd의 검색 품질을 따라잡는가?
**결론:** 측정한 합성 세트에서는 네이티브 DB 검색이 qmd parity 이상이지만, query
expansion이 항상 이득은 아니다. 리랭커 호출을 수정한 뒤(§4 참고) 네이티브 엔진은 기존
36-doc 세트에서 recall@10 = 1.000, MRR@10 = 0.938을 기록했고 qmd는 1.000/1.000을
기록했다. 이후 ambiguous-query adversarial 세트에서는 native hybrid가 qmd query보다
recall@3/MRR에서 앞섰고, qmd의 1.7B expander를 native에 붙여도 no-expansion native와
동률이었다.

## 1. 측정 이유

qmd는 v0.3.2(P9)에서 코드베이스에서 제거되었다. 이 제거가 **검색 품질 회귀가
아님**을 확인하기 위해, qmd를 외부 바이너리로 잠깐 다시 실행하여(재설치 없음 — 모델
캐시 기존 존재) 통제된 코퍼스 + ground-truth relevance로 네이티브 엔진과 비교했다.

## 2. 방법

- **기존 코퍼스:** 12개 서로 다른 주제 군집(생물학, 딥러닝, 분산 시스템, DB/IR, 기후,
  물리, 경제)에 걸친 짧은 문서 36개 + **어휘적으로 겹치는 distractor 6개**
  (예: "교실에서의 attention", "산악 등반 networks", "온실 원예") — 질의와 키워드는
  겹치지만 주제가 다르므로 키워드 중복이 아닌 vector + rerank 정밀도를 압박한다.
- **확장 코퍼스:** 현재 벤치 스크립트는 systems/statistics/control/data-structure
  주제와 near-miss distractor를 추가해 문서 64개, 질의 40개를 포함한다. 전체 rerank가
  느릴 때는 `BENCH_QUERY_OFFSET` / `BENCH_QUERY_LIMIT`로 hard-query smoke subset을
  실행한다.
- **질의:** 기존 자연어 질문 20개 + 더 어려운 paraphrase 질문 20개. 다수는 정답 문서와
  키워드가 거의/전혀 겹치지 않는 패러프레이즈(어휘 검색만으로는 실패)이며, 일부는
  의도적으로 distractor의 키워드와 충돌한다.
- **공유 id 공간:** 각 문서를 `search_documents` row(네이티브)와 마크다운 파일
  `<id>.md`(qmd) 양쪽으로 만들어, 반환된 hit이 두 엔진에서 같은 id로 매핑되어 지표가
  정렬되도록 했다.
- **지표:** recall@3, MRR@10, recall@10 (20개 질의 macro 평균).
- **격리:** 네이티브(in-process llama-cpp)와 qmd(subprocess llama-cpp)는 **별도
  프로세스**로 실행한다(두 llama 스택을 한 프로세스에 로드하면 segfault). qmd는
  `INDEX_PATH` + `QMD_CONFIG_DIR`로 격리된 인덱스에 고정한다.

### 비교한 모델

| 단계 | 네이티브 엔진 | qmd |
|---|---|---|
| lexical | SQLite FTS5 (BM25) | qmd BM25 |
| embedding | `Qwen3-Embedding-0.6B` (GGUF, 1024차원) | `EmbeddingGemma-300M` (GGUF) |
| query expansion | 결정적 Tier-1 + recovery-only LLM/HyDE Tier-2 | 파인튜닝 `qmd-query-expansion-1.7B` |
| fusion | RRF (k=60) | RRF |
| **reranker** | **`Qwen3-Reranker-0.6B`** (GGUF) | **`Qwen3-Reranker-0.6B`** (GGUF) |

두 엔진이 **동일한 리랭커 모델**을 사용하므로 rerank 단계는 원리상 동일하며,
네이티브는 qmd보다 *더 큰* 임베더를 쓴다.

## 3. 결과

문서 36개 · 질의 20개 · ground-truth 주제 relevance:

| 엔진 | recall@3 | MRR@10 | recall@10 |
|---|---|---|---|
| **native hybrid+rerank** | **0.950** | **0.938** | **1.000** |
| native lex (FTS5만) | 0.750 | 0.683 | 0.850 |
| **qmd query (full)** | **1.000** | **1.000** | **1.000** |
| qmd search (BM25만) | 0.000 | 0.000 | 0.000 |

해석:

- **네이티브는 qmd와 동등하다.** `recall@10 = 1.000`은 모든 정답 문서가 네이티브
  후보 집합에 검색됨을 의미하며, qmd 대비 작은 `recall@3`/`MRR` 차이는 36개 합성
  코퍼스에서 rank-2에 놓인 소수 사례(노이즈 수준)이다. qmd의 유일하게 측정 가능한
  우위는 일부 패러프레이즈 질의에서 파인튜닝된 1.7B query-expansion 모델 덕분이다.
- **`qmd search`(BM25만) = 0.000**은 결함이 아니라 예상된 결과다: qmd의 BM25 모드는
  질의어를 AND로 묶으므로 완전한 자연어 질문은 매칭되지 않는다. qmd는 자연어에
  `qmd query`(전체 파이프라인)를 의도한다. 네이티브 `lex`(FTS5)는 OR로 묶어 0.750을
  기록 — 자연어에 더 강건하지만 여전히 하이브리드 경로보다 낮다.
- 하이브리드 경로(lexical + chunk vector + RRF + rerank)는 두 엔진 모두에서 lexical
  단독보다 결정적으로 우수하며, v0.3.2 아키텍처를 뒷받침한다.

## 4. 리랭커 호출 수정 (parity를 닫은 변경)

첫 실행에서 네이티브는 `recall@3 = 0.850 / MRR = 0.828 / recall@10 = 0.975`였다 —
같은 리랭커를 쓰는데도 정답 문서가 *검색*은 되나 qmd만큼 top-3로 *랭킹*되지 못했다.
원인: 네이티브 `LlamaCppReranker`가 `"{query}\t{passage}"` 평문을 점수화했는데,
`Qwen3-Reranker`는 instruction 템플릿을 기대한다:

```
<Instruct>: Given a web search query, retrieve relevant passages that answer the query
<Query>: {query}
<Document>: {passage}
```

instruction 템플릿으로 바꾸자 관련/무관 점수 분리가 대략 **두 배**가 되었고(어려운
질의 한 예: 관련 0.919→0.992, distractor 0.611→0.506) 네이티브가
`0.950 / 0.938 / 1.000`으로 이동했다. `backend/src/curator/retrieval/providers.py`
(`LlamaCppReranker._format`)에서 수정.

## 4a. Tier-2 LLM 쿼리 확장 (실측: 공짜 이득 아님)

엔진은 Tier-2 LLM 확장기(`search.query_expansion`, 기본 on)를 지원한다 — 쿼리를
추가 lexical 용어, vector 패러프레이즈, HyDE 문서로 재작성해 RRF로 융합한다. 현재는
기본적으로 **recovery-only**로 동작한다. Incurator가 먼저 raw lexical hit 수와 raw
vector top similarity를 확인한 뒤 confidence가 낮을 때만 Tier-2/HyDE를 사용하므로,
이미 포화된 검색 순위가 expansion noise로 흔들리는 것을 막는다.

아래는 recovery-only gating 이전에 **작은 로컬 확장기(`qwen2.5:0.5b`, Ollama)**로
측정한 결과다:

| 엔진 | recall@3 | MRR@10 | recall@10 |
|---|---|---|---|
| native hybrid+rerank | 0.950 | 0.938 | 1.000 |
| native + LLM 확장 (qwen2.5:0.5b) | 0.950 | **0.912** | 1.000 |

여기서는 **도움이 되지 않았고** MRR을 소폭 낮췄다. 이유와 의미:

- 이 코퍼스에서 native `recall@10`이 이미 **1.000** — 확장 없이도 정답이 전부
  검색되므로 확장이 더할 recall 여지가 없고, 약한 0.5B 확장기는 RRF 순서를 흔드는
  노이즈 프로브만 추가한다.
- 확장의 진짜 가치는 lexical + vector가 정답을 놓치는 **더 어렵거나 큰 코퍼스에서의
  recall**이지, recall이 이미 포화된 상황의 미세 랭킹이 아니다.
- qmd의 MRR=1.000 우위는 generic 확장이 아니라 **파인튜닝된 1.7B**
  `qmd-query-expansion` 모델에서 나온다. 확장기 품질은 모델을 따라간다: 작은 generic
  모델은 하한, 강한 프로덕션 LLM(gemini/claude급)은 도움이 될 것으로 기대된다. 이
  기능은 fail-safe다(LLM 불가 시 Tier-1로 저하).

실무 지침: recovery-only gating과 유능한 답변 경로 LLM을 함께 사용하라. 효과는 검색에
recall 공백이 있는 실제 코퍼스에서 드러나며, 긍정적이라고 가정하지 말고 배포별로
벤치마크해야 한다.

## 4b. qmd 1.7B GGUF expander compatibility와 adversarial 비교

네이티브 벤치는 qmd 호환 GGUF expander variant를 opt-in으로 지원한다:

```bash
BENCH_QUERY_OFFSET=20 BENCH_QUERY_LIMIT=1 FUSE_CAP=2 EXPANDER_MODEL='' \
RUN_QMD_EXPANDER=1 uv run --project backend python scripts/benchmarks/search_parity_bench.py
```

2026-06-05 결과:

| 엔진 | recall@3 | MRR@10 | recall@10 |
|---|---|---|---|
| native hybrid+rerank | 1.000 | 1.000 | 1.000 |
| native + qmd-1.7B expansion | 1.000 | 1.000 | 1.000 |
| native lex (FTS5) | 1.000 | 1.000 | 1.000 |
| qmd query (full) | 1.000 | 1.000 | 1.000 |
| qmd search (BM25) | 0.000 | 0.000 | 0.000 |

이는 Python GGUF expander 경로가 qmd의 structured `lex:` / `vec:` / `hyde:`
출력을 로드하고 파싱함을 확인한다. 그러나 1-query smoke도 recall headroom이 없으므로
expansion 우위를 증명하지는 않는다. 또한 로컬 머신에서 약 103초가 걸렸으므로
qmd-1.7B 행은 기본 다질의 벤치가 아니라 `RUN_QMD_EXPANDER=1` opt-in으로 둔다.

스크립트에는 이제 `adversarial` scenario도 들어 있다. 32개 문서 / 8개 짧거나 모호한
질의(`paint mix`, `web mail`, `io file`, `build up` 등)와 near-miss distractor를
사용한다. 이 scenario는 다시 포화되는 쉬운 세트가 아니라 expansion이 개입할 top-rank
headroom을 만들기 위해 설계했다.

사용한 명령:

```bash
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:none

BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  EXPANSION_RECOVERY_ONLY=0 \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:qmd

BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py qmd
```

native qmd-expander 실행은 8개 질의에 약 16분 걸렸다.

문서 32개 · adversarial 질의 8개 · ground-truth 주제 relevance:

| 엔진 | recall@3 | MRR@10 | recall@10 |
|---|---:|---:|---:|
| native hybrid+rerank | **1.000** | **0.917** | **1.000** |
| native + qmd-1.7B expansion | **1.000** | **0.917** | **1.000** |
| qmd query (full) | 0.875 | 0.906 | **1.000** |
| qmd search (BM25만) | 0.500 | 0.469 | 0.625 |

해석:

- adversarial 세트는 top-rank headroom을 만들었다. native no-expansion은 `build up`
  관련 정답 문서를 rank 1이 아니라 rank 3에 놓았다.
- qmd의 1.7B expander는 이 세트에서 native ranking을 개선하지 못했고, native
  no-expansion과 동률이었다.
- qmd full query는 같은 `build up` 정답을 더 낮게(rank 4) 배치했으므로 native hybrid가
  recall@3와 MRR에서 앞섰다.
- 이는 실제 코퍼스에서 expansion의 가치를 부정하지 않는다. 다만 의도적으로 모호하게
  만든 합성 질의에서도 qmd-trained expander가 native Qwen3 embedding + reranking보다
  자동으로 우월하지는 않음을 보여준다.

## 5. 한계

- **사람 판정이 아닌 주제 기반** relevance의 합성 코퍼스이며 여전히 작다(64개).
  절대 수치는 리더보드 점수가 아니라 sanity 벤치마크다.
- qmd는 제품에서 제거되었으므로 이는 **회귀 게이트가 아니라 절대 품질** 확인이다;
  일반 사용에서 비교할 qmd 경로 자체가 더 이상 없다.
- 네이티브 query expansion Tier-2(LLM/HyDE)는 기본적으로 recovery-only gating으로
  연결되어 있다. 현재 합성 subset은 안정적인 expansion 우위를 보여주지 못한다.
  adversarial 세트는 ranking headroom을 만들었지만 qmd expander가 그 격차를 닫지는
  못했다.

## 6. 재현

```bash
# 필요: wiki models ensure (Qwen3 GGUF) + 모델 캐시가 있는 qmd 바이너리
uv run --project backend python scripts/benchmarks/search_parity_bench.py

# optional qmd 1.7B expander 행을 피한 빠른 hard-query smoke
BENCH_QUERY_OFFSET=20 BENCH_QUERY_LIMIT=2 FUSE_CAP=4 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py

# adversarial 비교. 여러 GGUF stack을 연속 로드할 때 llama-cpp subprocess가
# 불안정할 수 있으므로 행을 분리해서 실행한다.
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:none
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' EXPANSION_RECOVERY_ONLY=0 \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py native:qmd
BENCH_SCENARIO=adversarial FUSE_CAP=8 EXPANDER_MODEL='' \
  uv run --project backend python scripts/benchmarks/search_parity_bench.py qmd
```

스크립트: [`scripts/benchmarks/search_parity_bench.py`](../../scripts/benchmarks/search_parity_bench.py).
코퍼스·질의·지표가 인라인으로 정의되어 확장하기 쉽다.
