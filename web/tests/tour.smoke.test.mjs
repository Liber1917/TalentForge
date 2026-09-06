/* M12 新手引导真浏览器冒烟（D31 演示沙箱端到端）：
 * 真 uvicorn 后端 + 真 Chromium（playwright-core）驱动 spec-m12 §验收2/3——
 * 按钮→横幅+步骤卡→步进→Esc 全清→localStorage 命名空间→零 POST 污染审计。
 *
 * 环境缺失（playwright-core / .venv uvicorn / chromium 未装）自动 skip，
 * 不阻塞 node --test 套件与 CI；本地具备条件时真跑。
 */

import { readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import net from "node:net";
import { createRequire } from "node:module";
import { test } from "node:test";
import assert from "node:assert/strict";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

function loadPlaywright() {
  // 锚点优先级：TF_PLAYWRIGHT_CORE 指向 playwright-core 包目录（本机全局/
  // npx 缓存场景）→ 以其 package.json 为锚解析；否则常规解析仓库依赖。
  const anchors = [];
  if (process.env.TF_PLAYWRIGHT_CORE) {
    anchors.push(join(process.env.TF_PLAYWRIGHT_CORE, "package.json"));
  }
  anchors.push(import.meta.url);
  for (const anchor of anchors) {
    try {
      return createRequire(anchor)("playwright-core");
    } catch {
      /* try next anchor */
    }
  }
  return null;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

function spawnBackend(port, cwd) {
  const uvicorn = join(REPO_ROOT, ".venv", "bin", "uvicorn");
  const child = spawn(
    uvicorn,
    ["talentforge.api.app:create_app", "--factory", "--port", String(port)],
    {
      cwd,
      env: {
        ...process.env,
        TALENTFORGE_PROFILE_PATH: join(REPO_ROOT, "docs", "demo", "profile.json"),
        TALENTFORGE_COMPETENCY_CACHE: join(cwd, "cm.json"),
      },
      stdio: ["ignore", "ignore", "pipe"],
    },
  );
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += String(chunk);
  });
  return { child, stderr: () => stderr };
}

async function waitHealth(port, deadlineMs = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < deadlineMs) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/health`, {
        signal: AbortSignal.timeout(2000),
      });
      if (res.ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

test("tour smoke (real browser, demo sandbox)", { timeout: 120000 }, async (t) => {
  const pw = loadPlaywright();
  if (!pw) {
    t.skip("playwright-core 不可用（npm i -D playwright-core 后本测试真跑）");
    return;
  }
  const cwd = mkdtempSync(join(tmpdir(), "tf-tour-smoke-"));
  const port = await freePort();
  const backend = spawnBackend(port, cwd);
  let ctx = null;
  try {
    if (!(await waitHealth(port))) {
      t.skip(`后端未就绪（uvicorn 缺失或启动失败）：${backend.stderr().slice(-200)}`);
      return;
    }
    try {
      ctx = await pw.chromium.launchPersistentContext(join(cwd, "profile"), {
        headless: true,
        channel: "chromium",
        args: ["--no-sandbox"],
      });
    } catch (err) {
      t.skip(`chromium 不可用（npx playwright install chromium）：${String(err).slice(0, 120)}`);
      return;
    }

    const page = await ctx.newPage();
    const posts = [];
    page.on("request", (req) => {
      if (req.method() !== "GET") posts.push(`${req.method()} ${req.url()}`);
    });

    await page.goto(`http://127.0.0.1:${port}/`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForTimeout(1200);

    const btn = await page.$("#tf-tour-btn");
    assert.ok(btn, "顶栏应有常驻『新手引导』按钮");
    await btn.click();
    await page.waitForTimeout(800);

    const banner = await page.$(".tf-tour-banner");
    assert.ok(banner, "引导横幅应出现");
    assert.match(await banner.textContent(), /演示数据/);

    const card = await page.$(".tf-tour-card");
    assert.ok(card, "步骤卡应出现");
    assert.match(await page.$eval(".tf-tour-card__title", (e) => e.textContent), /欢迎/);

    await (await card.$('[data-act="next"]')).click();
    await page.waitForTimeout(500);
    assert.match(
      await page.$eval(".tf-tour-card__title", (e) => e.textContent),
      /决策卡/,
      "next 应步进到第二步",
    );

    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    const after = await page.evaluate(() => ({
      bannerGone: !document.querySelector(".tf-tour-banner"),
      cardGone: !document.querySelector(".tf-tour-card"),
      overlayGone: !document.querySelector(".tf-tour-overlay"),
      spotlightGone: !document.querySelector(".tf-tour-spotlight"),
      lsKeys: Object.keys(window.localStorage),
      useFixtures: window.TalentForgeApi.USE_FIXTURES,
    }));
    assert.ok(after.bannerGone && after.cardGone && after.overlayGone && after.spotlightGone,
      "Esc 后横幅/卡/遮罩/spotlight 应全清");
    assert.deepEqual(after.lsKeys, ["tf_tour_done"], "localStorage 只应新增 tf_tour_done");
    assert.equal(after.useFixtures, true, "退出后 USE_FIXTURES 应还原默认");

    assert.deepEqual(posts, [], "引导全程不得出现任何非 GET 请求（D31 污染审计）");
  } finally {
    if (ctx) await ctx.close().catch(() => {});
    backend.child.kill("SIGTERM");
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, 5000);
      backend.child.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
    rmSync(cwd, { recursive: true, force: true });
  }
});
