// Construit l'extension dans dist/ : un fichier par point d'entrée, plus le manifeste et les pages.
import { cpSync, mkdirSync, rmSync } from "node:fs";
import * as esbuild from "esbuild";

const surveiller = process.argv.includes("--watch");
rmSync("dist", { recursive: true, force: true });
mkdirSync("dist", { recursive: true });
cpSync("static", "dist", { recursive: true });

const options = {
  entryPoints: ["src/background.ts", "src/content.ts", "src/pont.ts", "src/popup.ts", "src/options.ts"],
  bundle: true,
  outdir: "dist",
  format: "iife",
  target: "chrome120",
  sourcemap: true,
  logLevel: "info",
};

if (surveiller) {
  const contexte = await esbuild.context(options);
  await contexte.watch();
} else {
  await esbuild.build(options);
}
