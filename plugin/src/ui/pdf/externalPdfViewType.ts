/**
 * The external-PDF view type string, kept in its own obsidian-free module so
 * guards and tests can import it without pulling in the Obsidian runtime.
 * `ExternalPdfView` re-exports it, so the established import path is unchanged
 * (PLUGIN_SCHEMA §1.3 stable facades).
 */
export const EXTERNAL_PDF_VIEW_TYPE = "ai-agent-external-pdf";
