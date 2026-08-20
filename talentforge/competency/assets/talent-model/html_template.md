## HTML报告模板规范

> **全局配色标准（必须严格遵循）**
>
> 所有图表中，**同一维度编号（D1-D6）必须使用相同的颜色**，不得因图表类型不同而改变。
>
> | 维度 | 颜色代码 | 用途 |
> |:----:|---------|------|
> | D1 | `#7b8b78` | 橄榄绿 |
> | D2 | `#a88244` | 土黄 |
> | D3 | `#89a89b` | 青灰 |
> | D4 | `#8d6b61` | 砖红 |
> | D5 | `#64748b` | 蓝灰 |
> | D6 | `#31526b` | 深蓝 |
>
> **使用规则：**
> - 能力树使用半透明版本：`rgba(hex, 0.14)` 作为背景，`rgba(hex, 0.26)` 作为边框
> - 若报告只有5个维度，使用 D1-D5 的颜色
> - CSS `conic-gradient` 中的 rgba 取原色乘以约 0.85 透明度（如 `#7b8b78` → `rgba(123,139,120,0.85)`）
> - 散点图维度气泡、ECharts 能力树节点均须参照此表，不得使用 ECharts 默认色

生成的HTML必须包含以下结构：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>{ROLE_NAME} 候选人人才画像胜任力模型</title>
  <!-- 内嵌CSS样式（参考案例风格） -->
  <style>...</style>
