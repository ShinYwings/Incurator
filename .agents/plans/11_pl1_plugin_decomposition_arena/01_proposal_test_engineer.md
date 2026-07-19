# Test Proposal: Characterize Before Every Slice

Date: 2026-07-09 | Agent Persona: Test Engineer

## 1. Core Logic & Implementation

Validation must happen in small loops:

1. Baseline:
   - `npx vitest run -c ./plugin/vitest.config.ts`
   - `npx tsc --noEmit -p plugin/tsconfig.json`
   - `npm run build --prefix plugin`
2. Add characterization tests:
   - Facade export tests.
   - Tests that locate the new owner modules for source-contract assertions.
   - Smoke tests for `ChatSidebarView`, `LLMClient`, and `ExternalPdfView`
     construction/importability under mocked Obsidian.
3. For every extraction phase:
   - Move one concern.
   - Update only tests whose ownership moved.
   - Run the focused test file and full plugin test suite before continuing.

Do not defer all tests to the end. The blast radius is high and failures become
untriageable if thousands of lines move at once.

## 2. Pros & Cons

Pros:

- Keeps mechanical moves reviewable.
- Gives reviewers an objective way to verify zero behavior change.

Cons:

- More commits and more intermediate test updates.
- Source-contract tests will need careful wording to avoid testing incidental
  file placement forever.
