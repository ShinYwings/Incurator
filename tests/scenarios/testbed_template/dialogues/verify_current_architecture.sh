#!/usr/bin/env bash
set -euo pipefail

vault_root="${VAULT_ROOT:-testbed}"
db_path="$vault_root/.curator/state.sqlite"

test -f "$db_path"
sqlite3 "$db_path" "SELECT version FROM schema_version;" | grep -Eq '^[1-9][0-9]*$'

VAULT_ROOT="$vault_root" wiki update
for table in sources source_spans knowledge_units graph_entities community_reports synthesis_nodes search_documents; do
  sqlite3 "$db_path" "SELECT COUNT(*) FROM $table;" | grep -Eq '^[1-9][0-9]*$'
done

authoritative_counts() {
  sqlite3 "$db_path" "
    SELECT group_concat(name || '=' || count_value, ';') FROM (
      SELECT 'sources' name, COUNT(*) count_value FROM sources
      UNION ALL SELECT 'source_spans', COUNT(*) FROM source_spans
      UNION ALL SELECT 'knowledge_units', COUNT(*) FROM knowledge_units
      UNION ALL SELECT 'graph_entities', COUNT(*) FROM graph_entities
      UNION ALL SELECT 'community_reports', COUNT(*) FROM community_reports
      UNION ALL SELECT 'synthesis_nodes', COUNT(*) FROM synthesis_nodes
    );
  "
}

before_counts="$(authoritative_counts)"
VAULT_ROOT="$vault_root" wiki update
after_counts="$(authoritative_counts)"
test "$before_counts" = "$after_counts"

before_traces="$(sqlite3 "$db_path" "SELECT COUNT(*) FROM query_traces;")"
VAULT_ROOT="$vault_root" python3 - <<'PY'
import os
from pathlib import Path

from curator import config
from curator.retrieval import QueryOrchestrator, QueryRequest

class NoChat:
    model = "none"
    def chat(self, *args, **kwargs):
        raise AssertionError("fetch_context must remain provider-free")

paths = config.WikiPaths(Path(os.environ["VAULT_ROOT"]))
QueryOrchestrator(paths, NoChat()).fetch_context(
    QueryRequest(question="sample", mode="local")
)
PY
after_traces="$(sqlite3 "$db_path" "SELECT COUNT(*) FROM query_traces;")"
test "$after_traces" -eq "$((before_traces + 1))"

sqlite3 "$db_path" "
  SELECT COUNT(*)
  FROM json_each((SELECT source_span_ids FROM query_traces ORDER BY created_at DESC LIMIT 1)) j
  LEFT JOIN source_spans s ON s.id = j.value
  WHERE s.id IS NULL;
" | grep -Eq '^0$'

sqlite3 "$db_path" "
  SELECT retrieval_trace_json
  FROM query_traces ORDER BY created_at DESC LIMIT 1;
" | grep -q '"mode"'

python3 -m pytest -q \
  backend/tests/test_failure_atlas_experiments.py::test_unchanged_rebuild_is_id_stable_at_l1_and_search \
  backend/tests/test_failure_atlas_experiments.py::test_rename_as_new_source_duplicates_every_span \
  backend/tests/test_failure_atlas_repro.py::test_f7_baseline_no_dependency_invalidation_and_stale_spans_linger
