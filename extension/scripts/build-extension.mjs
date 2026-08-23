// Extension build: content scripts MUST be self-contained classic scripts —
// Chrome content_scripts don't support ES module imports (SyntaxError on
// injection). So each content entry gets its own single-input IIFE build
// (shared deps like kernel/backend-endpoint get inlined per file), while the
// service worker stays an ES module (manifest declares "type": "module").
import { build } from "vite";
import { fileURLToPath } from "node:url";

const entry = (p) => fileURLToPath(new URL(`../${p}`, import.meta.url));

// 1. Service worker first (empties dist; ES module format is fine here).
await build({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      input: { "background/service-worker": entry("./src/background/service-worker.ts") },
      output: { format: "es", entryFileNames: "[name].js" },
    },
  },
});

// 2. Content scripts: one IIFE build per entry — no imports, no shared chunks.
for (const name of ["content/bilibili", "content/zhihu", "content/boss"]) {
  await build({
    build: {
      outDir: "dist",
      emptyOutDir: false,
      target: "es2022",
      rollupOptions: {
        input: { [name]: entry(`./src/${name}.ts`) },
        output: { format: "iife", entryFileNames: "[name].js" },
      },
    },
  });
}
