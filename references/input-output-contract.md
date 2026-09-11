# 输入、输出和产品 Profile 契约

## 患者输入

工作簿第一张表第 1 行为标题，第 2 行支持以下两种固定列契约，顺序必须一致。

### 标准 18 列月度患者源表

`序号、患者唯一标识、姓名、激活日期、性别、年龄、联系电话、所属地区、疾病、既往过敏史、AI用药提醒次数、AI随访次数、症状自评完成次数、患教内容阅读次数、AI服务使用概况、本月是否发生不良反应（AE）、AE严重程度分级、患者标签`

### 13 列用药提醒表

`序号、患者唯一标识、姓名、性别、年龄、疾病、既往过敏史、联合用药、用药方案确认时间、用药方案、用药周期、方案链接、本月是否发生不良反应（AE）`

13 列格式的 `inputFormat` 为 `medicationReminder13`。它没有激活日期，`用药方案确认时间` 是唯一的确认时间来源，必须非空且可解析；提取结果保留 `sourceConfirmationTime` 和 `confirmationTime`，并将 `activateTime` 置为空。不得读取或解析该表已有的 `联合用药`、`用药方案` 来补造临床药物事实。

`患者唯一标识` 作为 userid。空值或重复值直接停止；不要修复、补齐、转号或去重。

18 列格式的 `inputFormat` 为 `monthlyPatient18`。该格式按激活日期计算同月、且晚于激活时间的确认时间；13 列格式则直接复用源确认时间。两种格式都必须将确认时间限制在 06:00:00–21:59:59，并在最终工作簿中与 payload 保持一致。

## Product Profile

每次产品都应新建 JSON，不能把某个示例药物硬编码为通用规则：

```json
{
  "schemaVersion": 2,
  "productType": "用药",
  "productName": "产品规范名称",
  "evidence": [
    {"title": "药品说明书/监管信息", "url": "https://...", "scope": "规格、用法、禁忌"}
  ],
  "baseMedication": {
    "drugName": "产品规范名称",
    "displayName": "产品规范名称(已核实商品名，可选)",
    "specification": "规格",
    "singleDose": "每次用量",
    "route": "给药途径",
    "frequency": "每日2次",
    "medicationTime": "早、晚餐后",
    "treatmentDays": 30,
    "precautions": "个体化注意事项",
    "ageDoseRules": [{"ageMin": 65, "singleDose": "说明书支持的老年剂量"}],
    "femalePrecautions": "妊娠或哺乳期需告知医师",
    "malePrecautions": ""
  },
  "directProductAdjuncts": [
    {
      "drugName": "与产品直接绑定的复溶液",
      "specification": "规格",
      "singleDose": "每次用量",
      "route": "仅用于复溶",
      "frequency": "每日1次",
      "medicationTime": "固定时间",
      "treatmentDays": 7,
      "precautions": "仅与当前产品配套使用",
      "role": "directProductAdjunct",
      "rationale": "产品说明书要求使用该复溶液"
    }
  ],
  "diseasePlans": [
    {
      "id": "某疾病联合用药方案",
      "when": {"diseaseContainsAny": ["疾病关键词"]},
      "evidence": [
        {"title": "某疾病诊疗指南", "url": "https://...", "scope": "本疾病的候选联合用药"}
      ],
      "allowProductOnly": false,
      "medicationGroups": [
        {
          "id": "有直接依据的疾病用药组",
          "when": {"ageMin": 18},
          "required": false,
          "alternatives": [
            {
              "drugName": "首选药",
              "displayName": "首选药(已核实商品名，可选)",
              "specification": "规格",
              "singleDose": "每次用量",
              "route": "口服",
              "frequency": "每日1次",
              "medicationTime": "晚间",
              "treatmentDays": 30,
              "precautions": "仅在医师确认本疾病指征后启用",
              "role": "diseaseTreatment",
              "diseaseRationale": "该药用于当前 diseasePlan 对应疾病的治疗或风险管理",
              "evidence": [{"title": "疾病用药依据", "url": "https://...", "scope": "该药与当前疾病的关联"}],
              "avoidIfAllergyContains": ["相关过敏关键词"]
            }
          ]
        }
      ]
    }
  ],
  "surgeryRules": [],
  "globalNotes": ["需经医师或药师审核，不作疗效承诺"]
}
```

