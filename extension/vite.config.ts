import { defineConfig } from "vite";

const entry = (p: string): string => new URL(p, import.meta.url).pathname;

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      input: {
        "content/kernel": entry("./src/content/kernel.ts"),
        "content/bilibili": entry("./src/content/bilibili.ts"),
        "content/zhihu": entry("./src/content/zhihu.ts"),
        "content/boss": entry("./src/content/boss.ts"),
        "background/service-worker": entry("./src/background/service-worker.ts"),
      },
      output: {
        format: "es",
        entryFileNames: "[name].js",
      },
    },
  },
});
