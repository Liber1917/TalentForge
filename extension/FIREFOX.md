# Firefox 适配说明

TalentForge 扩展同时支持 Chrome（MV3 service worker）与 Firefox（MV3 event page）。
两个目标产物相互独立，互不影响：

| 目标 | 构建命令 | 产物 | 加载方式 |
|------|----------|------|----------|
| Chrome | `npm run build` | `dist/`（不变） | chrome://extensions → Load unpacked |
| Firefox | `npm run build:firefox` | `dist-firefox/` | about:debugging → Load Temporary Add-on |

两个命令都内嵌冒烟校验：manifest 可解析、所有被引用脚本存在且非空、
background 形态与目标匹配，失败即中断构建。

## Firefox 加载步骤（about:debugging）

1. `npm run build:firefox` 生成 `dist-firefox/`。
2. Firefox 打开 `about:debugging#/runtime/this-firefox`。
3. 「临时载入附加组件…（Load Temporary Add-on）」→ 选择
   `extension/dist-firefox/manifest.json`（目录内任意文件均可，选 manifest 最直观）。
4. 确认插件列表出现 TalentForge，检查「检查」(Inspect) 可打开 event page 控制台。

### 权限授予

- Firefox MV3 的 `host_permissions` 走**用户授予**模型：临时加载
  （about:debugging）会直接授予全部 host 权限，无需额外操作。
- 若日后通过签名 .xpi 常规安装，需在 `about:addons` → TalentForge →
  「权限」里手动开启 bilibili / zhihu / zhipin 站点访问，否则 content script
  不会注入。
- 后端地址 `http://127.0.0.1:8420` 依赖 `http://127.0.0.1/*` host 权限上传事件。

## 已知差异与风险

| 项 | 差异 / 风险 | 处理或状态 |
|----|-------------|-----------|
| background 模型 | Firefox 无 MV3 service worker | 变体 manifest 用 `background.scripts`（event page），background 以 IIFE 经典脚本构建 |
| alarms 最小周期 | Firefox 把 `periodInMinutes < 1` 钳到 1 分钟 | 运行时检测（全局 `browser` 命名空间）显式钳到 1 分钟；缓冲上限 50 + 满即触发即时 flush，不依赖 alarm 的 30s 周期，无丢失风险 |
| flush 延迟 | Firefox 下 alarm flush 从 30s 放宽到最长 60s | 行为事件持久化在 `storage.local`，event page 卸载不丢；可接受 |
| `chrome.runtime.sendMessage` 返回 Promise | Firefox / Chrome 99+ 无回调调用返回 Promise，端口关闭时 reject | kernel.ts 已吞并 rejection（fire-and-forget 采集不受影响） |
| 异步 `sendResponse` | Firefox 对 listener 返回 `true` 后异步 `sendResponse` 的送达与 Chrome 存在历史差异 | 发送方从不读取响应（fire-and-forget），事件入队先于响应；两侧均有 try/catch 兜底 |
| boss.ts wapi 抓取 | content script 内 `credentials: "include"` 同源 fetch：Firefox 对 content script fetch 的 CSP/CORS 处理与 Chrome 有差异 | **需真机验证**（本环境无 Firefox 无法实证）。若失败会静默降级走 DOM 渠道，采集不中断，仅少 wapi 字段 |
| content script 隔离模型 | Firefox 用 Xray wrapper 而非 Chrome 隔离 world | 本扩展只读 DOM（kernel/boss 均无页面 world 注入），Xray 下兼容 |
| `browser_specific_settings` | gecko id `talentforge@local`、`strict_min_version` 142.0（桌面 140 / Android 142 起识别 `data_collection_permissions`，取交集）、`data_collection_permissions: none` | 由 `src/shared/firefox.ts` 单一来源生成，有单测覆盖 |
| addons-linter | — | `npx addons-linter dist-firefox` 通过（0 errors / 0 warnings） |

## 变体生成逻辑

manifest 变体由 `src/shared/firefox.ts` 的 `buildFirefoxManifest()` 纯函数派生
（构建脚本与单测共用同一实现）：

- `background.service_worker` → `background.scripts`，并去掉路径的 `dist/` 前缀
  （`dist-firefox/` 是自包含可加载目录）；
- `content_scripts[].js` 同样去 `dist/` 前缀，`matches`/`run_at` 原样保留；
- 追加 `browser_specific_settings.gecko`（id / strict_min_version /
  data_collection_permissions）；
- 其余字段（permissions、host_permissions、版本号等）逐字沿用基准 manifest。