schema v2 不得包含顶层 `baseCompanions` 或 `conditionalGroups`。疾病治疗药必须放在对应 `diseasePlan.medicationGroups`中。

每个 `diseasePlan.when` 必须包含 `diseaseEqualsAny` 或 `diseaseContainsAny`，每位患者必须且只能匹配一个疾病方案。无匹配或多匹配直接停止生成。

`allowProductOnly` 必须显式填写布尔值，用于 schema v2 兼容和器械流程判断。疾病方案未设置 `minimumCombinedMedicationCount` 和 `minimumDiseaseMedicationCount` 时，用药流程默认分别为 3 和 2。只有产品说明书或直接相关指南支持时，方案才可以声明较低的数值，并提供非空 `medicationCountRationale`。例如，单药方案可使用 `1/0`，双药方案可使用 `2/1`。直接产品辅助品不计入疾病治疗药数量；实际数量不足对应方案门槛时停止生成。

不同疾病可以在分别配置疾病方案和独立依据的前提下使用相同候选药，但最终完全相同的用药方案跨疾病只计 1 种。用药方案去重目标为 `ceil(患者数/100)`，即每增加 100 条记录增加 1 组，属于推荐优先级而非必须条件；记录数量越大，推荐目标越高。每个疾病方案应优先配置足够的同疾病、同治疗角色候选药；同一药品有多种说明书或直接相关指南支持的给药方案时，可使用 `regimenVariants` 配置每种变体的规格、剂量、途径、频次、时段、疗程、注意事项和药品依据。生成器按输入顺序在通过过敏/禁忌筛选的候选组合和变体间确定性轮换。去重以药品、规格、剂量、频次、时段和疗程的完整给药方案计算；候选组合不足时继续生成并记录实际值与目标差额，不得用无关药品凑数。

`when` 可使用：`diseaseEqualsAny`、`diseaseContainsAny`、`genderAny`、`ageMin`、`ageMax`、`allergyContainsAny`、`allergyNotContainsAny`、`aeEqualsAny`。同一对象中的条件为 AND，数组内部为 OR。

每个候选药可使用 `avoidIfAllergyContains`，用于成分、药物类别或已知交叉过敏关系；复杂交叉过敏不得仅由药名猜测，必须在 profile 明确配置。脚本还会检查药名（去除常见剂型后）是否直接命中过敏史，例如“阿司匹林过敏”会排除“阿司匹林肠溶片”。当前产品、直接产品辅助品、疾病治疗药和自动检索补充药均须通过患者级过敏筛选；最终输出前再次检查全部待输出药物。候选药冲突时按顺序选择有疾病依据的安全替代药；当前产品或直接产品辅助品冲突，或任一药物在最终输出前仍冲突时，停止生成并指出 userid、既往过敏史和冲突药名，要求补充安全替代方案或人工审核。没有安全替代且 `required=false` 时跳过，不得随意补药。

器械 profile 的 `surgeryRules` 结构：

```json
[{"when": {"diseaseContainsAny": ["疾病"]}, "surgeryName": "规范手术名称"}]
```

## Payload

`records` 中每个元素严格为：

```json
{
  "userid": "原始userid",
  "combinedMedication": ["当前产品", "疾病治疗药1", "疾病治疗药2"],
  "prescriptionList": "药品1 ... + 药品2 ...",
  "surgeryName": ""
}
```

用药清单 payload 每行字段为：`userid、drugName、displayName、specification、singleDose、frequency、medicationTime、treatmentDays、precautions`。`displayName` 只允许使用 profile 中显式配置的非空字符串；未配置时生成器回退为 `drugName`，不得自行猜测商品名。工作簿逐药明细仍按既有列输出，不新增展示名称列。

