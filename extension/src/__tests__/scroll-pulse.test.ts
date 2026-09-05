// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ASSIST_MAX_DELAY_MS,
  ASSIST_MIN_DELAY_MS,
  createAssistToggle,
  createScrollPulse,
  isAtBottom,
  nextPulseDelay,
  nextPulseStep,
} from "../shared/scroll-pulse";

describe("pulse parameters", () => {
  it("jitters delays within the human-like band", () => {
    for (let i = 0; i < 200; i++) {
      const d = nextPulseDelay();
      expect(d).toBeGreaterThanOrEqual(ASSIST_MIN_DELAY_MS);
      expect(d).toBeLessThanOrEqual(ASSIST_MAX_DELAY_MS);
    }
  });

  it("jitters scroll steps within bounds", () => {
    for (let i = 0; i < 200; i++) {
      const s = nextPulseStep();
      expect(s).toBeGreaterThanOrEqual(300);
      expect(s).toBeLessThanOrEqual(900);
    }
  });
});

describe("isAtBottom", () => {
  it("detects bottom within a small tolerance", () => {
    expect(isAtBottom({ scrollY: 900, viewportH: 100, docH: 1000 })).toBe(true);
    expect(isAtBottom({ scrollY: 890, viewportH: 100, docH: 1000 })).toBe(true); // 10px 容差
    expect(isAtBottom({ scrollY: 500, viewportH: 100, docH: 1000 })).toBe(false);
  });
});

describe("createScrollPulse", () => {
  afterEach(() => vi.restoreAllMocks());

  function harness() {
    const state = { scrollY: 0, viewportH: 100, docH: 1000 };
    const steps: number[] = [];
    const tick = vi.fn();
    const pulse = createScrollPulse({
      scrollBy: async (step) => {
        steps.push(step);
        state.scrollY += step;
      },
      measure: () => ({ ...state }),
      delay: async (ms) => {
        tick(ms);
      },
    });
    return { pulse, steps, state, tick };
  }

  it("stops after reaching the bottom", async () => {
    const { pulse, steps } = harness();
    await pulse.runToBottom();
    expect(steps.length).toBeGreaterThan(0);
    expect(steps.length).toBeLessThan(20); // 1000px / 300-900px 步长，几脉冲即到底
    expect(pulse.isRunning()).toBe(false);
  });

  it("scrollBy receives jittered positive steps only", async () => {
    const { pulse, steps } = harness();
    await pulse.runToBottom();
    for (const s of steps) expect(s).toBeGreaterThan(0);
  });

  it("stop() halts the loop even mid-document", async () => {
    const h = harness();
    const running = h.pulse.runToBottom();
    h.pulse.stop();
    await running;
    const stepsAfterStop = h.steps.length;
    expect(h.pulse.isRunning()).toBe(false);
    expect(h.state.scrollY).toBeLessThan(h.state.docH);
    expect(stepsAfterStop).toBe(0); // stop 先于首个 delay → 未滚一步
  });
});

describe("createAssistToggle", () => {
  it("renders a fixed toggle, fires on click, and flips its label", async () => {
    const onClick = vi.fn();
    const el = createAssistToggle(document, onClick);
    expect(el.tagName).toBe("BUTTON");
    expect(document.body.contains(el)).toBe(true);
    expect(el.textContent).toContain("开启");
    expect(el.textContent).not.toContain("关闭");
    el.click();
    await vi.waitFor(() => expect(onClick).toHaveBeenCalledTimes(1));
    expect(el.textContent).toContain("关闭");
    el.remove();
  });
});
