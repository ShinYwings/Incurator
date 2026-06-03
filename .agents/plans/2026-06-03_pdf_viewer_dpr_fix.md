# PDF Viewer Cross-Monitor DPR Fix

## Background
The user reported that moving the Obsidian PDF viewer popout window to a different monitor with a different resolution/scaling still causes text to appear garbled ("글자가 다 깨져서 나옴"). This occurs despite the previous fix that synced PDF.js font styles across document contexts.

## Root Cause Analysis
When a window is moved to a monitor with a different Device Pixel Ratio (DPR), Chromium fires a `resize` event. However:
1. The logical `clientWidth` of the container often remains identical, meaning our `onResize()` method hits an early return (`currentWidth === this.lastClientWidth`).
2. Because `onResize()` returns early, `renderPage()` is never called to re-render the canvas for the new DPR.
3. When the canvas is stretched/scaled by the OS without being re-rendered, or when Chromium attempts to redraw it with cached font glyphs at a new DPR, the text becomes severely distorted, pixelated, or garbled (a known issue with `@font-face` rendering across different display bounds in Electron).

## Proposed Changes

### 1. Track `devicePixelRatio` in `ExternalPdfView`
Update `onResize` to track the current `devicePixelRatio` of the popout window and force a re-render if it changes, even if the logical width remains the same.

#### [MODIFY] `plugin/src/ui/externalPdfView.ts`
- Add `private lastDpr = 1;` property.
- Update `onResize`:
  ```typescript
  const currentWidth = this.containerEl.clientWidth;
  const currentDpr = (this.containerEl.win || window).devicePixelRatio || 1;
  
  // If neither width nor DPR has changed, return early
  if (currentWidth === this.lastClientWidth && currentDpr === this.lastDpr) return;
  
  this.lastClientWidth = currentWidth;
  this.lastDpr = currentDpr;
  this.setZoom(this.zoom); // Triggers re-render
  ```

### 2. Disable Font-Face for Native Path Rendering
To completely eradicate cross-window, cross-monitor font corruption bugs caused by Chromium's text scaling, we will instruct PDF.js to render fonts as vector paths instead of DOM-injected `@font-face` rules. This natively supports any DPR scaling without garbling.

#### [MODIFY] `plugin/src/ui/externalPdfView.ts`
- In `getDocument` call, pass `disableFontFace: true`:
  ```typescript
  pdf = (await pdfjsLib.getDocument({ data, disableFontFace: true }).promise) as PdfDocument;
  ```

## Verification Plan
### Manual Verification
- Open the PDF viewer in a popout window.
- Move the window between a Retina display (e.g., MacBook screen) and a non-Retina display (e.g., standard 1080p monitor).
- Verify that text instantly re-renders sharply and does not become garbled.

## User Review Required
> [!IMPORTANT]
> The plan is ready for review. By forcing PDF.js to use vector paths for text and explicitly triggering re-renders on DPR changes, the cross-monitor scaling bug will be fully resolved. Please approve this plan to proceed with the implementation.
