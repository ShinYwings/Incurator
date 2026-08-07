/**
 * Resolve which Incurator workspace the user is currently working in.
 *
 * `curate.yml` — the Knowledge Requirement Spec that acts as the retrieval lens
 * — lives ONLY at `01_Workspaces/<project>/curate.yml`. Vault-scoped settings
 * live in `.curator/settings.yml` and are a different thing.
 *
 * Until v0.47.0 the chat surface passed the Obsidian vault ROOT as its
 * workspace path. `resolve_curate_policy()` looks for `curate.yml` at the path
 * it is given, finds nothing at the vault root, and silently falls back to the
 * empty default policy — so every pack came back with `workspace_id: "default"`
 * and an empty `policy_hash`, and the Artist-persona lens described in
 * `about.md` §4/§5.6 never applied to anything a user actually read.
 */

/** The vault folder that holds workspaces. */
export const WORKSPACES_DIR = "01_Workspaces";

/**
 * Given a vault-relative file path, return the vault-relative workspace folder
 * that owns it, or "" when the file is not inside any workspace.
 *
 * Only the immediate `01_Workspaces/<project>` level is a workspace; deeper
 * folders belong to that same project rather than defining new ones.
 */
export function workspaceRelpathForFile(fileRelpath: string): string {
  if (!fileRelpath) return "";
  const parts = fileRelpath.replace(/\\/g, "/").replace(/^\/+/, "").split("/");
  if (parts.length < 2 || parts[0] !== WORKSPACES_DIR) return "";
  const project = parts[1].trim();
  // `01_Workspaces/note.md` is a loose file, not a project.
  if (!project || parts.length < 3) return "";
  return `${WORKSPACES_DIR}/${project}`;
}

/**
 * Absolute workspace path to hand the backend, or "" when no workspace applies.
 *
 * Callers should fall back to the vault base on "". The backend's
 * `workspace_path` argument is overloaded: besides selecting the KRS it is also
 * how `_plugin_paths()` resolves WHICH VAULT to operate on, so sending nothing
 * would make the backend fall back to its own last-root discovery and possibly
 * target a different vault entirely. Sending the vault root yields the
 * documented `default` policy, which is the correct outcome when the user is
 * not working inside a project.
 */
export function resolveWorkspacePath(
  vaultBasePath: string,
  activeFileRelpath: string
): string {
  const rel = workspaceRelpathForFile(activeFileRelpath);
  if (!rel || !vaultBasePath) return "";
  const base = vaultBasePath.replace(/\\/g, "/").replace(/\/+$/, "");
  return `${base}/${rel}`;
}
