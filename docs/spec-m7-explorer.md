# M7 规格 — 方向探索器（三口径 × B→A 混合交互）

> 状态：待用户复核（用户已口头确认方向与形态：三口径都做、先快照后深谈）。
> 上游：D24（signal vs index——既有信号投向哪个市场）、D13（助产士原则——摆证据不灌输）、D17（八格结构位置——场域推理主输入）、D10（锻造人才非迎合市场）。
> 用户原话锚点："我如何根据已有的经历或成果探索出潜在方向"。这是**人驱动**的探索，区别于现有全部**岗位驱动**链路。

## 0. 问题与定位

现有系统回答"这个岗该不该投/差什么/怎么补"（战术）；无人回答"**我该站在哪**"（战略）。数据已齐（画像三轨 + 作品信号 + 决策历史），缺一个"从既有资产出发向可能性空间搜索"的推理器。

三个口径（用户逐一口径确认，含原话展开）：

| 口径 | 问题 | 推理输入 |
|---|---|---|
| 一·赛道 | 我这堆东西能干什么（边缘 AI？机器人？AI infra？） | 信号组合 × 市场稀缺度 |
| 二·活法 | 同赛道选哪种组织形态（初创核心/大厂部门/读研/量化） | 信号增速 × 八格约束（现金缓冲/价值观/硬边界） |
| 三·场域 | 换哪张桌子打（沪/新一线/新日/欧美远程） | 信号重定价 × 八格全格改写（支持网络/再生产成本/城市约束） |

**边界诚实（设计红线）**：Boss 数据只覆盖国内——口径三的海外推理必须标注"不可验证推理"（LLM 知识 + 信号特征，给置信度），禁止假装有数据。D13：宁可不装懂。

## 1. 交互（B→A 混合，用户确认）

- **B·快照**（先行）：一键触发 → 直接出 3-5 张方向卡（全部基于已有画像，零提问）→ 低成本试错看全景
- **A·深谈**（后接）：对某张卡感兴趣 → 进入对话页深谈流修正（苏格拉底式：系统摆资产盘点 → 逐层问偏好 → 收敛修正该卡）

## 2. 方向卡（DirectionCard）

```python
class DirectionCard(BaseModel):
    card_id: str                    # "dir-{sha1[:12]}"（标题哈希，同 claim 模式）
    scope: Literal["track", "lifestyle", "field"]   # 口径一二三
    title: str                      # "边缘 AI 部署"
    why_you: list[EvidenceRef]      # 为什么是你——证据链（kind=work/profile/behavior/dialogue）
    market_evidence: str            # 市场验证（数据可达时给岗位量/薪资带；不可达时"推理·置信度X"）
    data_backed: bool               # 国内可验证 vs 海外推理
    distance: str                   # 差多远（人话；详细 gap 接 M6 引擎按需展开）
    first_step: str                 # 第一步做什么
    constraint_check: list[str]     # 八格/硬边界碰撞提示（如"竞业硬边界 × 量化形态冲突"）
    confidence: float               # 0-1
    created_from: str               # 快照 id（深谈修正溯源）
```

存储 `data/directions.json`（同 feedback_log 风格；env `TALENTFORGE_DIRECTIONS_PATH`）。

## 3. 探索引擎（explore/engine.py）

### 3.1 资产盘点（纯数据层，无 LLM）

`build_asset_brief(profile, artifacts) -> dict`：技能簇（作品语言分布聚类）+ 强信号清单（strong 作品 + active 主张）+ 行为兴趣（trial 主张）+ 八格摘要 + 硬边界。**深谈模式先展示给用户纠错**（D23 防线 c 同构）。

### 3.2 快照生成（LLM 一次深推）

- system 常量 `EXPLORE_SNAPSHOT_SYSTEM_PROMPT`（模块级，prompt-cache 合规）：三口径各出 1-2 卡、每卡字段精确对齐 DirectionCard、证据必须引用资产清单条目、不可验证市场明确降置信度
- user = 资产盘点 JSON + 岗位库统计摘要（title 关键词频率，给 LLM 国内市场感知）
- 输出解析容错（extract_json + 形状校验，失败 → 空结果 + 错误信息，不 500）

### 3.3 深谈模式

复用对话页 chat 流：意图路由加 "explore-deep" 关键词组（"深挖/细聊/展开这个方向"）→ 注入方向卡上下文 + 资产盘点到 system 侧 user message → 苏格拉底式收敛。修正后的卡写回 directions.json（created_from 溯源）。

## 4. API

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/explore/snapshot` | POST | 生成快照（3-5 张方向卡，含三口径）→ 存库返回 |
| `/api/explore/directions` | GET | 已有方向卡列表 |
| `/api/explore/asset-brief` | GET | 资产盘点（深谈前置展示/纠错） |

## 5. Web

- **入口**：对话页欢迎语加"帮我探索方向"引导 + 工作台空态加"探索方向"链接
- **快照页**（#/explore）：方向卡展——scope 徽章（赛道=terracotta/活法=琥珀/场域=stone）、证据链折叠、data_backed 标记（数据 ✓ / 推理 ≈）、"深挖这个方向"按钮（跳对话页深谈）
- **深谈**：对话流内嵌方向卡上下文（复用 ClaimCard 的卡片内嵌模式）
- fixtures 模式：LOCAL_DIRECTION_FIXTURES（3 张示例卡）

## 6. 范围外

- 海外岗位数据源接入（推理标注即可）；方向卡自动权重收敛（浏览反馈调权——记 backlog）；深谈多轮状态机（v1 用现有 chat 轮次 + 卡上下文注入够用）

## 7. 验收

1. 单元：资产盘点（纯数据）/ 快照解析容错 / DirectionCard 形状
2. API：三端点契约 + FakeLLM
3. Web：方向卡渲染/三口径徽章/深挖按钮（node:test）
4. 真机：**用户真实画像 + 100 仓库 → 快照出的方向卡含"边缘 AI"类交叉方向**（嵌入式 × 架构实验的稀缺组合应被识别）——这是本里程碑的灵魂验收
