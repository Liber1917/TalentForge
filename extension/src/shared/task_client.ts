// M11 auto 通道客户端：claim / report 与后端 /api/tasks/* 的契约封装。
// 任何失败都吞掉返回空/false——task alarm 的下一轮会重试（任务在服务端保持
// running 直到回报，异常退出最多造成一次人工清理，不影响其他任务）。
import { backendEndpoint } from "./backend-endpoint";

export interface TaskClaim {
  id: number;
  platform: string;
  url: string;
  status: string;
  dwell_ms?: number;
}

export type TaskReport =
  | { status: "done"; inserted?: number }
  | { status: "failed"; error?: string }
  | { status: "aborted"; risk_signal?: string };

export async function claimTask(
  runner: string,
  base: string = backendEndpoint(),
): Promise<TaskClaim | null> {
  try {
    const res = await fetch(`${base}/tasks/next?runner=${encodeURIComponent(runner)}`);
    if (!res.ok || res.status === 204) return null;
    const data: unknown = await res.json();
    if (typeof data === "object" && data !== null && "id" in data) {
      return data as TaskClaim;
    }
    return null;
  } catch {
    return null;
  }
}

export async function reportTask(
  taskId: number,
  payload: TaskReport,
  base: string = backendEndpoint(),
): Promise<boolean> {
  try {
    const res = await fetch(`${base}/tasks/${taskId}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.ok;
  } catch {
    return false;
  }
}