`combinedMedication` 按实际生成顺序列出全部 `drugName`，有几种就显示几种。`patients[].medicationPlan` 按相同顺序列出全部“展示名称+每次用量”，使用中文顿号 `、` 连接，有几种就显示几种，例如：`双歧杆菌四联活菌片(思连康)1.0g、蒙脱石散3g、口服补液盐I5.125g、消旋卡多曲颗粒30mg`。

用药方案字段不得包含“用药草案：”、性别、年龄、疾病、过敏史、审核说明或注意事项等长文本。安全与审核内容继续保留在逐药 `precautions` 和 `records[].prescriptionList`，不得因简化展示字段而删除。

用药 payload 的 `meta` 必须包含兼容默认值 `minimumCombinedMedicationCount: 3`、`minimumDiseaseMedicationCount: 2`、`minimumUniqueMedicationPlanCount`、`uniqueMedicationPlanCount` 和 `diseaseMedicationNamesByUserid`。生成器还必须写入 `minimumCombinedMedicationCountByUserid` 、`minimumDiseaseMedicationCountByUserid` 和 `medicationCountRationaleByUserid`，以记录每位患者所匹配方案的实际门槛和降低门槛依据。构建器和最终验证器必须使用这些患者级值；映射缺失时回退到 3/2 兼容默认。其中去重目标按 `ceil(患者数/100)` 计算，仅作为推荐优先级；去重依据为药品、规格、剂量、频次、时段和疗程的完整给药方案。`meta` 还应记录 `uniqueMedicationPlanPriority`、`uniqueMedicationPlanTargetMet` 和 `uniqueMedicationPlanShortfall`。构建器和最终验证器必须重算实际去重数并校验元数据一致性，但不得因未达成推荐目标而失败。`diseaseMedicationNamesByUserid` 逐 userid 记录从当前患者唯一 `diseasePlan.medicationGroups` 选出的药名；复溶液、稀释液等直接产品辅助品不计入该映射。药品产品必须位于 `combinedMedication` 首项，且必须满足当前患者方案的最低疾病治疗药数，不得用无关药品补足。

每个 `diseasePlan` 可选声明 `minimumCombinedMedicationCount` 和 `minimumDiseaseMedicationCount`，二者必须满足 `minimumCombinedMedicationCount >= 1 + minimumDiseaseMedicationCount`。任一值低于默认值 3/2 时，必须提供非空 `medicationCountRationale`。

当安全筛选后某个匹配疾病方案的疾病治疗药为 0 种时，生成器默认自动检索候选药；设置 `AUTO_MEDICATION_SEARCH=0` 可关闭。检索器只抓取 `nmpa.gov.cn`、`nhc.gov.cn`、`gov.cn`、`cma.org.cn`、`csu.org.cn` 等白名单来源页，不把搜索摘要、营销页或论坛作为依据。每个自动候选必须提供完整 `specification`、`singleDose`、`route`、`frequency`、`medicationTime` 和正整数 `treatmentDays`；候选字段不完整时仅记录在 `searchAudit` 并停止。`meta.searchAudit` 至少记录疾病方案、查询、来源 URL/标题、状态、候选数和错误信息；检索不能读取 13 列输入中的旧联合用药或用药方案文本。

`diseasePlan.medicationGroups[].alternatives[]` 中的每个疾病治疗候选药必须声明 `role: "diseaseTreatment"`、非空 `diseaseRationale`（疾病关联理由）和非空 `evidence`（药品依据）。生成器拒绝缺少这些字段的候选药，也拒绝把 `directProductAdjunct` 角色的复溶液或稀释液放入疾病治疗药组。

## 最终输出

- `用药提醒_<产品名称>.xlsx`：每个 userid 一行。
- `用药方案_<产品名称>.xlsx`：每个 userid 每个联合药一行。
- 验证文件和预览只留在任务工作目录，不交付给用户，除非用户要求。

## 不良反应清单契约

触发文案：`生成不良反应清单 依据文件：/absolute/path/月度患者清单.xlsx 产品：产品名称 服务周期：2026-08-01 至 2026-08-15`。`产品` 为必填规范名称，`服务周期` 必填；该工作流不要求产品类型。

