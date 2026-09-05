// 岗位批量上报（M11/D25 统一通道）：content script 一律经 service worker
// 中转 POST /api/jobs/batch——SW fetch 属扩展上下文，无 Origin 头（过 M10
// Origin 校验）且不受 PNA（content-script 直连 127.0.0.1 自 Chromium ~151
// 起 net::ERR_FAILED，boss.ts 直连同样是雷）。
import type { SxsJobCard } from "./platforms/shixiseng";
import type { ZpJobCard } from "./platforms/zhaopin";

export type ReportableJob = SxsJobCard | ZpJobCard;

export function reportJobs(source: string, jobs: ReportableJob[]): void {
  if (jobs.length === 0) return;
  const chromeApi = (globalThis as { chrome?: { runtime?: { sendMessage?: (m: unknown, cb?: (r: unknown) => void) => void } } }).chrome;
  try {
    chromeApi?.runtime?.sendMessage?.({ action: "JOBS_BATCH", source, jobs }, () => {
      // fire-and-forget；SW 侧落库，失败静默（下次滚动/加载重采，后端按 URL 去重）
      void chrome.runtime?.lastError;
    });
  } catch {
    // SW 不可达（极端场景）——放弃本批，采集触发器会再来
  }
}
