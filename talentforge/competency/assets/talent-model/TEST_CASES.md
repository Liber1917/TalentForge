# TalentModel-skill 测试用例集
# 测试目标：验证 skill 的泛化能力以及先验胜任力模型的恰当性
# 验证公司组合说明：每组至少覆盖 2 种企业类型，避免单一互联网大厂偏差
# TC-001~TC-008 均已混入中型/垂直行业/传统行业企业

---

## 测试用例 1：技术类 - 社招中级

```yaml
ROLE_NAME: 后端开发工程师
TALENT_LEVEL: 社招 3-5年
USE_CASE: 招聘筛选
VALIDATION_COMPANIES: 字节跳动, 腾讯, 科大讯飞
ENTERPRISE_TYPES: 互联网大厂, 互联网大厂, 中型成长期
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: false
CHART_RENDER: cdn
```

---

## 测试用例 2：技术类 - 校招

```yaml
ROLE_NAME: 前端开发实习生
TALENT_LEVEL: 校招大三/研二
USE_CASE: 实习招聘
VALIDATION_COMPANIES: 字节跳动, 小红书, 网易
ENTERPRISE_TYPES: 互联网大厂, 中型成长期, 互联网大厂
OUTPUT_FORMAT: markdown
SELF_CHECK_MATRIX: false
CHART_RENDER: offline
```

---

## 测试用例 3：产品类

```yaml
ROLE_NAME: 产品经理
TALENT_LEVEL: 社招 5年+
USE_CASE: 晋升评估
VALIDATION_COMPANIES: 腾讯, 字节跳动, 纷享销客, 华为
ENTERPRISE_TYPES: 互联网大厂, 互联网大厂, 中型成长期, 传统行业
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: true
CHART_RENDER: offline
```

---

## 测试用例 4：设计类

```yaml
ROLE_NAME: UI/UX 设计师
TALENT_LEVEL: 社招 1-3年
USE_CASE: 招聘筛选
VALIDATION_COMPANIES: 字节跳动, 小米, 大疆, 特斯拉上海
ENTERPRISE_TYPES: 互联网大厂, 传统行业(消费电子), 垂直行业(制造), 外资
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: true
CHART_RENDER: cdn
```

---

## 测试用例 5：数据类

```yaml
ROLE_NAME: 数据分析师
TALENT_LEVEL: 校招
USE_CASE: 校园招聘
VALIDATION_COMPANIES: 阿里巴巴, 京东, 东方财富, 恒生电子
ENTERPRISE_TYPES: 互联网大厂, 互联网大厂, 垂直行业(金融), 垂直行业(金融IT)
OUTPUT_FORMAT: markdown
SELF_CHECK_MATRIX: false
CHART_RENDER: offline
```

---

## 测试用例 6：算法类 - 高级

```yaml
ROLE_NAME: 算法工程师（推荐方向）
TALENT_LEVEL: 资深专家 P7+
USE_CASE: 高端人才猎聘
VALIDATION_COMPANIES: 字节跳动, 腾讯, 第四范式, 科大讯飞
ENTERPRISE_TYPES: 互联网大厂, 互联网大厂, 中型成长期, 中型成长期
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: false
CHART_RENDER: cdn
```

---

## 测试用例 7：运营类

```yaml
ROLE_NAME: 用户运营
TALENT_LEVEL: 社招 2-4年
USE_CASE: 招聘面试设计
VALIDATION_COMPANIES: 拼多多, 美团, Keep, 泡泡玛特
ENTERPRISE_TYPES: 互联网大厂, 互联网大厂, 中型成长期, 中型成长期
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: true
CHART_RENDER: offline
```

---

## 测试用例 8：管理类

```yaml
ROLE_NAME: 技术团队负责人（TL）
TALENT_LEVEL: 管理者 10-30人团队
USE_CASE: 晋升评估
VALIDATION_COMPANIES: 腾讯, 阿里云, 钉钉, 美的集团
ENTERPRISE_TYPES: 互联网大厂, 互联网大厂, 中型成长期, 传统行业
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: false
CHART_RENDER: offline
```

---

## 测试用例 9：传统行业 - 金融

```yaml
ROLE_NAME: 金融科技工程师
TALENT_LEVEL: 社招 3-5年
USE_CASE: 内部培训规划
VALIDATION_COMPANIES: 蚂蚁集团, 招商银行金融科技, 恒生电子, 东方财富
ENTERPRISE_TYPES: 垂直行业(金融), 垂直行业(金融), 垂直行业(金融IT), 垂直行业(金融)
OUTPUT_FORMAT: html
SELF_CHECK_MATRIX: true
CHART_RENDER: offline
```

---

## 测试用例 10：传统行业 - 制造业

```yaml
ROLE_NAME: 智能制造工程师
TALENT_LEVEL: 社招 5年+
USE_CASE: 人才盘点
VALIDATION_COMPANIES: 华为, 海尔智家, 比亚迪, 宁德时代
ENTERPRISE_TYPES: 垂直行业(通信/制造), 垂直行业(制造), 垂直行业(制造), 垂直行业(制造)
OUTPUT_FORMAT: markdown
SELF_CHECK_MATRIX: false
CHART_RENDER: offline
```

---

## 测试覆盖矩阵

| 维度 | 覆盖情况 |
|------|----------|
| 岗位类型 | 技术(3), 产品(1), 设计(1), 数据(1), 运营(1), 管理(1), 金融(1), 制造(1) |
| 人才级别 | 校招(3), 初级(2), 中级(2), 资深(2), 管理(1) |
| 使用场景 | 招聘筛选(4), 晋升评估(2), 面试设计(1), 培训规划(1), 人才盘点(1), 猎聘(1) |
| 行业 | 互联网(7), 金融(1), 制造(1), 混合(1) |
| 验证公司企业类型多样性 | TC-001~008均含≥2种类型; TC-009/010同行业多点对标 |
| 输出格式 | HTML(7), Markdown(3) |
| 自测矩阵 | 是(4), 否(6) |
| 渲染方式 | 离线(7), CDN(3) |

---

## 验证公司企业类型分类参考

| 企业 | 类型 | 说明 |
|------|------|------|
| 字节跳动/腾讯/阿里/美团/拼多多/网易 | 互联网大厂 | 第一梯队，市值万亿级 |
| 小红书/科大讯飞/Keep/泡泡玛特/第四范式/满帮 | 中型成长期 | 独角兽或上市中型，估值数百亿至数千亿 |
| 蚂蚁集团/恒生电子/东方财富/招商银行金融科技 | 垂直行业龙头-金融 | 金融科技/互联网金融 |
| 华为/海尔智家/比亚迪/宁德时代/美的/大疆 | 垂直行业龙头-制造 | 制造业数字化转型 |
| 特斯拉上海/微软中国/IBM中国/西门子中国 | 外资/跨国企业 | 全球胜任力框架，中国为执行层 |
| 纷享销客/钉钉/有赞/北森 | 企业服务SaaS | 中型互联网/垂直SaaS |

---

生成时间：2026-04-09 13:00
