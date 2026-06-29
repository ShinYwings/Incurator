import { defineConfig } from "vitest/config";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const pluginRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: pluginRoot,
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
});