</head>
<body>
  <header>
    <h1>{ROLE_NAME} 候选人人才画像胜任力模型</h1>
    <p>一句话画像描述...</p>
    <div class="source-strip">验证公司标签...</div>
  </header>
  
  <main>
    <!-- 建模口径说明 -->
    <div class="model-note">...</div>
    
    <!-- 01 旭日图：人才画像全景 -->
    <section>
      <div class="section-header">
        <span class="section-num">01</span>
        <span class="section-title">人才画像全景</span>
      </div>
      <div class="chart-wrapper">
        <div class="chart-toolbar">
          <button class="chart-export-btn" onclick="exportChart('chart-sunburst', 'png')" title="导出PNG">PNG</button>
          <button class="chart-export-btn" onclick="exportChart('chart-sunburst', 'jpeg')" title="导出JPEG">JPEG</button>
          <button class="chart-export-btn" onclick="exportChart('chart-sunburst', 'svg')" title="导出SVG">SVG</button>
        </div>
        <div id="chart-sunburst" class="chart-container">
          <!-- 方案A：ECharts 旭日图（全景概览，只显示维度名，二级折叠，三级不展开）：
          ⚠️ 旭日图约束（防文字堆叠）：
             - 只显示 D1-D6 维度名称（二级行为折叠不显示）
             - 三级证据节点禁止出现在旭日图中
             - D1维度名每个不超过 8 个字符
             - value 只表示结构占比，不要写精确数字
          {
            type: 'sunburst',
            data: [{
              name: 'D1 方向感',        // ← 仅维度名，禁止展开行为/证据
              itemStyle: { color: '#7b8b78' },
              children: []              // ← 二级折叠，hover时显示label，不展开子节点
            }, {
              name: 'D2 内驱力',
              itemStyle: { color: '#a88244' },
              children: []
            }, {
              name: 'D3 韧性',
              itemStyle: { color: '#89a89b' },
              children: []
            }, {
              name: 'D4 学习敏捷',
              itemStyle: { color: '#8d6b61' },
              children: []
            }, {
              name: 'D5 专业度',
              itemStyle: { color: '#64748b' },
              children: []
            }, {
              name: 'D6 协作力',
              itemStyle: { color: '#31526b' },
              children: []
            }],
            radius: ['15%', '90%'],
            label: { rotate: 'radial', fontSize: 11 }
          }
          -->

          <!-- 方案B（推荐）：CSS conic-gradient 旭日图 — 无需 ECharts，完全避免 value 数据问题。
          ⚠️ 旭日图约束：维度名不超过 8 字符；仅标注维度名称（二级折叠），三级证据不显示。
          用 CSS conic-gradient 绘制同心圆环，用 ring-chip 标注各维度名称。

          HTML:
          <div class="sunburst-stage">
            <div class="ring outer"></div>
            <div class="ring middle"></div>
            <div class="ring inner"></div>
            <div class="sun-center">
              <strong>候选人画像</strong>
              <span>维度 → 行为 → 证据</span>
            </div>
            <div class="ring-labels">
              <!-- ⚠️ 每个维度名不超过 8 个字符 -->
              <div class="ring-chip" style="top:18px;left:50%;transform:translateX(-50%)">D1 方向感</div>
              <div class="ring-chip" style="top:86px;right:52px">D2 内驱力</div>
              <div class="ring-chip" style="bottom:104px;right:38px">D3 韧性</div>
              <div class="ring-chip" style="bottom:18px;left:50%;transform:translateX(-50%)">D4 学习敏捷</div>
              <div class="ring-chip" style="bottom:104px;left:38px">D5 专业度</div>
              <div class="ring-chip" style="top:86px;left:52px">D6 协作力</div>
            </div>
          </div>
          <div class="sun-legend">
            <div class="legend-item"><span class="dot" style="background:#7b8b78"></span><span><strong>D1</strong>：质量标尺、性能意识</span></div>
            <div class="legend-item"><span class="dot" style="background:#a88244"></span><span><strong>D2</strong>：主动拆解、闭环推进</span></div>
            <div class="legend-item"><span class="dot" style="background:#89a89b"></span><span><strong>D3</strong>：回退恢复、持续试验</span></div>
            <div class="legend-item"><span class="dot" style="background:#8d6b61"></span><span><strong>D4</strong>：跨域学习、抽象迁移</span></div>
            <div class="legend-item"><span class="dot" style="background:#64748b"></span><span><strong>D5</strong>：CS 基础、系统判断</span></div>
            <div class="legend-item"><span class="dot" style="background:#31526b"></span><span><strong>D6</strong>：沟通清晰、文档测试</span></div>
          </div>

          CSS:
          .sunburst-stage{position:relative;height:420px;display:flex;align-items:center;justify-content:center}
          .ring{position:absolute;border-radius:50%;mask:radial-gradient(circle,transparent 0 57%,#000 57% 100%);-webkit-mask:radial-gradient(circle,transparent 0 57%,#000 57% 100%)}
          .ring.outer{width:360px;height:360px;opacity:.95;background:conic-gradient(#7b8b78 0 50deg,#a88244 50deg 105deg,#89a89b 105deg 160deg,#8d6b61 160deg 220deg,#64748b 220deg 280deg,#31526b 280deg 360deg)}
          .ring.middle{width:250px;height:250px;mask:radial-gradient(circle,transparent 0 47%,#000 47% 100%);-webkit-mask:radial-gradient(circle,transparent 0 47%,#000 47% 100%);background:conic-gradient(rgba(123,139,120,.82) 0 60deg,rgba(168,130,68,.82) 60deg 120deg,rgba(137,168,155,.85) 120deg 180deg,rgba(141,107,97,.82) 180deg 240deg,rgba(100,116,139,.85) 240deg 300deg,rgba(49,82,107,.85) 300deg 360deg)}
          .ring.inner{width:132px;height:132px;background:linear-gradient(135deg,#2f4b63,#1f3141);border:10px solid #f8f5ef}
          .sun-center{position:absolute;text-align:center;color:#fff;z-index:2;max-width:120px}
          .sun-center strong{display:block;font-size:20px;line-height:1.2}
          .sun-center span{font-size:12px;opacity:.88}
          .ring-labels{position:absolute;inset:0}
          .ring-chip{position:absolute;padding:6px 10px;border-radius:999px;background:rgba(251,250,247,.94);border:1px solid var(--line);font-size:12px;box-shadow:var(--shadow)}
          .sun-legend{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:8px}
          .legend-item{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--muted)}
          .dot{width:10px;height:10px;border-radius:50%;margin-top:6px;flex:0 0 auto}
          -->
        </div>
      </div>
    </section>

    <!-- 02 矩形树图：评估关注结构 -->
    <section>
      <div class="section-header">
        <span class="section-num">02</span>
        <span class="section-title">评估关注结构</span>
      </div>
      <div class="chart-wrapper">
        <div class="chart-toolbar">
          <button class="chart-export-btn" onclick="exportChart('chart-treemap', 'png')" title="导出PNG">PNG</button>
          <button class="chart-export-btn" onclick="exportChart('chart-treemap', 'jpeg')" title="导出JPEG">JPEG</button>
          <button class="chart-export-btn" onclick="exportChart('chart-treemap', 'svg')" title="导出SVG">SVG</button>
        </div>
        <div id="chart-treemap" class="chart-container">
          <!-- 方案A：ECharts 矩形树图（无 value 精确数字，纯结构占位）：
          ⚠️ 注意：value 只控制视觉面积比例（无真实数据），不要写精确数字或百分比。
          {
            type: 'treemap',
            data: [
              { name: 'D1 产品思维',
                children: [
                  { name: 'B1.1 需求分析' },
                  { name: 'B1.2 用户洞察' },
                  { name: 'B1.3 方案设计' }
                ]
              },
              { name: 'D2 执行力',
                children: [
                  { name: 'B2.1 项目管理' },
                  { name: 'B2.2 跨部门协作' }
                ]
              },
              { name: 'D3 技术理解',
                children: [
                  { name: 'B3.1 技术方案评估' },
                  { name: 'B3.2 技术风险判断' }
                ]
              },
              { name: 'D4 商业敏感',
                children: [
                  { name: 'B4.1 商业逻辑拆解' }
                ]
              },
              { name: 'D5 沟通影响',
                children: [
                  { name: 'B5.1 跨团队推动' }
                ]
              }
            ],
            label: { formatter: '{b}' },
            levels: [{ itemStyle: { borderWidth: 0 } }]
          }
          -->

          <!-- 方案B（推荐）：CSS Grid tile 矩形树图 — 无需 ECharts，完全避免 value 数据问题。
          用 CSS Grid 布局 + 彩色渐变 div 表示各维度的视觉权重区隔。

          HTML:
          <div class="treemap">
            <div class="tile b1">
              <div><h4>D1 方向与技术标尺</h4><p>看候选人是否把底层系统当长期事业。</p></div>
              <div class="subtiles">
                <div class="sub">质量/可靠性标尺</div>
                <div class="sub">长期投入与技术上限</div>
              </div>
            </div>
            <div class="tile b2">
              <div><h4>D2 内驱与主动闭环</h4><p>看是否能在模糊任务下自己启动。</p></div>
              <div class="subtiles">
                <div class="sub">主动拆解问题</div>
                <div class="sub">风险暴露与闭环</div>
              </div>
            </div>
            <div class="tile b3">
              <div><h4>D3 韧性与稳定推进</h4><p>看是否能在反复调优中保持节奏。</p></div>
              <div class="subtiles">
                <div class="sub">恢复力</div>
                <div class="sub">长链路耐心</div>
              </div>
            </div>
            <div class="tile b4">
              <div><h4>D4 学习敏捷与认知迁移</h4><p>看能否跨算法、系统、平台切换视角。</p></div>
              <div class="subtiles">
                <div class="sub">跨域学习</div>
                <div class="sub">抽象与迁移</div>
              </div>
            </div>
            <div class="tile b5">
              <div><h4>D5 工程基础与系统判断</h4><p>看基础知识能否转成工程判断。</p></div>
              <div class="subtiles">
                <div class="sub">编程/CS 基础</div>
                <div class="sub">系统 trade-off</div>
              </div>
            </div>
            <div class="tile b6">
              <div><h4>D6 协作与可信交付</h4><p>看是否能成为团队愿意继续合作的人。</p></div>
              <div class="subtiles">
                <div class="sub">沟通与文档</div>
                <div class="sub">测试/联调</div>
              </div>
            </div>
          </div>

          CSS:
          .treemap{min-height:420px;display:grid;grid-template-columns:1.05fr .95fr;gap:12px}
          .tile{border-radius:18px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;min-height:130px;color:#fff;position:relative;overflow:hidden}
          .tile h4{margin:0 0 6px;font-size:18px}
          .tile p{margin:0;font-size:13px;line-height:1.55;color:rgba(255,255,255,.9)}
          .tile .subtiles{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
          .tile .sub{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.16);padding:10px;border-radius:14px;font-size:12px}
          .b1{background:linear-gradient(135deg,#31526b,#23374a)} .b2{background:linear-gradient(135deg,#7b8b78,#667560)}
          .b3{background:linear-gradient(135deg,#8d6b61,#77584f)} .b4{background:linear-gradient(135deg,#89a89b,#6f9082)}
          .b5{background:linear-gradient(135deg,#a88244,#8d6e3e)} .b6{background:linear-gradient(135deg,#64748b,#4d5a6d)}
          @media(max-width:720px){.treemap{grid-template-columns:1fr}}
          -->
        </div>
      </div>
    </section>
    
    <!-- 03 散点图：人才分型象限 + 行为锚点表格 -->
    <section>
      <div class="section-header">
        <span class="section-num">03</span>
        <span class="section-title">人才分型象限 + 行为锚点</span>
      </div>
      <p class="section-desc">将候选人在各维度的表现投射到「成长潜力×当前能力」象限，识别不同发展路径的人才分型。</p>
      
      <!-- 散点图 -->
      <div class="chart-wrapper">
        <div class="chart-toolbar">
          <button class="chart-export-btn" onclick="exportChart('chart-scatter', 'png')" title="导出PNG">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            PNG
          </button>
          <button class="chart-export-btn" onclick="exportChart('chart-scatter', 'jpeg')" title="导出JPEG">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            JPEG
          </button>
          <button class="chart-export-btn" onclick="exportChart('chart-scatter', 'svg')" title="导出SVG">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            SVG
          </button>
        </div>
        <div id="chart-scatter" class="chart-container">
          <!-- 方案A：ECharts 散点图（无坐标数据，纯结构占位）：
          ⚠️ 注意：value 只表示气泡存在性，不写精确数字。适用于维度对比分布。
          {
            type: 'scatter',
            data: [
              // ⚠️ 配色必须与全局标准一致：D1=#7b8b78 D2=#a88244 D3=#89a89b D4=#8d6b61 D5=#64748b
              { name: 'D1', value: [null, null], itemStyle: { color: '#7b8b78' } },
              { name: 'D2', value: [null, null], itemStyle: { color: '#a88244' } },
              { name: 'D3', value: [null, null], itemStyle: { color: '#89a89b' } },
              { name: 'D4', value: [null, null], itemStyle: { color: '#8d6b61' } },
              { name: 'D5', value: [null, null], itemStyle: { color: '#64748b' } }
            ],
            xAxis: { name: '成长潜力（相对位置）', type: 'category' },
            yAxis: { name: '当前能力（相对位置）', type: 'category' }
          }
          -->

          <!-- 方案B（推荐）：CSS+SVG 四象限 — 无需 ECharts，完全避免坐标数据问题。
          展示"成长潜力 × 当前交付稳定性"的人才分型，四个象限代表四种培养路径。
          适用于校招/实习场景的人才分类，而非给维度打分。

          HTML:
          <div class="scatter-box">
            <div class="quad-label quad-1">高潜力 × 高稳定：优先争夺</div>
            <div class="quad-label quad-2">高潜力 × 低稳定：重点培养</div>
            <div class="quad-label quad-3">低潜力 × 低稳定：谨慎评估</div>
            <div class="quad-label quad-4">低潜力 × 高稳定：适合窄口径执行岗</div>
            <div class="axis-note axis-x">当前交付稳定性 →</div>
            <div class="axis-note axis-y">成长潜力 →</div>
            <svg class="scatter-svg" viewBox="0 0 900 420">
              <line x1="450" y1="30" x2="450" y2="390" stroke="#c9c2b8" stroke-width="2"/>
              <line x1="60" y1="210" x2="840" y2="210" stroke="#c9c2b8" stroke-width="2"/>
              <!-- 四个象限气泡（位置为相对结构，非真实数据） -->
              <g>
                <circle cx="620" cy="110" r="22" fill="#23374a" opacity=".92"/>
                <text x="620" y="116" text-anchor="middle" fill="#fff" font-size="12" font-weight="700">优先争夺</text>
                <text x="650" y="92" fill="#23374a" font-size="13" font-weight="700">自驱快跑型</text>
              </g>
              <!-- 维度气泡（用小圆点标注各维度的大致分布区域） -->
              <g>
                <!-- ⚠️ 配色必须与全局标准一致：D1=#7b8b78 D2=#a88244 D3=#89a89b D4=#8d6b61 D5=#64748b -->
                <circle cx="545" cy="156" r="10" fill="#8d6b61"/>
                <text x="560" y="160" fill="#5a3f38" font-size="12">D4</text>
                <circle cx="580" cy="176" r="10" fill="#a88244"/>
                <text x="595" y="180" fill="#8a5a2e" font-size="12">D2</text>
              </g>
            </svg>
          </div>

          CSS:
          .scatter-box{position:relative;border-radius:18px;background:linear-gradient(180deg,#fcfbf8,#f5f1e8);overflow:hidden}
          .scatter-svg{width:100%;height:100%}
          .quad-label{position:absolute;font-size:12px;color:var(--muted);background:rgba(251,250,247,.86);padding:6px 10px;border-radius:999px;border:1px solid var(--line)}
          .quad-1{top:14px;right:14px} .quad-2{top:14px;left:14px}
          .quad-3{bottom:14px;left:14px} .quad-4{bottom:14px;right:14px}
          .axis-note{position:absolute;font-size:13px;color:var(--deep);font-weight:700}
          .axis-x{bottom:10px;left:50%;transform:translateX(-50%)}
          .axis-y{left:10px;top:50%;transform:translateY(-50%) rotate(-90deg);transform-origin:left top}
          -->
        </div>
      </div>
      
      <!-- 行为锚点表格 -->
      <div class="persona-table">
        <table>
          <thead>
            <tr>
              <th>人才分型</th>
              <th>位置特征</th>
              <th>核心特征</th>
              <th>典型信号</th>
              <th>培养建议</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>🌱 潜力型</td>
              <td>潜力高 × 能力低</td>
              <td>学习敏锐度高、好奇心强、适应性好</td>
              <td>快速掌握新概念、主动提问、跨领域迁移</td>
              <td>给予挑战性任务、配对导师、关注基础夯实</td>
            </tr>
            <tr>
              <td>⚡ 达标型</td>
              <td>潜力中 × 能力中</td>
              <td>执行力强、稳定性好、团队协作佳</td>
              <td>按时交付、主动汇报、乐于帮助他人</td>
              <td>逐步增加挑战性、鼓励承担更多责任</td>
            </tr>
            <tr>
              <td>🔥 突出型</td>
              <td>潜力高 × 能力高</td>
              <td>成长型思维、卓越交付、影响力强</td>
              <td>超预期交付、带动团队、推动创新</td>
              <td>授权更多自主权、战略性项目、领导力培养</td>
            </tr>
            <tr>
              <td>⏸️ 平台型</td>
              <td>潜力中 × 能力高</td>
              <td>经验丰富、稳健可靠、专业深度</td>
              <td>独当一面、知识沉淀、稳定输出</td>
              <td>保持稳定发挥、适度引入新挑战、传承经验</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    
    <!-- 04 能力树：完整MECE结构 -->
    <section>
      <div class="section-header">
        <span class="section-num">04</span>
        <span class="section-title">完整MECE结构</span>
      </div>
      <p class="section-desc">先按二级行为发问，再用三级证据确认真实性。这个结构更适合面试设计和评审校准。</p>
      <div class="chart-wrapper">
        <div class="chart-toolbar">
          <button class="chart-export-btn" onclick="exportChart('chart-tree', 'png')" title="导出PNG">PNG</button>
          <button class="chart-export-btn" onclick="exportChart('chart-tree', 'jpeg')" title="导出JPEG">JPEG</button>
          <button class="chart-export-btn" onclick="exportChart('chart-tree', 'svg')" title="导出SVG">SVG</button>
        </div>
        <div id="chart-tree" class="chart-container">
          <!-- ECharts 能力树配置示例（横向 LR 布局）：
          {
            type: 'tree',
            orient: 'LR',  // 横向左右布局
            symbol: 'rectangle',
            symbolSize: [130, 34],  // 节点宽度收窄，控制横向占用
            nodePadding: 12,
            layerPadding: 50,       // ← 层级间横向距离调大，避免叠压
            initialTreeDepth: 2,    // 默认展开到 B 层（E 层折叠），首次展开不会太宽
            roam: true,
            itemStyle: { borderRadius: 8 },
            label: { fontSize: 12, color: '#e8edf7' },
            leaves: { label: { color: '#9ca8c6', fontSize: 11 } },
            data: [{
              name: '{ROLE_NAME}\n胜任力模型',
              // 根节点使用D1基准色（半透明）
              itemStyle: { color: 'rgba(123,139,120,0.18)', borderColor: 'rgba(123,139,120,0.35)' },
              children: [
                // ⚠️ 配色必须与全局标准一致：D1=#7b8b78 D2=#a88244 D3=#89a89b D4=#8d6b61 D5=#64748b D6=#31526b
                // 能力树半透明用法：背景用 rgba(hex, 0.14)，边框用 rgba(hex, 0.26)
                { name: 'D1', itemStyle: { color: 'rgba(123,139,120,0.14)', borderColor: 'rgba(123,139,120,0.26)' }, children: [
                  { name: 'B1.1 追问性能瓶颈', children: [{ name: 'profiling/kernel意识' }] },
                  { name: 'B1.2 系统边界映射', children: [{ name: '通信/显存/带宽意识' }] }
                ]},
                { name: 'D2', itemStyle: { color: 'rgba(168,130,68,0.14)', borderColor: 'rgba(168,130,68,0.26)' }, children: [
                  { name: 'B2.1 不等spec也能推进', children: [{ name: '补环境/补数据/补验证' }] },
                  { name: 'B2.2 拉到可运行结果', children: [{ name: '独立debug/主动补位' }] }
                ]},
                { name: 'D3', itemStyle: { color: 'rgba(137,168,155,0.14)', borderColor: 'rgba(137,168,155,0.26)' }, children: [
                  { name: 'B3.1 开放题先建模', children: [{ name: '计算/通信/存储/调度层次' }] },
                  { name: 'B3.2 做trade-off', children: [{ name: '论文到实现/框架迁移' }] }
                ]},
                { name: 'D4', itemStyle: { color: 'rgba(141,107,97,0.14)', borderColor: 'rgba(141,107,97,0.26)' }, children: [
                  { name: 'B4.1 追根因不绕路', children: [{ name: '攻坚经历/长周期稳定' }] },
                  { name: 'B4.2 长周期不掉线', children: [{ name: '复盘再启动' }] }
                ]},
                { name: 'D5', itemStyle: { color: 'rgba(100,116,139,0.14)', borderColor: 'rgba(100,116,139,0.26)' }, children: [
                  { name: 'B5.1 建立共同语言', children: [{ name: '跨算法/平台/业务' }] },
                  { name: 'B5.2 分歧中推动对齐', children: [{ name: 'code review/跨团队' }] }
                ]},
                { name: 'D6', itemStyle: { color: 'rgba(49,82,107,0.14)', borderColor: 'rgba(49,82,107,0.26)' }, children: [
                  { name: 'B6.1 区分补丁与建设', children: [{ name: '长期思维/可复利' }] },
                  { name: 'B6.2 质量/效率/成本', children: [{ name: '优化边界感/取舍' }] }
                ]}
              ]
            }]
          }
          -->
        </div>
      </div>
    </section>

    <!-- 【备选】CSS/HTML 能力树 — 超长内容时可滚动，永不截断 -->
    <details style="margin-top: 0.75rem;">
      <summary style="cursor:pointer; color: var(--text-muted); font-size: 0.82rem; padding: 0.3rem 0;">
        📋 备选：CSS/HTML 树（超长时横向滚动）
      </summary>
      <div class="competency-tree" style="margin-top: 0.75rem;">
        <ul>
          <li>
            <span class="tree-node root">{ROLE_NAME} 胜任力模型</span>
            <ul>
              <li><span class="tree-node d1">D1 系统与性能直觉</span>
                <ul>
                  <li><span class="tree-node">B1.1 会主动追问性能、资源与瓶颈</span></li>
                  <li><span class="tree-node">B1.2 能把软件问题映射到系统边界</span></li>
                  <li><span class="tree-node evidence">E：profiling/kernel优化/通信显存带宽意识</span></li>
                </ul>
              </li>
              <li><span class="tree-node d2">D2 工程驱动与闭环</span>
                <ul>
                  <li><span class="tree-node">B2.1 不等spec完整也能推进</span></li>
                  <li><span class="tree-node">B2.2 能把方案拉到可运行结果</span></li>
                  <li><span class="tree-node evidence">E：项目交付/独立debug/主动补位</span></li>
                </ul>
              </li>
              <li><span class="tree-node d3">D3 抽象建模与学习迁移</span>
                <ul>
                  <li><span class="tree-node">B3.1 面对开放题先建模</span></li>
                  <li><span class="tree-node">B3.2 能做trade-off并解释原因</span></li>
                  <li><span class="tree-node evidence">E：系统设计/论文到实现/框架迁移</span></li>
                </ul>
              </li>
              <li><span class="tree-node d4">D4 韧性与长期投入</span>
                <ul>
                  <li><span class="tree-node">B4.1 卡点后继续追根因</span></li>
                  <li><span class="tree-node">B4.2 长周期任务不掉线</span></li>
                  <li><span class="tree-node evidence">E：攻坚经历/稳定投入/复盘再启动</span></li>
                </ul>
              </li>
              <li><span class="tree-node d5">D5 协作沟通与影响</span>
                <ul>
                  <li><span class="tree-node">B5.1 能与算法/平台/业务建立共同语言</span></li>
                  <li><span class="tree-node">B5.2 在分歧里推动对齐</span></li>
                  <li><span class="tree-node evidence">E：code review/接口对接/跨团队推进</span></li>
                </ul>
              </li>
              <li><span class="tree-node d6">D6 方向感与结果标尺</span>
                <ul>
                  <li><span class="tree-node">B6.1 能区分短期补丁与长期建设</span></li>
                  <li><span class="tree-node">B6.2 对质量/效率/成本有判断</span></li>
                  <li><span class="tree-node evidence">E：技术取舍说明/长期项目偏好/优化边界感</span></li>
                </ul>
              </li>
            </ul>
          </li>
        </ul>
      </div>
    </details>
    
    <!-- 【可选】自测矩阵（三水位对照） -->
    <!-- 仅当用户选择添加自测矩阵功能时包含此节 -->
    <section class="self-check-section">
      <div class="section-header">
        <span class="section-num">04.5</span>
        <span class="section-title">自测矩阵（三水位对照）</span>
      </div>
      <p class="section-desc">帮助候选人自我评估在各维度的当前水位，明确下一步努力方向。适合自测、培训发展、辅导对话等场景。</p>
      
      <div class="matrix-legend">
        <span><span class="matrix-level level-seedling"></span> 🌱 起步 — 尚未稳定展现该特质</span>
        <span><span class="matrix-level level-qualified"></span> ⚡ 达标 — 在多数场景能稳定展现</span>
        <span><span class="matrix-level level-outstanding"></span> 🔥 突出 — 在复杂场景也能引领示范</span>
      </div>
      
      <div class="self-check-matrix">
        <div class="matrix-grid">
          <!-- 表头 -->
          <div class="matrix-header">胜任力维度</div>
          <div class="matrix-header">🌱 起步</div>
          <div class="matrix-header">⚡ 达标</div>
          <div class="matrix-header">🔥 突出</div>
          <div class="matrix-header">下一步努力方向</div>
          
          <!-- 示例行 -->
          <div class="matrix-cell matrix-dim-name">方向与标尺</div>
          <div class="matrix-cell">
            <label><input type="radio" name="dim1" value="seedling"><span>能完成指定任务，但对目标主动思考较少</span></label>
          </div>
          <div class="matrix-cell">
            <label><input type="radio" name="dim1" value="qualified"><span>能理解任务背景，对质量有一定追求</span></label>
          </div>
          <div class="matrix-cell">
            <label><input type="radio" name="dim1" value="outstanding"><span>主动定义目标，推动标准提升，带动他人</span></label>
          </div>
          <div class="matrix-cell matrix-action">→ 主动认领有挑战的子目标，记录质量反思</div>
          
          <!-- 更多维度行... -->
        </div>
      </div>
      
      <div class="matrix-tip">
        <strong>使用建议：</strong>
        <ul>
          <li>建议在安静的时段独立完成，避免匆忙勾选</li>
          <li>如有具体事例支撑选择，会更有价值</li>
          <li>「下一步」方向可与导师或上级讨论确认</li>
        </ul>
      </div>
    </section>
    
    <!-- 05 官网岗位链接（人工检验） -->
    <section>
      <div class="section-header">
        <span class="section-num">05</span>
        <span class="section-title">官网岗位链接（人工检验）</span>
      </div>
      <p class="section-desc">以下链接仅作为人工校验这个模型的外部参照：能切到校招、应届生招聘或实习的，已优先切换；其余保留官方招聘入口作为补充。目的不是要求年轻候选人与资深岗位逐项对标，而是观察不同公司在早期人才身上重视哪些稳定特征。</p>
      <div class="validation-note">阅读建议：优先关注岗位或校招页中反复出现的学习潜力、主动性、责任感、工程基础、协作气质与长期建设倾向，而不是逐条比对工具栈。对年轻候选人，更适合看"能否长成"而不是"是否已经全部具备"。</div>
      <div class="link-grid">
        <!-- 链接卡片示例 -->
        <a class="link-card" href="{公司官网校招/实习链接}" target="_blank" rel="noopener noreferrer">
          <div class="link-card-meta">{公司名} · 官方校招 / 实习</div>
          <div class="link-card-title">{岗位名称}</div>
          <div class="link-card-desc">检验点：{简明说明这个链接用来检验什么，例如"观察对潜力、主动性、协作气质的要求"}</div>
        </a>
        <!-- 更多链接卡片... -->
      </div>
    </section>
  </main>
  
  <footer>...</footer>
  
  <!-- ECharts + 图表初始化脚本（已配置CDN自动降级） -->
  <script>
    // CDN 自动降级加载：jsdelivr → unpkg → 本地文件
    (function() {
      var cdnList = [
        'https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js',
        'https://unpkg.com/echarts@5.4.3/dist/echarts.min.js'
      ];
      var localPath = 'assets/echarts.min.js'; // 本地内嵌备用路径
      var loadIndex = 0;

      function loadScript(src, onSuccess, onError) {
        var script = document.createElement('script');
        script.src = src;
        script.onload = onSuccess;
        script.onerror = onError;
        document.head.appendChild(script);
      }

      function tryNext() {
        if (loadIndex < cdnList.length) {
          loadScript(cdnList[loadIndex++], function() {
            console.log('[ECharts] Loaded from CDN: ' + cdnList[loadIndex - 1]);
          }, tryNext);
        } else {
          // 降级到本地文件
          loadScript(localPath, function() {
            console.log('[ECharts] Loaded from local fallback');
          }, function() {
            console.error('[ECharts] Failed to load ECharts from all sources');
          });
        }
      }

      tryNext();
    })();
  </script>
  <script>...</script>
</body>
</html>
```

**图表数据规则：**
- value 仅表达相对关注重心，不表示精确分数
- 颜色区分6个主维度
- 所有图表支持SVG导出

**图表导出功能规范：**

```css
/* 图表工具栏 */
.chart-wrapper {
  position: relative;
  margin-bottom: 1.5rem;
}
.chart-toolbar {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  display: flex;
  gap: 0.35rem;
  z-index: 10;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.chart-wrapper:hover .chart-toolbar {
  opacity: 1;
}
.chart-export-btn {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.35rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.chart-export-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
  background: rgba(59,130,246,0.06);
}
.chart-container {
  min-height: 400px;
  overflow: auto; /* 安全兜底：ECharts 图表超出容器时允许滚动 */
}
@media (max-width: 768px) {
  .chart-toolbar { opacity: 1; }
  .chart-container { min-height: 300px; }
}

/* 方案A（推荐）：CSS/HTML 能力树 — 永不截断，天然响应式 */
.competency-tree {
  margin-top: 0.5rem;
  padding: 0.5rem 0 0 0.5rem;
  overflow-x: auto; /* 超长树允许横向滚动 */
}
.competency-tree ul {
  list-style: none;
  margin: 0;
  padding-left: 22px;
  position: relative;
}
.competency-tree ul::before {
  content: "";
  position: absolute;
  left: 8px;
  top: 0;
  bottom: 10px;
  border-left: 1px dashed rgba(130, 160, 255, 0.18);
}
.competency-tree li {
  position: relative;
  margin: 10px 0;
}
.competency-tree li::before {
  content: "";
  position: absolute;
  left: -14px;
  top: 14px;
  width: 14px;
  border-top: 1px dashed rgba(130, 160, 255, 0.18);
}
.tree-node {
  display: inline-block;
  padding: 9px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.07);
  color: #e8edf7;
  font-size: 0.84rem;
  line-height: 1.4;
}
.tree-node.root {
  background: rgba(91, 140, 255, 0.12);
  border-color: rgba(91, 140, 255, 0.30);
  font-weight: 700;
  color: #dce7ff;
}
.tree-node.d1 { border-color: rgba(91, 140, 255, 0.28); }
.tree-node.d2 { border-color: rgba(33, 199, 183, 0.26); }
.tree-node.d3 { border-color: rgba(242, 185, 75, 0.24); }
.tree-node.d4 { border-color: rgba(239, 107, 168, 0.24); }
.tree-node.d5 { border-color: rgba(167, 139, 250, 0.24); }
.tree-node.d6 { border-color: rgba(251, 146, 60, 0.24); }
.tree-node.evidence {
  background: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.05);
  color: #9ca8c6;
  font-size: 0.78rem;
}
```

**导出功能 JS 实现：**
```javascript
// ECharts 图表导出功能（支持 PNG / SVG / JPEG 三种格式）
function exportChart(chartId, format) {
  var chart = echarts.getInstanceByDom(document.getElementById(chartId));
  if (!chart) {
    console.error('[Export] Chart instance not found: ' + chartId);
    return;
  }

  var formats = {
    png: { type: 'png', pixelRatio: 2, quality: 1 },
    jpeg: { type: 'jpeg', pixelRatio: 2, quality: 0.8 },
    svg: { type: 'svg' }
  };

  var option = formats[format];
  if (!option) {
    console.error('[Export] Unsupported format: ' + format);
    return;
  }

  try {
    var url = chart.getDataURL(option);
    var link = document.createElement('a');
    var timestamp = new Date().toISOString().slice(0, 10);
    link.download = chartId + '_' + timestamp + '.' + format;
    link.href = url;
    link.click();
    console.log('[Export] Successfully exported ' + format.toUpperCase() + ' for ' + chartId);
  } catch (e) {
    console.error('[Export] Failed to export chart:', e);
  }
}

// 全局导出函数（供按钮 onclick 调用）
window.exportChart = exportChart;
```

**人才分型表格样式规范：**
```css
.persona-table {
  margin-top: 1.5rem;
  overflow-x: auto;
}
.persona-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.persona-table th,
.persona-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.persona-table th {
  background: var(--surface);
  font-weight: 700;
  color: var(--text);
  font-size: 0.85rem;
}
.persona-table td:first-child {
  font-weight: 700;
  color: var(--primary);
  white-space: nowrap;
}
.persona-table tr:hover td {
  background: var(--surface);
}
```

**自测矩阵样式规范（可选功能）：**
```css
.self-check-matrix {
  margin-top: 1.5rem;
}
.matrix-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 1.5fr;
  gap: 0;
  font-size: 0.88rem;
}
.matrix-header {
  background: var(--surface);
  font-weight: 700;
  font-size: 0.82rem;
  color: var(--text-muted);
}
.matrix-header,
.matrix-cell {
  padding: 0.75rem;
  border-bottom: 1px solid var(--border);
}
.matrix-dim-name {
  font-weight: 600;
  color: var(--text);
}
.matrix-cell { color: var(--text-muted); }
.matrix-cell label { display: flex; align-items: flex-start; gap: 0.5rem; cursor: pointer; }
.matrix-level {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-top: 3px;
  flex-shrink: 0;
}
.level-seedling { background: #22c55e; }   /* 起步 */
.level-qualified { background: #3b82f6; }  /* 达标 */
.level-outstanding { background: #f59e0b; } /* 突出 */
.matrix-action { font-size: 0.85rem; color: var(--text-muted); }
.matrix-legend {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
  font-size: 0.85rem;
  color: var(--text-muted);
}
.matrix-legend span { display: flex; align-items: center; gap: 0.4rem; }
@media (max-width: 900px) {
  .matrix-grid { grid-template-columns: 1fr; }
  .matrix-header { display: none; }
  .matrix-cell { border-left: 3px solid var(--border); padding-left: 1rem; }
}
```

**链接卡片样式规范：**
```css
.validation-note {
  margin-bottom: 1rem;
  color: var(--text-muted);
  font-size: 0.92rem;
}
.link-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.link-card {
  display: block;
  text-decoration: none;
  color: inherit;
  background: var(--surface);
  border: 1px solid rgba(59,130,246,0.16);
  border-radius: 12px;
  padding: 1rem 1.1rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.04);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.link-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(15,23,42,0.08);
  border-color: rgba(59,130,246,0.3);
}
.link-card-title {
  font-size: 0.98rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 0.35rem;
}
.link-card-meta {
  font-size: 0.82rem;
  color: var(--primary);
  margin-bottom: 0.35rem;
  font-weight: 600;
}
.link-card-desc {
  font-size: 0.9rem;
  color: var(--text-muted);
}
@media (max-width: 900px) {
  .link-grid { grid-template-columns: 1fr; }
}
```

**链接选择优先级：**
1. 优先使用官方校招/实习入口
2. 其次使用官方 careers/招聘主页
3. 最后才用具体岗位页面（标注为"上限参照"）

**链接卡片标签规范：**
- 校招/实习入口：`{公司} · 官方校招 / 实习`
- 官方招聘主页：`{公司} · 官方招聘入口`
- 上限参照岗位：`{公司} · 官方岗位（上限参照）`

**每个卡片必须包含：**
- `link-card-meta`：公司名和入口类型
- `link-card-title`：具体岗位或页面名称
- `link-card-desc`：**必须包含"检验点"**，说明这个链接用来检验模型的哪个维度或特质
