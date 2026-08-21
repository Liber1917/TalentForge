# M2b 验收笔记 — 插件内容采集（B站+知乎）最小闭环

> 验收依据：`docs/plan-m2b.md` Task 6；Spec：`docs/spec-m2b-extension.md`。
> 验收日期：2026-08-21。执行人：agentic worker（Task 6）。
> 结论速览：**后端契约联调通过（已复现，真实 curl 输出见 §1）；画像自长链路离线通过（真实 LLM 输出见 §3）；插件↔后端浏览器端到端标记 pending-user——需用户授权浏览器加载扩展后方可执行（§2），不阻塞本里程碑收尾。全测绿：pytest 110 + vitest 33。**

---

## 1. 后端契约验收（已通过，可复现）

**启动 events_server（port 8421，避开默认 8420 可能冲突）：**

```bash
nohup .venv/bin/python -c "from talentforge.api.events import events_server; from talentforge.storage.db import init_db; s = events_server(port=8421, conn=init_db('/tmp/opencode/m2b-e2e.db', check_same_thread=False)); s.serve_forever()" &
```

> **注意：** `conn` 必须带 `check_same_thread=False`——`ThreadingHTTPServer` 每个请求跑在独立 worker 线程，默认（`check_same_thread=True`）会抛 `sqlite3.ProgrammingError`。`events_server()` 不传 conn 时内部已自动加该参数（见 `talentforge/api/events.py` docstring），仅调用方自建 conn 时需要显式传。`tests/test_events_api.py` 中 `test_events_server_http_endpoints` 同样显式传 `check_same_thread=False`。

**curl 模拟插件 POST（首次，应 accepted=1）：**

```bash
curl -s -w "\nHTTP_STATUS=%{http_code}\n" -X POST http://127.0.0.1:8421/api/events \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"event_id":"e2e-1","type":"click","url":"https://www.bilibili.com/video/BV1xx411c7mD","title":"测试视频","source_platform":"bilibili","context":{"pageType":"video"},"metadata":{}}]}'
```

**实测输出：**

```
{"ok": true, "accepted": 1, "duplicates": 0, "rejected": []}
HTTP_STATUS=200
```

**同 event_id 再 POST（幂等，应 accepted=0 duplicates=1）：**

```
{"ok": true, "accepted": 0, "duplicates": 1, "rejected": []}
HTTP_STATUS=200
```

**库核验（events 表应只有 1 行，幂等去重生效）：**

```
events rows: 1
{'event_id': 'e2e-1', 'event_type': 'click', 'url': 'https://www.bilibili.com/video/BV1xx411c7mD', 'title': '测试视频', 'source_platform': 'bilibili', 'context_json': '{"pageType": "video"}', 'metadata_json': '{}', 'received_at': '2026-08-21T15:15:45.105816+00:00'}
```

**验收判定：** ✅ 通过——POST 200、`accepted=1`、重复 POST `duplicates=1`、events 表 1 行。契约（`{"ok":bool,"accepted":n,"duplicates":m,"rejected":[...]}` + event_id 幂等）与插件 `backend-endpoint.ts` 的 flush 契约一致（见 extension 单测 `tests` 覆盖的 URL 构造 / POST 逻辑）。

**环境备注：** 本机 127.0.0.1:8420/8421 无端口冲突；验收用 8421 避免与共享宿主上其他进程探测 8420 的噪声（验收日志含无关 `/api/sources/*` 404 探针，来自宿主其他进程，非本服务器业务请求）。

---

## 2. 插件↔后端端到端（pending-user，需用户授权浏览器）

当前环境无图形浏览器交互，且加载扩展、人工浏览 bilibili.com/zhihu.com 需用户现场授权。按计划标记 **pending-user**，不阻塞。单测/构建已充分覆盖插件侧行为（vitest 33：kernel 事件构造、buffer 持久化与满 50 flush、adapter 解析、endpoint URL 构造）。

**待用户授权后执行：**

1. **起后端**（终端 1）：
   ```bash
   cd /home/TalentForge
   nohup .venv/bin/python -c "from talentforge.api.events import events_server; from talentforge.storage.db import init_db; s = events_server(conn=init_db('data/talentforge.db', check_same_thread=False)); s.serve_forever()" &
   ```
2. **装扩展**：Chrome 打开 `chrome://extensions` → 开启"开发者模式" → "加载已解压的扩展程序" → 选 `extension/` 目录（manifest.json 的 background/content 均指向 `dist/`，故需先 `npm run build`；也可直接选 `extension/dist/`，但当前 manifest 在 `extension/` 根下、`extension/dist/` 无独立 manifest，故选 `extension/` 根）。
3. **浏览采集**：访问 https://www.bilibili.com/ 与 https://www.zhihu.com/ ，点击视频卡片 / 搜索（触发 click/search 事件，30s 内 flush 到 `http://127.0.0.1:8420/api/events`）。
4. **核验入库**：
   ```bash
   sqlite3 data/talentforge.db "SELECT event_id, event_type, url, source_platform, received_at FROM events ORDER BY received_at DESC LIMIT 20;"
   ```

**验收执行清单：**
- [ ] `cd extension && npm install && npm run build` 产出 `extension/dist/`（background/content js）
- [ ] Chrome 加载 `extension/`（开发者模式）
- [ ] 起后端 8420（上述命令）
- [ ] 浏览 B站/知乎触发点击/搜索事件
- [ ] events 表出现 ≥1 条 source_platform=bilibili / zhihu 记录
- [ ] 记录真实行数回填本节

---

## 3. 画像自长链路（离线可复现，真实 LLM）

