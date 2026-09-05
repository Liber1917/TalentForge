import { afterEach, describe, expect, it, vi } from "vitest";
import { claimTask, reportTask } from "../shared/task_client";

function okFetch(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
}

describe("task_client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("claims a task from /api/tasks/next", async () => {
    const fetchMock = okFetch({ id: 7, platform: "shixiseng", url: "https://x", dwell_ms: 9000 });
    vi.stubGlobal("fetch", fetchMock);
    const task = await claimTask("runner-1");
    expect(task?.id).toBe(7);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/api/tasks/next?runner=runner-1");
    expect(init?.method).toBeUndefined(); // GET
  });

  it("returns null on 204 (no pending task)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 204, json: async () => null })),
    );
    expect(await claimTask("runner-1")).toBeNull();
  });

  it("returns null on transport/backend failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("backend down");
      }),
    );
    expect(await claimTask("runner-1")).toBeNull();
  });

  it("reports a terminal status with payload", async () => {
    const fetchMock = okFetch({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    const ok = await reportTask(7, { status: "aborted", risk_signal: "captcha" });
    expect(ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/api/tasks/7/report");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init!.body))).toEqual({
      status: "aborted",
      risk_signal: "captcha",
    });
  });

  it("swallows report failures (backend down must not crash the runner)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("backend down");
      }),
    );
    expect(await reportTask(7, { status: "done", inserted: 3 })).toBe(false);
  });
});
