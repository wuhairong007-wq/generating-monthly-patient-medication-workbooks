# 洞察报告中间数据契约

`extract_insight_sources.py` 输出 `insight.json`。默认输入月度患者清单、患者随访、症状自评和用药提醒四类必填工作簿，不良反应清单选填（合计4或5份）。兼容旧患者主表、健康管理方案、跟踪提醒、智能随访、症状自评、逐药用药清单六类必填及可选不良反应清单（6/7份）；角色按表头识别，日期事件按服务周期闭区间过滤。

`metadata` 保存产品、周期、患者数、地区数、疾病数及合同目标；`metrics` 保存画像、服务执行、随访、症状、用药、不良反应、风险和目标指标。所有比例对象包含 `numerator`、`denominator`、`value`、`display`，空集合保留零计数和实际分母。患者主表 `userid` 必须非空且唯一，其他表使用 `userid` 或 `患者ID` 关联。症状评分按 A-E 映射为 1-5 分。

仅旧6/7表模式：服务响应率按照各患者的响应率对提醒次数加权估算，报告中必须标明该统计口径；症状自评按有效六维度答卷次数统计，并报告有效答卷数。风险分层为：存在人工干预或高度/重度/严重/危及生命不良反应患者为高风险，其余发生不良反应患者为中风险，未匹配事件登记患者在内部表示为低风险，月度报告须写为“未登记事件患者”，不作临床安全结论。

不良反应清单省略时，`sourceDiagnostics.roles.adverseEvents.provided=false`，路径、表头行和行数为 `null`；`records.adverseEvents=[]` 仅维持记录结构。`metrics.adverseEvents.provided=false`，事件人数、例数及 `adverseEventRate` 为 `null`，分布与 `riskDistribution` 为空，`serviceGoals` 不包含不良反应监测比例。已提供清单（含仅表头的空表）时 `provided=true`，按周期内实际记录统计；零条事件仍保留实际患者分母。两种状态不能混同。

## 月度模式

`metadata.inputMode=monthly`，旧模式为`legacy`。`records.medicationReminders`保存按日期及主表患者过滤的方案记录；`sourceDiagnostics.roles`记录`sourceRows`、`includedRows`（周期内）、`matchedRows`及`unmatchedRows`。明细未匹配患者不纳入指标。

`metrics.monthlySummary`保存`sourceMonth`、`matchesPeriod`和`sourceReminderTotal`。只有主表标题月份与请求完整自然月一致且各行提醒次数合法时，`serviceExecution.medicationReminders/totalPrompts`才采用源汇总，否则为`null`。不将其他月份计数移入请求周期。

`reminderPlanCoverage`按周期内确认方案的唯一患者数/主表人数计算；`medications.drugDistribution`来自明确的联合用药药名，按患者药名去重；`combinationModeDistribution`按登记记录计数；`planCycleDistribution`直接来自用药周期字段。规格、频次、逐药疗程分布为空，不能从叙述推导。

`healthPlanCoverage`、响应率、体温和血压心率监测等无对应输入的指标为`null`，报告与图表不得将其转成零或推测值。疾病/年龄模块覆盖只含用药方案登记、智能随访、症状自评。随访`positiveRate`键为兼容中间格式保留，但月度语义仅为A/B选项占比，按实际题目解释。无完整自评答卷时均值不可用，不绘制零分雷达图。
