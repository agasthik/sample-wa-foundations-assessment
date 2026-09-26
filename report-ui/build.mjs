// Builds the Cloudscape report UI into a single JS file and a single CSS file
// under src/report/assets/. The Python report generator inlines both into each
// HTML report, so the output must stay self-contained and deterministic.
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const here = dirname(fileURLToPath(import.meta.url));
const outdir = join(here, "..", "src", "report", "assets");
const attribution =
  "/*! WAFA report UI. Includes Cloudscape Design System components " +
  "(https://cloudscape.design/, Apache-2.0) and React (MIT). */";
const outputs = ["report-ui.js", "report-ui.css"].map((name) => join(outdir, name));

outputs.forEach((file) => rmSync(file, { force: true }));

await esbuild.build({
  entryPoints: { "report-ui": join(here, "src", "index.jsx") },
  outdir,
  bundle: true,
  minify: true,
  // Keep third-party license notices in the redistributed bundle.
  legalComments: "eof",
  banner: { js: attribution, css: attribution },
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff": "dataurl", ".woff2": "dataurl", ".svg": "dataurl" },
  logLevel: "warning",
});

for (const file of outputs) {
  // The bundle is inlined in <script> and <style> elements. "<\/" is
  // equivalent to "</" inside JS string, template, and regex literals, so
  // escaping it prevents the HTML parser from closing the element early.
  const content = readFileSync(file, "utf8").replace(/<\/(script|style)/gi, "<\\/$1");
  // The report must work offline, so reject remote stylesheet imports or
  // font/image URLs in the bundle.
  if (/@import|url\(\s*["']?(https?:)?\/\//i.test(content)) {
    throw new Error(`${file} references a remote resource`);
  }
  // The Python generator strips trailing whitespace from each report line.
  // Fail here instead of letting that silently change bundle content.
  if (/[ \t]\r?$/m.test(content)) {
    throw new Error(`${file} contains trailing whitespace`);
  }
  writeFileSync(file, content.endsWith("\n") ? content : `${content}\n`);
}
