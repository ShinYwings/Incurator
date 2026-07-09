# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

- 2026-07-09 PR #85 review follow-up for v0.34.0 CM-1:
  1. The _resolve_root_or_die helper raises SystemExit when a vault root cannot be resolved. Catching typer.Exit will not intercept this exception, causing the command to exit with an error instead of gracefully setting paths = None as intended when run outside of a vault.
  2. The LLM client initialized by _start_client is never closed, which can lead to resource leaks. Wrap the command execution in a try...finally block to guarantee client.close() is called.
  3. The _ws_client is initialized but never closed, leading to resource leaks. Add a finally block to ensure _ws_client.close() is called.
  4. The LLM client created by _llm.build_client(config) and the extracted client from _resolve_extract_client are never closed, leading to connection leaks. Wrap the execution in a try...finally block to ensure both clients are closed.
  5. Executing a separate database connection and update query for each row in a loop when force is enabled is highly inefficient. Perform a single bulk update query instead.
  6. Opening a database connection and executing an update query per row in a loop is inefficient. Use a single bulk update query instead.
  7. Opening a database connection and executing an update query per row in a loop is inefficient. Use a single bulk update query instead.
  8. test_plugin_models_ollama_lists_with_install_and_ram_flags CI test failed.
  Plan: `.agents/plans/11_pr85_review_followup.md`
