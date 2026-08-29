import { afterAll, beforeAll } from "vitest";
import { existsSync, readFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";

// Fail the run if a test wrote the developer's real agy configuration.
//
// The backend suite was doing exactly this — `~/.gemini/config/mcp_config.json`
// was found pointing VAULT_ROOT at a deleted pytest temp directory — and the
// plugin suite then did it too: a test that spied on `os.homedir` AFTER the
// module under test had already bound it wrote its fixture server into the real
// registry. Both were only noticed by chance.
//
// This does not sandbox the write (a test needing isolation should mock
// `os.homedir` at the module level, as `agyMcpRegistry.test.ts` does). It makes
// the leak loud instead of silent, which is the part that was missing: a
// registry entry pointing at a temp directory keeps agy registered against a
// vault that no longer exists, and nothing complains.
const REGISTRIES = [
  join(homedir(), ".gemini", "config", "mcp_config.json"),
  join(homedir(), ".gemini", "antigravity", "mcp_config.json"),
  join(homedir(), ".gemini", "settings.json"),
];

const before = new Map<string, string>();

beforeAll(() => {
  for (const path of REGISTRIES) {
    if (existsSync(path)) before.set(path, readFileSync(path, "utf-8"));
  }
});

afterAll(() => {
  const touched = REGISTRIES.filter((path) => {
    const had = before.has(path);
    const exists = existsSync(path);
    if (!had && !exists) return false;
    if (had !== exists) return true;
    return readFileSync(path, "utf-8") !== before.get(path);
  });
  if (touched.length) {
    throw new Error(
      "A test modified the real home directory:\n  " + touched.join("\n  ") +
      "\nMock `os.homedir` at the module level — a `vi.spyOn` after import is " +
      "too late, because the module under test has already bound it."
    );
  }
});
