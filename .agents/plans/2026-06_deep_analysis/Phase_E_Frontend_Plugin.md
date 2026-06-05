# Phase E: Frontend & Obsidian Plugin — Senior Committee Deep Analysis

**Target Files**: `plugin/main.ts`, `plugin/src/**/*.ts`

**Panel**: Charlie (Security), Alice (Architect), Grace (UX), Evan (Plugin), Hannah (QA)

---

## Debate Transcript

### 1. Fake HITL: Benchmarking Against Argilla and LangSmith

**Grace (UI/UX Designer)**:
"I researched the two industry-leading HITL platforms:

**Argilla** (open-source, Hugging Face ecosystem):
- Dedicated annotation UI with multi-profile user support
- Dataset-first approach: curate-heavy tasks for fine-tuning/RLHF
- Flexible labeling interface for domain expert collaboration

**LangSmith** (LangChain ecosystem):
- 'Annotation Queues' for routing production failures to human reviewers
- 'Trace View' showing the full execution path of how an insight was derived
- 'Align Evaluator' for human experts to calibrate LLM-as-a-judge prompts

Our plugin currently shows the user a raw text block and asks 'approve or reject'. There is:
- No trace view showing which L1 source spans the insight was derived from
- No diff view comparing the proposed insight against the original source text
- No refinement editor for the user to tweak the insight before approving

This is 'checkbox HITL' — it satisfies the letter of the law but not the spirit."

**Evan (Plugin Specialist)**:
"To build an Argilla-level review interface inside Obsidian, we need to move beyond the basic Markdown renderer. I researched the **Obsidian plugin community's best practices for 2024/2025**:

- **Svelte is recommended** for performance-heavy interactive UIs inside Obsidian (no Virtual DOM overhead, simpler state management via `svelte/store`)
- Mount the component to `this.contentEl` inside an `ItemView` subclass
- Always explicitly `$destroy()` the component in `onClose()` to prevent memory leaks
- Use scoped CSS to avoid breaking Obsidian's theme

The implementation pattern:
```typescript
export class InsightReviewView extends ItemView {
    component: any;
    async onOpen() {
        this.component = new InsightReviewPanel({
            target: this.contentEl,
            props: { candidates: await this.fetchCandidates() }
        });
    }
    async onClose() {
        this.component?.$destroy();
    }
}
```"

### 2. Legacy Code Pollution

**Alice (Chief Architect)**:
"`main.ts` and `zoteroWizardModal.ts` still contain `imageFolder` and `data.json` fallback logic from pre-v0.3.0. This legacy code creates phantom execution paths that are impossible to test and actively interfere with the new `assetFolder` and structured API approach."

**Hannah (QA Engineer)**:
"These dead code paths prevent us from achieving acceptable test coverage. We cannot write meaningful tests for logic that is no longer exercised by any valid code path. Deleting this legacy code is a prerequisite for any serious QA effort."

### 📝 Consensus & Action Items

1. **[UX/Plugin]** Build an `InsightReviewView` using **Svelte** mounted in an Obsidian `ItemView`, featuring:
   - Source span trace view (showing which L1 text the insight was derived from)
   - Side-by-side diff comparing proposed insight vs. original source
   - Inline refinement editor for human corrections before approval
2. **[Plugin]** Delete all `imageFolder`, `data.json`, and pre-v0.3.0 fallback code.
3. **[QA]** Achieve >80% test coverage on the plugin codebase after legacy deletion.
