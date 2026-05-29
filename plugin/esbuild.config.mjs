import { config } from "dotenv";
config();
import esbuild from "esbuild";
import { copyFileSync, existsSync, mkdirSync } from "fs";
import path from "path";

const isProduction = process.argv.includes("--production");
const isWatch = process.argv.includes("--watch");
const pluginDir = process.env.OBSIDIAN_PLUGIN_DIR;
const outfile = pluginDir ? path.join(pluginDir, "main.js") : "main.js";

if (pluginDir) {
  mkdirSync(pluginDir, { recursive: true });
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
  if (pluginDir) {
    for (const file of ["manifest.json", "styles.css"]) {
      if (existsSync(file)) {
        copyFileSync(file, path.join(pluginDir, file));
      }
    }
  }
}
