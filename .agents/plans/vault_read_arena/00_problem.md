# Vault read execution failure
Date: 2026-09-21

The user reports Obsidian agent cannot read project Research Notes because
`sandbox-exec: sandbox_apply: Operation not permitted` happens before tools run.
User requires vault files always directly readable without access questions.
Investigate the actual launch, preserve existing editing and reference capability.
Current plugin wraps every CLI in OS write sandbox. Codex also applies native
read-only/workspace-write. Claude native Read is denied on text-only turns.
Do not silently reduce capabilities or grant Zotero writes. No production data
migration, deletion, global permission bypass, or unrelated lifetime changes.
Determine minimal measured repair; explicitly distinguish confirmed cause from
remaining hypotheses. Use real parallel proposals, cross-critique and verification.
Current master f184c99d is v0.82.8 (#209). Work branch hotfix/v0.82.9-vault-read.
Existing USER_REPORT timeout report is user WIP; preserve every detail.
