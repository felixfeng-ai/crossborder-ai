# 跨境电商 IP 风险初筛

## 目标

在现有合规审查链路中增加可解释、可复现的知识产权风险初筛，覆盖 Listing
文本和按需触发的商品图。输出风险等级、命中证据和建议动作，不做侵权或法律结论。

## 非目标

- 不做商标注册检索、近似率计算或授权真实性判定
- 不做专利查新、权利要求拆解或新颖性判断
- 不接外部商标、专利或反查图片 API
- 不把品牌词配置放入数据库

## 能力一：文本 IP 初筛

### Requirement

每次 Listing 合规生成和人工重新合规时，必须运行确定性文本规则。

### Scenario: 未授权品牌声明

- Given Listing 中出现品牌词配置中的品牌
- And 没有对应的有效品牌授权声明
- When 执行 IP 初筛
- Then 输出 high 风险项
- And evidence 包含字段、原文、起止位置

### Scenario: 已提供品牌授权

- Given 品牌命中且存在有效授权声明
- When 执行初筛
- Then 降级为 info 或 low
- And 仍提示人工核验授权真实性

### Scenario: 无证据认证声称

- Given Listing 声称 CE、FDA、UL、FCC 或 RoHS
- And 没有对应且有效的认证声明
- When 执行初筛
- Then 输出 CERTIFICATION_CLAIM_WITHOUT_EVIDENCE

### Scenario: 类目授权提示

- Given 请求、商品或品牌配置能够确定类目
- When 命中需要授权链的类目规则
- Then 输出 medium 风险提示
- And 不把提示描述成确定的法律结论

### Scenario: 确定性

- Given 相同文本、相同规则版本和相同授权数据
- When 连续执行两次
- Then 风险 code、severity、evidence 和排序完全一致

## 能力二：商品图视觉初筛

### Requirement

图片检查必须是可选增强层。未配置视觉模型时仍完成文本链路。

### Scenario: 未配置视觉模型

- Given 用户请求 scope=both
- And 平台没有可用视觉模型配置
- When 执行初筛
- Then status=partial
- And coverage.image=not_checked
- And overall_risk=unknown
- And 不返回 HTTP 500

### Scenario: 视觉模型返回 Logo 区域

- Given 视觉模型识别到疑似 Logo、水印或 IP 形象
- When 返回有效 normalized_1000 bbox
- Then 风险项保存 asset_id 和 bbox
- And 仅使用“疑似/待核实”措辞

### Scenario: 无 bbox

- Given 视觉模型返回风险信号但没有区域坐标
- When 聚合风险
- Then 不伪造坐标
- And 标记为人工复核

## 能力三：风险报告与发布 Gate

### Requirement

IP 风险必须与现有 compliance_status 分离，并绑定 Listing 版本。

### Scenario: 高风险发布

- Given 当前 Listing 版本存在 high IP 风险
- When 发布到 Shopify 或 Amazon
- Then 阻止发布
- And 返回 report_id 和风险摘要

### Scenario: 版本失效

- Given Listing 修改后版本递增
- When 发布
- Then 旧版本 IP 报告不得复用

### Scenario: 未检查图片

- Given 文本已检查但图片未检查
- When 用户查看报告或发布
- Then 不显示为完全合规通过

## 能力四：AI 决策助手

### Requirement

AI 决策助手和营销 Agent 共用同一个 IP 初筛服务与 `screen_ip_risk` 工具。

### Scenario: 复用报告

- Given 当前 Listing 版本已有相同规则版本的 IP 报告
- When Agent 再次检查
- Then 默认返回已有报告
- And 不重复调用视觉模型

## 验收标准

- 故意违规样例包含品牌词和无证据认证声称时返回 high 风险并阻止发布。
- 文本二次执行结果一致。
- 无视觉模型时图片项标记未检查，链路不报错。
- 风险证据可定位到文本片段或图片 bbox。
- 现有 Listing 生成、合规状态和 Agent 其他工具行为不被破坏。
- 新增逻辑测试覆盖率不低于 80%。
