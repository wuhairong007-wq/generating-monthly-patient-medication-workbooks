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

`allowProductOnly` 必须显式填写布尔值，用于 schema v2 兼容和器械流程判断。在 `产品类型=用药` 时，该字段不能放宽最小数量规则：每位患者的 `combinedMedication` 至少 3 种，且必须从其唯一匹配的疾病方案中选出至少 2 种疾病治疗药。直接产品辅助品不计入疾病治疗药数量；不足时停止生成。

不同疾病可以在分别配置疾病方案和独立依据的前提下使用相同候选药，但最终完全相同的用药方案跨疾病只计 1 种。用药方案最低去重数为 `min(患者数, max(10, ceil(sqrt(患者数))))`，因此患者数量越大，最低去重数越多。每个疾病方案应配置足够的同疾病、同治疗角色候选药，生成器按输入顺序在通过过敏/禁忌筛选的候选组合间确定性轮换。候选组合不足时停止生成并报告实际值和目标值，不得用无关药品凑数。

`when` 可使用：`diseaseEqualsAny`、`diseaseContainsAny`、`genderAny`、`ageMin`、`ageMax`、`allergyContainsAny`、`allergyNotContainsAny`、`aeEqualsAny`。同一对象中的条件为 AND，数组内部为 OR。

每个候选药可使用 `avoidIfAllergyContains`。脚本按顺序选择第一种对当前过敏史安全的方案；没有安全替代且 `required=false` 时跳过，不得随意补药。

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

用药 payload 的 `meta` 必须包含 `minimumCombinedMedicationCount: 3`、`minimumDiseaseMedicationCount: 2`、`minimumUniqueMedicationPlanCount`、`uniqueMedicationPlanCount` 和 `diseaseMedicationNamesByUserid`。其中最低去重数按 `min(患者数, max(10, ceil(sqrt(患者数))))` 计算；构建器和最终验证器必须重算实际去重数并与元数据及最低目标比较。`diseaseMedicationNamesByUserid` 逐 userid 记录从当前患者唯一 `diseasePlan.medicationGroups` 选出的药名；复溶液、稀释液等直接产品辅助品不计入该映射。药品产品必须位于 `combinedMedication` 首项，至少 2 种疾病治疗药必须有当前疾病的独立依据并通过患者过敏/禁忌筛选。

`diseasePlan.medicationGroups[].alternatives[]` 中的每个疾病治疗候选药必须声明 `role: "diseaseTreatment"`、非空 `diseaseRationale`（疾病关联理由）和非空 `evidence`（药品依据）。生成器拒绝缺少这些字段的候选药，也拒绝把 `directProductAdjunct` 角色的复溶液或稀释液放入疾病治疗药组。

## 最终输出

- `用药提醒_<产品名称>.xlsx`：每个 userid 一行。
- `用药方案_<产品名称>.xlsx`：每个 userid 每个联合药一行。
- 验证文件和预览只留在任务工作目录，不交付给用户，除非用户要求。

## 不良反应清单契约

触发文案：`生成不良反应清单 依据文件：/absolute/path/月度患者清单.xlsx 产品：产品名称`。`产品` 为必填规范名称；该工作流不要求产品类型。

### 筛选范围

- 只输出患者标签严格等于 `中度患者` 或 `重度患者` 的患者。
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

- `中度患者` 映射为 `中度（2级）` 和人工干预 `否`。
- `重度患者` 映射为 `重度（3级）` 和人工干预 `是`。
- `discoveryMethod` 只能为 `AI用药随访发现` 或 `患者自评反馈`。
- `occurrenceTime` 必须严格早于对应患者 `activateTime`。
- `followupRecord` 默认空字符串。
- severityGrade 是供人工审核的建议，不是最终系统等级。

### 不良反应工作簿

使用 `assets/adverse-reaction-template.xlsx`，保留13列表头：`序号、患者ID、疾病、不良反应发生时间、发现途径、不良反应症状描述、不良反应严重程度分级、与用药关系分析、处理措施、处理结果/转归、是否触发人工干预、关联随访记录、备注`。清除模板示例数据后按筛选结果写入；输出只包含目标标签患者。

症状描述和与用药关系分析必须包含 `meta.productName`，但不得将产品与症状写成确定性因果关系。处理措施根据症状描述生成；处理结果/转归综合症状描述、关系分析和处理措施生成，并在缺少事实时保持待随访核实。不得虚构剂量、检查结果、确诊或已经发生的好转/痊愈，不得添加“结构化草案：”“人工审核草案：”等固定前缀。
