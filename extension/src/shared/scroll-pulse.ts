// D30 assist 档共享件：拟人滚动脉冲调度 + 页内浮动开关。
// Boss（zhipin）搜索页使用：用户在场点击开启 → 按抖动间隔滚动脉冲直至页底，
// 既有 scroll 监听自然触发采集——采集语义与人工滚动完全一致。
export const ASSIST_MIN_DELAY_MS = 1_200;
export const ASSIST_MAX_DELAY_MS = 2_400;

const STEP_MIN_PX = 300;
const STEP_MAX_PX = 900;
const BOTTOM_TOLERANCE_PX = 10;

export function nextPulseDelay(rand: () => number = Math.random): number {
  return ASSIST_MIN_DELAY_MS + rand() * (ASSIST_MAX_DELAY_MS - ASSIST_MIN_DELAY_MS);
}

export function nextPulseStep(rand: () => number = Math.random): number {
  return Math.round(STEP_MIN_PX + rand() * (STEP_MAX_PX - STEP_MIN_PX));
}

export interface ScrollMeasure {
  scrollY: number;
  viewportH: number;
  docH: number;
}

export function isAtBottom(m: ScrollMeasure): boolean {
  return m.scrollY + m.viewportH >= m.docH - BOTTOM_TOLERANCE_PX;
}

export interface ScrollPulseDeps {
  scrollBy(step: number): void | Promise<void>;
  measure(): ScrollMeasure;
  delay(ms: number): Promise<void>;
}

export interface ScrollPulse {
  runToBottom(): Promise<void>;
  stop(): void;
  isRunning(): boolean;
}

export function createScrollPulse(deps: ScrollPulseDeps): ScrollPulse {
  let running = false;
  let stopped = false;
  return {
    isRunning: () => running,
    stop() {
      stopped = true;
    },
    async runToBottom() {
      if (running) return;
      running = true;
      stopped = false;
      try {
        while (!stopped) {
          if (isAtBottom(deps.measure())) break;
          await deps.delay(nextPulseDelay());
          if (stopped) break;
          await deps.scrollBy(nextPulseStep());
        }
      } finally {
        running = false;
      }
    },
  };
}

export function createAssistToggle(
  doc: Document,
  onClick: () => void,
): HTMLButtonElement {
  const btn = doc.createElement("button");
  btn.type = "button";
  let active = false;
  const render = () => {
    btn.textContent = active ? "辅助浏览：关闭" : "辅助浏览：开启";
  };
  render();
  btn.style.cssText = [
    "position:fixed", "right:16px", "bottom:16px", "z-index:2147483647",
    "padding:8px 14px", "border-radius:8px", "border:1px solid #0f6b62",
    "background:#fff", "color:#0f6b62", "font-size:13px", "cursor:pointer",
    "box-shadow:0 2px 8px rgba(0,0,0,.15)",
  ].join(";");
  btn.addEventListener("click", () => {
    active = !active;
    render();
    onClick();
  });
  (doc.body ?? doc.documentElement).appendChild(btn);
  return btn;
}
