# 输入、输出和产品 Profile 契约

## 患者输入

工作簿第一张表第 1 行为标题，第 2 行必须包含以下 18 列，顺序一致：

`序号、患者唯一标识、姓名、激活日期、性别、年龄、联系电话、所属地区、疾病、既往过敏史、AI用药提醒次数、AI随访次数、症状自评完成次数、患教内容阅读次数、AI服务使用概况、本月是否发生不良反应（AE）、AE严重程度分级、患者标签`

`患者唯一标识` 作为 userid。空值或重复值直接停止；不要修复、补齐、转号或去重。

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
              "specification": "规格",
              "singleDose": "每次用量",
              "route": "口服",
              "frequency": "每日1次",
              "medicationTime": "晚间",
              "treatmentDays": 30,
              "precautions": "仅在医师确认本疾病指征后启用",
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

`allowProductOnly` 必须显式填写布尔值。如未选出任何疾病方案用药，只有该值为 `true` 时允许生成当前产品单药方案。

不同疾病可以在分别配置疾病方案和独立依据的前提下生成相同药品组合；不得为制造差异而任意换药。

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
  "combinedMedication": ["药品1", "药品2"],
  "prescriptionList": "药品1 ... + 药品2 ...",
  "surgeryName": ""
}
```

用药清单每行字段为：`userid、drugName、specification、singleDose、frequency、medicationTime、treatmentDays、precautions`。

## 最终输出

- `用药提醒_<产品名称>.xlsx`：每个 userid 一行。
- `用药方案_<产品名称>.xlsx`：每个 userid 每个联合药一行。
- 验证文件和预览只留在任务工作目录，不交付给用户，除非用户要求。
