import { afterEach, describe, expect, it, vi } from "vitest";
import {
  TASK_ALARM_NAME,
  TASK_PERIOD_MINUTES,
  initTaskRunner,
  isRiskTitle,
  runOnce,
  type RunnerDeps,
} from "../background/task_runner";
import type { TaskClaim } from "../shared/task_client";

const TASK: TaskClaim = {
  id: 7,
  platform: "shixiseng",
  url: "https://www.shixiseng.com/interns?k=python",
  status: "running",
  dwell_ms: 4000,
};

function makeDeps(overrides: Partial<RunnerDeps> = {}) {
  return {
    claim: vi.fn(async (): Promise<TaskClaim | null> => TASK),
    report: vi.fn(async (): Promise<boolean> => true),
    openTab: vi.fn(async (): Promise<number | null> => 42),
    closeTab: vi.fn(async (): Promise<void> => undefined),
    getTabTitle: vi.fn(async (): Promise<string> => "Python实习_实习僧"),
    ...overrides,
  };
}

describe("isRiskTitle", () => {
  it("flags captcha / verification titles", () => {
    expect(isRiskTitle("安全验证")).toBe(true);
    expect(isRiskTitle("请完成验证码")).toBe(true);
    expect(isRiskTitle("Captcha challenge")).toBe(true);
    expect(isRiskTitle("human verification required")).toBe(true);
  });

  it("passes normal job pages", () => {
    expect(isRiskTitle("Python实习_实习僧")).toBe(false);
    expect(isRiskTitle("招聘_智联招聘")).toBe(false);
    expect(isRiskTitle("")).toBe(false);
  });
});

describe("runOnce", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns idle and touches nothing when no task is claimable", async () => {
    const deps = makeDeps({ claim: vi.fn(async () => null) });
    const outcome = await runOnce(deps, { sleep: vi.fn(async () => undefined) });
    expect(outcome).toBe("idle");
    expect(deps.openTab).not.toHaveBeenCalled();
    expect(deps.report).not.toHaveBeenCalled();
  });

  it("visits, dwells, closes the tab, and reports done", async () => {
    const deps = makeDeps();
    const sleeps: number[] = [];
    const outcome = await runOnce(deps, {
      sleep: vi.fn(async (ms: number) => {
        sleeps.push(ms);
      }),
    });
    expect(outcome).toBe("done");
    expect(deps.openTab).toHaveBeenCalledWith(TASK.url);
    expect(deps.closeTab).toHaveBeenCalledWith(42);
    expect(deps.report).toHaveBeenCalledWith(7, { status: "done" });
    expect(sleeps.length).toBeGreaterThan(0);
  });

  it("clamps dwell to the 30s budget", async () => {
    const deps = makeDeps();
    const sleeps: number[] = [];
    await runOnce(deps, {
      sleep: vi.fn(async (ms: number) => {
        sleeps.push(ms);
      }),
    });
    const total = sleeps.reduce((a, b) => a + b, 0);
    expect(total).toBeLessThanOrEqual(30_000);
  });

  it("aborts with risk_signal when the tab title trips risk control", async () => {
    const deps = makeDeps({
      getTabTitle: vi.fn(async () => "安全验证 - 请完成验证码"),
    });
    const outcome = await runOnce(deps, { sleep: vi.fn(async () => undefined) });
    expect(outcome).toBe("aborted");
    expect(deps.closeTab).toHaveBeenCalledWith(42);
    expect(deps.report).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ status: "aborted", risk_signal: expect.any(String) }),
    );
  });

  it("reports failed when the tab cannot be opened", async () => {
    const deps = makeDeps({ openTab: vi.fn(async () => null) });
    const outcome = await runOnce(deps, { sleep: vi.fn(async () => undefined) });
    expect(outcome).toBe("failed");
    expect(deps.report).toHaveBeenCalledWith(7, { status: "failed", error: "tab_open_failed" });
    expect(deps.closeTab).not.toHaveBeenCalled();
  });
});

describe("initTaskRunner", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("registers the task alarm and reacts only to its own alarm name", () => {
    const alarmListeners: Array<(alarm: unknown) => void> = [];
    const createAlarm = vi.fn();
    vi.stubGlobal(
      "chrome",
      {
        alarms: {
          create: createAlarm,
          onAlarm: { addListener: vi.fn((l: (a: unknown) => void) => alarmListeners.push(l)) },
        },
      } as unknown as typeof chrome,
    );
    initTaskRunner();
    expect(createAlarm).toHaveBeenCalledWith(TASK_ALARM_NAME, {
      periodInMinutes: TASK_PERIOD_MINUTES,
    });
    expect(alarmListeners).toHaveLength(1);
  });

  it("is a no-op without the chrome API (tests/node)", () => {
    expect(() => initTaskRunner()).not.toThrow();
  });
});
