# Problem Brief: PDF Crop Context Injection Failure

## User Report
`ctrl + shift + x`로 pdf 크롭한거 side chat에 context로 안들어가짐 (적어도 대답할 때 인식을 못함)

## Core Problem Definition
When a user crops a section of a PDF using the `ctrl+shift+x` shortcut, the resulting cropped content (likely an image or OCR text) is expected to be injected into the active Side Chat context. However, the LLM fails to recognize it when answering. This indicates a failure in the context pipeline:
1. The crop action is successfully capturing the region, but failing to serialize or append the payload to the active chat session's context store.
2. OR, the payload is appended, but the chat prompt builder strips, drops, or fails to parse this specific type of payload before sending the request to the LLM.

## Constraints & Edge Cases
1. **Payload Serialization:** Determine if the crop is being passed as a base64 image or text. Ensure the format matches what the side chat prompt builder expects for attachments/context blocks.
2. **Context Routing:** Ensure the injection targets the currently active session without requiring a UI refresh.
3. **LLM Vision Capability:** If the crop is passed as an image, ensure the prompt format correctly embeds the image block for models that support vision (or ensure OCR is successfully triggered and embedded if text-only).

## Success Criteria
- Cropping a PDF via `ctrl+shift+x` successfully attaches the cropped content to the active side chat context.
- The LLM explicitly recognizes and can answer questions about the cropped content.
- The fix must be implemented on the current branch without breaking the core RAG extraction logic.
