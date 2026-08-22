# easyCV 拆解笔记（lvy010/easyCV，MIT）

> 调研日期：2026-08-22。目的：评估"简历产出"能力是否可借鉴（D10 锻造人才定位下的辅助能力）。
> 仓库：https://github.com/lvy010/easyCV（212 stars / 27 forks，14 commits，约 700 行代码）。

## 是什么

极简 **YAML 驱动的简历工具**：一个 `resume.yaml` 定义全部内容 → FastAPI 渲染 A4 简历页 → 浏览器打印导出 PDF。无数据库、无复杂依赖、纯文件读写。

**代码构成：**

| 文件 | 行数 | 作用 |
|---|---|---|
| `app.py` | 129 | FastAPI 服务：/resume 预览、/editor 编辑、/api/resume（JSON/YAML 读写）、/docs |
| `templates/resume.html` | 163 | Jinja2 简历模板（学习经历/代码/团队项目/个人项目/实验教程分段） |
| `templates/editor.html` | 68 | 左 YAML 编辑 + 右 iframe 实时预览 |
| `static/style.css` | 340 | 蓝色主题、A4 排版、打印友好（@media print 隐藏工具条） |
| `resume.yaml` | 53 | 示例数据模型 |

**API：** GET/PUT `/api/resume`（JSON 覆盖更新）、GET/PUT `/api/resume/raw`（YAML 读写，PUT 时 safe_load 校验）、`/resume`（HTML 预览）、`/editor`（编辑器）。

**数据模型：** basics（姓名/岗位/联系方式）、education、code、personal_docs、team_projects（date/company/role/name/highlights/tech_stack）、personal_projects、lab_tutorials。

## 与 TalentForge 的契合点

1. **简历产出补 TalentForge 空白**——D10"锻造人才"下我们已有画像（M1）、岗位决策（M2/M3）、作品源规划（M4），但缺"把画像/胜任力变成一份好简历"的能力。easyCV 的"数据→模板→A4→PDF"链路是天然补全方向。
2. **数据源模式同构**：它的 YAML ↔ 我们的 JSON profile 都是单一文件数据源；team_projects 的 highlights/tech_stack 结构与我们胜任力/作品源展示几乎对得上。
3. **PDF 导出零依赖**：打印友好 CSS + `window.print()`；M3 已是 FastAPI + 静态 Web，加 print CSS + 简历页即可，成本极低。
4. **编辑交互**：左数据 + 右实时预览的 iframe 模式简单有效，可借给简历校对流（spec-m3 §3 resume-review diff 视图的进阶形态）。

## 局限（照搬不可取）

- **定位不同**：它是排版工具，不管岗位/决策/画像。TalentForge 北极星是决策陪伴，简历产出是辅助能力。
- **视觉冲突**：蓝色 A4 简历主题 vs 我们 DESIGN.md 暖纸面/terracotta 体系——模板必须重做，不能直接套用。
- **极简到缺东西**：无字段校验、无版本历史、无多模板；参考足够，直接搬不够。

## 决策建议

把"**简历产出页**"（profile/画像 JSON → A4 打印模板 → PDF 导出，吸收 easyCV 思路 + 套 DESIGN.md 体系）记为 **M4 伴随项**，与作品源（D23/D24，GitHub/Gitee/arXiv）同期做——作品源数据正好喂简历 projects 部分，两者强相关。

借鉴清单（若 M4 立项）：
- `window.print()` + 打印友好 CSS 的 PDF 方案（零依赖）
- 单一数据源 → 模板渲染的解耦方式（YAML↔JSON 概念同构）
- 编辑/预览双栏 iframe 交互
- highlights + tech_stack 的项目展示结构（对齐胜任力/作品源）
