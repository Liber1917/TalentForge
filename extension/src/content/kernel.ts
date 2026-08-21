// Content-script collector kernel: wires a PlatformAdapter to DOM observers and emits BehaviorEvents (Task 4 fills implementation).
import type { PlatformAdapter } from "../shared/types";

export function startCollector(_adapter: PlatformAdapter): void {
  // Task 4: observe click / scroll / search / navigation, build BehaviorEvent, sendMessage({action: "BEHAVIOR_EVENT"}).
}

(globalThis as Record<string, unknown>).__talentforge_kernel = true;
