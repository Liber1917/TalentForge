/* M12 新手引导测试（D31 演示沙箱）：状态机流转 / tf_real 保存还原 /
   tf_tour_* 命名空间隔离 / override 委托契约。模式同 jobs.test.mjs（vm 加载）。 */

import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

globalThis.window = globalThis;
const src = readFileSync(new URL("../js/tour.js", import.meta.url), "utf8");
vm.runInThisContext(src);
const Tour = globalThis.TalentForgeTour;

function makeDeps(initial = {}) {
  const store = new Map(Object.entries(initial));
  const calls = { setFixtureOverride: [], navigations: [], steps: [] };
  return {
    storage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    },
    setFixtureOverride: (v) => calls.setFixtureOverride.push(v),
    navigate: (h) => calls.navigations.push(h),
    onStep: (s) => calls.steps.push(s),
    store,
    calls,
  };
}

test("module exports core factory and six steps", () => {
  assert.equal(typeof Tour.createTourCore, "function");
  assert.equal(Tour.steps.length, 6);
  assert.deepEqual(
    Tour.steps.map((s) => s.id),
    ["welcome", "decision-card", "workbench", "profile", "sources", "go-real"],
  );
});

test("start forces fixture mode, saves tf_real, activates, navigates to step 1", () => {
  const deps = makeDeps({ tf_real: "1" });
  const core = Tour.createTourCore(deps);
  assert.equal(core.start(), true);
  assert.deepEqual(deps.calls.setFixtureOverride[0], true);
  assert.equal(deps.store.get("tf_tour_active"), "1");
  assert.equal(deps.calls.navigations[0], "/chat");
  assert.equal(deps.calls.steps[0].id, "welcome");
  assert.equal(core.state().prevReal, "1");
  assert.equal(core.start(), false, "重复 start 幂等");
});

test("stop restores tf_real='1' (was set) and clears sandbox keys", () => {
  const deps = makeDeps({ tf_real: "1" });
  const core = Tour.createTourCore(deps);
  core.start();
  core.stop();
  assert.equal(deps.store.get("tf_real"), "1");
  assert.equal(deps.store.has("tf_tour_active"), false);
  assert.equal(deps.store.get("tf_tour_done"), "1");
  assert.deepEqual(deps.calls.setFixtureOverride.at(-1), null);
  assert.equal(deps.calls.steps.at(-1), null);
  assert.equal(core.state().active, false);
});

test("stop removes tf_real when it was absent before the tour", () => {
  const deps = makeDeps({});
  const core = Tour.createTourCore(deps);
  core.start();
  core.stop();
  assert.equal(deps.store.has("tf_real"), false);
});

test("sandbox touches only tf_tour_* and tf_real keys", () => {
  const deps = makeDeps({ tf_real: "1" });
  const core = Tour.createTourCore(deps);
  core.start();
  core.next();
  core.next();
  core.stop();
  const keys = [...deps.store.keys()];
  for (const k of keys) {
    assert.ok(k.startsWith("tf_tour_") || k === "tf_real", `命名空间泄漏: ${k}`);
  }
});

test("next walks all steps then completes; prev clamps at 0", () => {
  const deps = makeDeps({});
  const core = Tour.createTourCore(deps);
  core.start();
  core.prev();
  assert.equal(core.state().index, 0, "第一步 prev 不动");
  for (let i = 1; i < 6; i += 1) core.next();
  assert.equal(core.state().index, 5, "五次 next 到达最后一步");
  assert.equal(core.state().active, true);
  core.next();
  assert.equal(core.state().active, false, "最后一步再 next 即完成退出");
  assert.deepEqual(deps.calls.steps.map((s) => s && s.id), [
    "welcome",
    "welcome", // prev 在第一步钳制 → 幂等重渲染当前步
    "decision-card",
    "workbench",
    "profile",
    "sources",
    "go-real",
    null,
  ]);
});

test("go-real step does not navigate (stays on current view)", () => {
  const deps = makeDeps({});
  const core = Tour.createTourCore(deps);
  core.start();
  core.goTo(5);
  assert.equal(core.state().index, 5);
  const lastStep = deps.calls.steps.at(-1);
  assert.equal(lastStep.id, "go-real");
  assert.equal(lastStep.view, null);
  assert.equal(deps.calls.navigations.length, 1, "go-real 步不新增导航");
  assert.equal(deps.calls.navigations[0], "/chat");
});
