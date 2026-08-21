// Zhihu content-script entry (document_idle, isolated world). Wires the zhihu adapter into the kernel (Task 5 fills implementation).
import type { PlatformAdapter } from "../shared/types";

export function bootZhihu(_adapter: PlatformAdapter): void {
  void _adapter;
}

(globalThis as Record<string, unknown>).__talentforge_zhihu = true;
