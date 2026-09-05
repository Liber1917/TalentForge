// M11 auto 通道执行器：claim → 开 inactive tab → 拟人停留（预算内轮询 tab
// title 探风控）→ 关 tab → 回报。采集本身由平台 content script 按既有机制
// 完成（页面加载即上报 /api/jobs/batch），runner 只管生命周期。
import { claimTask, reportTask, type TaskClaim, type TaskReport } from "../shared/task_client";

export const TASK_ALARM_NAME = "talentforge-task";
export const TASK_PERIOD_MINUTES = 5;

const RISK_TITLE_RE =
  /安全验证|验证码|人机验证|访问异常|操作频繁|captcha|security check|verif/i;
const PROBE_SLICE_MS = 2_000;
const MIN_DWELL_MS = 3_000;
const MAX_DWELL_MS = 30_000;

export function isRiskTitle(title: string): boolean {
  return RISK_TITLE_RE.test(title);
}

export function clampDwell(ms: number | undefined): number {
  return Math.min(Math.max(ms ?? MIN_DWELL_MS, MIN_DWELL_MS), MAX_DWELL_MS);
}

export interface RunnerDeps {
  claim(): Promise<TaskClaim | null>;
  report(taskId: number, payload: TaskReport): Promise<boolean>;
  openTab(url: string): Promise<number | null>;
  closeTab(tabId: number): Promise<void>;
  getTabTitle(tabId: number): Promise<string>;
}

export interface RunnerOpts {
  sleep?: (ms: number) => Promise<void>;
}

export type RunOutcome = "idle" | "done" | "failed" | "aborted";

export async function runOnce(
  deps: RunnerDeps,
  opts: RunnerOpts = {},
): Promise<RunOutcome> {
  const sleep =
    opts.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const task = await deps.claim();
  if (!task) return "idle";

  const tabId = await deps.openTab(task.url);
  if (tabId === null) {
    await deps.report(task.id, { status: "failed", error: "tab_open_failed" });
    return "failed";
  }

  const dwell = clampDwell(task.dwell_ms);
  let title = "";
  let waited = 0;
  while (waited < dwell) {
    const slice = Math.min(PROBE_SLICE_MS, dwell - waited);
    await sleep(slice);
    waited += slice;
    title = await deps.getTabTitle(tabId);
    if (isRiskTitle(title)) break;
  }

  await deps.closeTab(tabId);
  if (isRiskTitle(title)) {
    await deps.report(task.id, {
      status: "aborted",
      risk_signal: title.slice(0, 60) || "risk_title",
    });
    return "aborted";
  }
  await deps.report(task.id, { status: "done" });
  return "done";
}

function realDeps(): RunnerDeps {
  const chromeApi = (globalThis as { chrome?: typeof chrome }).chrome;
  return {
    claim: () => claimTask("talentforge-runner"),
    report: (id, payload) => reportTask(id, payload),
    openTab: async (url) => {
      try {
        const tab = await chromeApi!.tabs!.create({ url, active: false });
        return typeof tab?.id === "number" ? tab.id : null;
      } catch {
        return null;
      }
    },
    closeTab: async (tabId) => {
      try {
        await chromeApi!.tabs!.remove(tabId);
      } catch {
        // tab may already be gone; nothing to recover.
      }
    },
    getTabTitle: async (tabId) => {
      try {
        return (await chromeApi!.tabs!.get(tabId))?.title ?? "";
      } catch {
        return "";
      }
    },
  };
}

export function initTaskRunner(): void {
  const chromeApi = (globalThis as { chrome?: typeof chrome }).chrome;
  if (!chromeApi?.alarms?.create) return;
  chromeApi.alarms.create(TASK_ALARM_NAME, { periodInMinutes: TASK_PERIOD_MINUTES });
  chromeApi.alarms?.onAlarm?.addListener?.((alarm) => {
    if (alarm?.name !== TASK_ALARM_NAME) return;
    void runOnce(realDeps()).catch((err: unknown) => {
      console.warn(
        "[TalentForge] task run failed:",
        err instanceof Error ? err.message : String(err),
      );
    });
  });
}
