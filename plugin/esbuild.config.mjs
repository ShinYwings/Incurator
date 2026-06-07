import { config } from "dotenv";
import { copyFileSync, existsSync, mkdirSync } from "fs";
import path from "path";
import esbuild from "esbuild";

if (existsSync(".env.local")) {
  config({ path: ".env.local" });
}
config();

const isProduction = process.argv.includes("--production");
const isWatch = process.argv.includes("--watch");
const pluginDir = process.env.OBSIDIAN_PLUGIN_DIR;
let actualPluginDir = null;
let outfile = "main.js";

if (pluginDir) {
  try {
    mkdirSync(pluginDir, { recursive: true });
    actualPluginDir = pluginDir;
    outfile = path.join(pluginDir, "main.js");
  } catch (err) {
    console.warn(`\x1b[33m⚠️ Warning: Could not access/create OBSIDIAN_PLUGIN_DIR "${pluginDir}": ${err.message}\x1b[0m`);
    console.warn("Falling back to building plugin in the local directory.");
  }
}

const context = await esbuild.context({
  entryPoints: ["main.ts"],
  bundle: true,
  external: [
    "obsidian",
    "electron",
    "@codemirror/autocomplete",
    "@codemirror/collab",
    "@codemirror/commands",
    "@codemirror/language",
    "@codemirror/lint",
    "@codemirror/search",
    "@codemirror/state",
    "@codemirror/view",
    "@lezer/common",
    "@lezer/highlight",
    "@lezer/lr",
  ],
  format: "cjs",
  target: "es2020",
  logLevel: "info",
  sourcemap: isProduction ? false : "inline",
  treeShaking: true,
  outfile,
  platform: "node",
  minify: isProduction,
});

if (isWatch) {
  await context.watch();
  console.log("Watching for changes...");
} else {
  await context.rebuild();
  await context.dispose();
  if (actualPluginDir) {
    for (const file of ["manifest.json", "styles.css"]) {
      if (existsSync(file)) {
        try {
          copyFileSync(file, path.join(actualPluginDir, file));
        } catch (err) {
          console.warn(`\x1b[33m⚠️ Warning: Could not copy ${file} to "${actualPluginDir}": ${err.message}\x1b[0m`);
        }
      }
    }
  }
}