验证"事件→trial 主张（behavior 证据）"消费链。事件数据来自 `talentforge events-ingest` 入库 → `profile-update` 消费。

**造 5 条 B站/知乎浏览事件 JSONL（可复现样例）：**

```jsonl
{"event_id":"demo-1","type":"click","url":"https://www.bilibili.com/video/BV1GJ411x7h7","title":"Python 异步编程实战：asyncio 深入理解","source_platform":"bilibili","context":{"pageType":"video","scrollPosition":0},"metadata":{"action":"video_click"}}
{"event_id":"demo-2","type":"click","url":"https://www.bilibili.com/video/BV1Yb411J7Y9","title":"分布式系统设计：一致性协议从 Raft 到 Paxos","source_platform":"bilibili","context":{"pageType":"video","scrollPosition":30},"metadata":{"action":"video_click"}}
{"event_id":"demo-3","type":"search","url":"https://www.bilibili.com/search?keyword=system%20design%20interview","title":"B站搜索：system design interview","source_platform":"bilibili","context":{"pageType":"search","scrollPosition":0},"metadata":{"keyword":"system design interview"}}
{"event_id":"demo-4","type":"click","url":"https://www.zhihu.com/question/280898373","title":"系统设计面试应该如何准备？","source_platform":"zhihu","context":{"pageType":"question","scrollPosition":60},"metadata":{"action":"card_click"}}
{"event_id":"demo-5","type":"scroll","url":"https://www.bilibili.com/video/BV1GJ411x7h7","title":"Python 异步编程实战：asyncio 深入理解","source_platform":"bilibili","context":{"pageType":"video","scrollPosition":85},"metadata":{}}
```

**实测输出（`--db` 指向独立验收库，不污染默认 data/talentforge.db）：**

```bash
$ .venv/bin/talentforge events-ingest /tmp/opencode/m2b-browse-events.jsonl --db /tmp/opencode/m2b-selfgrow.db
{"ingested": 5, "duplicates": 0, "invalid": 0}

$ .venv/bin/talentforge profile-update --profile docs/demo/profile.json --limit 5 --db /tmp/opencode/m2b-selfgrow.db
{"added_claims": 6, "updated_claims": 0}
```

**profile 文件实测 claims（docs/demo/profile.json 追加 narrative_claims，state=trial、sources[0]={kind:behavior, ref:<event_id>}）：**

```
narrative_claims: 6
  - 用户对后端开发中的异步编程技术有深入学习的兴趣 (conf=0.9, state=trial, evid=0, ref=demo-5)
  - 用户正在准备系统设计面试，关注相关面试准备内容 (conf=0.95, state=trial, evid=0, ref=demo-5)
  - 用户对分布式系统设计中的一致性协议（如Raft、Paxos）有研究需求 (conf=0.85, state=trial, evid=0, ref=demo-5)
  - 用户偏好通过视频和问答平台获取技术知识 (conf=0.8, state=trial, evid=0, ref=demo-5)
  - 用户可能处于求职或职业进阶阶段，目标岗位涉及系统架构或后端开发 (conf=0.75, state=trial, evid=0, ref=demo-5)
  - 用户对系统设计面试的准备是系统性的，包括搜索和浏览相关资源 (conf=0.7, state=trial, evid=0, ref=demo-5)
```

> 证据回溯：ref=demo-5（批内最近事件，list_events 按 received_at 倒序取首条）；每条主张均可从事件批内容解释（异步/asyncio、Raft/Paxos、系统设计面试、视频+问答平台）——**"画像自长"链路成立**。`docs/demo/profile.json` 已包含上述 6 条 trial claims（验收写入；原始文件备份见 `/tmp/opencode/profile-before.json`）。

**验收判定：** ✅ 通过——`events-ingest` 入库 5 条、`profile-update` 新增 6 条 trial 主张、全部携带 behavior 证据（kind=behavior, ref 指向事件）。信号累积（evidence_count 增长）在单测 `tests/test_pipeline.py` 覆盖（同文本二次 → evidence_count+1）。

---

## 4. 本次验收实测数据

| 计数 | 值 |
|---|---|
| 后端 POST accepted（e2e-1） | 1 |
| 后端 POST duplicates（同 e2e-1 重复） | 1 |
| events 表行数（e2e 库 /tmp/opencode/m2b-e2e.db） | 1 |
| events-ingest 入库条数（m2b-selfgrow.db） | 5 |
| events-ingest duplicates / invalid | 0 / 0 |
| profile-update added_claims | 6 |
| profile narrative_claims（docs/demo/profile.json） | 6 |
| profile claims state / 证据种类 | 全 trial / 全 behavior |
| pytest | 110 passed |
| vitest（extension） | 33 passed |
| 端口冲突（8420/8421） | 无 |

---

## 5. 偏差与备注

1. **events_server 调用方 conn 需显式 `check_same_thread=False`**：计划启动命令原本省略该参数会触发 `sqlite3.ProgrammingError`（ThreadingHTTPServer 多线程 × 单线程连接）。已在 §1 命令中修正；`events_server()` 默认路径不受影响（内部已处理）。这是调用方用法问题而非代码缺陷，未改业务代码。
2. **验收库隔离**：§3 用 `--db /tmp/opencode/m2b-selfgrow.db`、§1 用 `/tmp/opencode/m2b-e2e.db`，避免污染默认 `data/talentforge.db` 与 demo profile 之外的文件；demo profile 按计划被写回 6 条 claims（自长证据）。
3. **浏览器端到端**：pending-user（需用户授权 Chrome 加载扩展 + 人工浏览），见 §2。
