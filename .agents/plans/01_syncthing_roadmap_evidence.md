# v0.4.0 System Build Evidence Ledger

## 1. Rollback Requirements
- Current branch: `release/v0.4.0` (Git tracked).

## 2. Current Schema & Reality To Recheck
- `state.sqlite` relies on `deleted_records` for tombstones.

## 3. Known Validation Results
- Baseline `pytest` passes with 458/458 green.
