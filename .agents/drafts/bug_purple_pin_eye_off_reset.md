# Problem Brief: Purple Pin 'Eye Off' State Reset

## User Report
purple pin에 eye off 기능이 채팅 send 보내면 다시 초기화됨. 초기화 안되도록 해줘.

## Core Problem Definition
The user can toggle an "eye off" (visibility/inclusion) state on a "purple pin" (presumably a pinned context item). However, whenever a new chat message is sent, this state is lost and resets to its default (likely "eye on"). 
This indicates a state management bug in the UI React/Svelte components or the plugin's session store. The "eye off" state is either not being persisted to the underlying store, or the chat submission triggers a re-render/re-fetch that overwrites the local component state with stale store data.

## Constraints & Edge Cases
1. **Persistence Scope:** Does the "eye off" state need to persist across Obsidian restarts, or just within the active chat session? Ensure it correctly limits what context is included in the LLM payload.
2. **Re-render Cycle:** The chat `send` action triggers a state update (adding user message, streaming assistant response). The executor must trace why this specific trigger obliterates the pin's state.
3. **Immutability:** Check if the pin state array/object is being mutated directly or replaced incorrectly during the chat update cycle.

## Success Criteria
- The "eye off" toggle state on purple pins remains stable and unchanged when sending a chat message.
- The state correctly determines whether the pinned item is included in the LLM context payload during that specific chat submission.
