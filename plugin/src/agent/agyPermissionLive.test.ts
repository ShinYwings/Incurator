import { describe, expect, it } from "vitest";
import { execFileSync, spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Does the permission rule we write actually AUTHORIZE anything?
 *
 * Every other test in this repo asserts what we wrote to settings.json. That is
 * how this defect shipped twice:
 *
 *   v0.48.4 wrote `$read_file$()` — a form agy prunes. Tests asserted the
 *           string was written, so they passed while the grant survived zero
 *           runs.
 *   v0.53.1 wrote `read_file()` and added an assertion that it PERSISTED.
 *           It does persist. It also authorizes nothing, so every image read
 *           stayed auto-denied for three more releases behind a green test.
 *
 * PLUGIN_SCHEMA §13.6 now states that the authorizing effect has to be measured
 * against the CLI rather than inferred from the file. This is that measurement,
 * automated: write a rule, ask a real agy to read a real file, see whether it
 * could.
 *
 * SKIPPED unless `agy` is on PATH and `INCURATOR_LIVE_AGY=1` — it spends real
 * provider quota and needs an authenticated CLI, so it must never run by
 * default in CI or on a contributor's machine. Run it when changing anything
 * about the permission rules:
 *
 *   INCURATOR_LIVE_AGY=1 npx vitest run -c ./plugin/vitest.config.ts \
 *     plugin/src/agent/agyPermissionLive.test.ts
 */

function agyAvailable(): boolean {
  if (process.env.INCURATOR_LIVE_AGY !== "1") return false;
  const probe = spawnSync("agy", ["--version"], { encoding: "utf-8" });
  return probe.status === 0;
}

const live = agyAvailable() ? describe : describe.skip;

/**
 * agy has no settings-path override, and pointing HOME at a temp dir breaks its
 * authentication (the run dies in under a second and every rule looks denied,
 * which is a false negative, not a measurement). So the real settings file is
 * edited in place and restored in a `finally` — the same thing a human doing
 * this by hand must do.
 */
const SETTINGS = join(
  process.env.HOME ?? homedir(),
  ".gemini",
  "antigravity-cli",
  "settings.json",
);

/** Run agy with `rule` as its only read permission; return true if it read the file. */
function canReadWith(rule: string): boolean {
  const original = existsSync(SETTINGS) ? readFileSync(SETTINGS, "utf-8") : null;
  const scratch = mkdtempSync(join(tmpdir(), "agy-perm-"));
  const target = join(scratch, "secret-token.txt");
  const token = "PERMISSION_PROOF_9F3A";
  writeFileSync(target, token);

  try {
    mkdirSync(join(SETTINGS, ".."), { recursive: true });
    writeFileSync(
      SETTINGS,
      JSON.stringify({ permissions: { allow: [rule, "command(wiki)"] } }, null, 2),
    );
    const out = execFileSync(
      "agy",
      [
        "--model", "gemini-3.6-flash",
        "--effort", "medium",
        "--print", `Read the file at ${target} and reply with its exact contents and nothing else.`,
        "--print-timeout", "4m",
      ],
      {
        encoding: "utf-8",
        env: {
          ...process.env,
          ANTIGRAVITY_TRUST_WORKSPACE: "true",
          AGY_TRUST_WORKSPACE: "true",
        },
      },
    );
    // The token can only appear if the model actually read the file — it is not
    // in the prompt, so an auto-denied run cannot produce it.
    return out.includes(token);
  } catch {
    return false;
  } finally {
    // Always put the user's settings back, including on a thrown assertion.
    if (original !== null) writeFileSync(SETTINGS, original);
    else rmSync(SETTINGS, { force: true });
  }
}

live("agy read permission — measured against the real CLI", () => {
  it(
    "the rule the plugin writes actually grants a read",
    () => {
      expect(canReadWith("read_file(*)")).toBe(true);
    },
    600_000,
  );

  it(
    "the retired forms grant nothing, which is why they had to be replaced",
    () => {
      // If either of these ever starts working, the wildcard is no longer
      // forced and the grant can be narrowed again — that is a result worth
      // knowing, and this test is where it would surface.
      expect(canReadWith("read_file()")).toBe(false);
      expect(canReadWith("$read_file$()")).toBe(false);
    },
    900_000,
  );

  it(
    "a path-scoped read rule is refused, so scoping reads is not available",
    () => {
      // Counter-intuitive and load-bearing: an EXACT path is denied. Without
      // this pinned, a future reviewer would reasonably try to narrow the grant
      // and reintroduce the bug.
      expect(canReadWith("read_file(/tmp/secret-token.txt)")).toBe(false);
    },
    600_000,
  );
});