### 服务周期与发生时间

- 将服务周期映射为生成脚本的必填参数 `--service-start YYYY-MM-DD` 和 `--service-end YYYY-MM-DD`。缺失时要求用户补充，不得根据激活日期或当前日期自动推断；非法日期或开始日晚于结束日时停止生成。
- `meta.servicePeriod` 必须包含 `{ "start": "2026-08-01", "end": "2026-08-15" }` 形式的日期字符串。北京时间开始日 `00:00:00` 和结束日 `23:59:59` 均包含在服务周期内，允许同一天及跨月周期。
- 每位目标患者的 `occurrenceTime` 必须严格晚于 `activateTime`，且处于服务周期内每天 `07:30:00` 至 `21:59:59` 的窗口。使用 userid 哈希在所有可用日期窗口的整秒闭区间内确定性选择时间；激活当日从激活时间之后第一个整秒开始，其他日期从 `07:30:00` 开始。
- 目标患者激活时间缺失、无效，或激活后在服务周期内没有可用整秒时停止生成，明确指出 userid 和原因；无可用时间时同时列出激活时间和服务周期。不得遗漏目标患者、改写激活时间或生成周期外时间。13列提醒表缺少患者标签和激活时间，不能用确认时间代替；要求补充18列源表。
- 构建器与独立验证器均校验合法日期、周期顺序、每日时间窗口及每条发生时间；验证器重新读取工作簿发生时间，核对与 payload 一致。校验报告使用 `occurrenceTimesFollowActivation`、`occurrenceTimesWithinServicePeriod` 和 `servicePeriod`，不再报告旧的时间先后规则。

### 筛选范围

- 只输出患者标签严格等于 `轻度患者`、`中度患者` 或 `重度患者` 的患者。
- 其他标签患者不输出；筛选后保持原始输入顺序。
- userid 必须逐字符保留，不新增、遗漏、改写、补齐、转号或去重。

### Payload records

每个 `records` 元素至少包含以下六个非空字段：

```json
{
  "userid": "原始userid",
  "symptomDescription": "结合患者资料和产品名称生成的观察性症状描述",
  "severityGrade": "中度（2级）",
  "treatmentMeasures": "供人工审核的处理措施建议",
  "treatmentOutcome": "待随访核实的处理结果/转归",
  "remark": "结合患者资料和产品名称生成的复核提示"
}
```

payload 的 `meta.productName` 保存用户提供的产品名称。每条记录同时包含工作簿字段：`disease`、`occurrenceTime`、`discoveryMethod`、`medicationRelationship`、`manualIntervention`、`followupRecord`。

- `轻度患者` 映射为 `轻度（1级）` 和人工干预 `否`。
- `中度患者` 映射为 `中度（2级）` 和人工干预 `否`。
- `重度患者` 映射为 `重度（3级）` 和人工干预 `是`。
- `discoveryMethod` 只能为 `AI用药随访发现` 或 `患者自评反馈`。
- `occurrenceTime` 必须严格晚于对应患者 `activateTime`，并位于 `meta.servicePeriod` 指定的服务周期内。
- `followupRecord` 默认空字符串。
- severityGrade 是供人工审核的建议，不是最终系统等级。

### 不良反应工作簿

使用 `assets/adverse-reaction-template.xlsx`，保留13列表头：`序号、患者ID、疾病、不良反应发生时间、发现途径、不良反应症状描述、不良反应严重程度分级、与用药关系分析、处理措施、处理结果/转归、是否触发人工干预、关联随访记录、备注`。清除模板示例数据后按筛选结果写入；输出只包含目标标签患者。

症状描述和与用药关系分析必须包含 `meta.productName`，但不得将产品与症状写成确定性因果关系。处理措施根据症状描述生成；处理结果/转归综合症状描述、关系分析和处理措施生成，并在缺少事实时保持待随访核实。不得虚构剂量、检查结果、确诊或已经发生的好转/痊愈，不得添加“结构化草案：”“人工审核草案：”等固定前缀。
