---
name: generating-monthly-patient-medication-workbooks
description: Use this skill whenever a user asks “生成月度患者清单” or provides a monthly patient Excel plus 依据文件、产品类型、产品名称 and wants individualized 联合用药、处方清单、器械手术方案、用药提醒 or 用药方案 workbooks. It preserves every userid exactly, derives clinically supported medication combinations from disease, sex, age and allergy history, authors from the bundled templates, and verifies the final Excel files.
---

# 生成月度患者用药清单

把月度患者基础数据转换为可审计的“用药提醒”和“用药方案”工作簿。以确定性脚本处理 userid、模板和校验；以经核对的产品说明书和诊疗依据制定本次产品规则。

**REQUIRED SUB-SKILL:** Use `spreadsheets:Spreadsheets` for workbook authoring and visual verification.

## 解析请求

从用户文案提取三个参数：

- `依据文件`：输入 `.xlsx` 的绝对路径。
- `产品类型`：仅接受 `用药` 或 `器械`。
- `产品名称`：保留用户提供的规范名称，不自行替换。

典型触发：`生成月度患者清单 依据文件：/path/月度患者清单.xlsx 产品类型：用药 产品名称：血栓通胶囊`。

输入、输出及 profile 契约见 [references/input-output-contract.md](references/input-output-contract.md)。临床生成边界见 [references/clinical-generation-rules.md](references/clinical-generation-rules.md)，每次生成前必须阅读全文。

## 执行流程

1. 在可写的任务目录中工作，绝不改写输入文件。使用 `scripts/extract_patients.py` 读取患者表：

   ```bash
   python scripts/extract_patients.py --source INPUT.xlsx --output patients.json
   ```

2. 查看 `patients.json` 的疾病、年龄、性别、过敏史和 AE 分布。核对当前产品的药品说明书/监管信息及每个疾病直接相关的指南，建立 `schemaVersion: 2` 的 `product-profile.json`。不要从示例产品复制药物。
3. profile 中把当前药品设为 `baseMedication`；仅把复溶液等与产品直接绑定的辅助品放入 `directProductAdjuncts`。按输入中的疾病分别建立 `diseasePlans`，每个方案都要有疾病条件、独立依据、`allowProductOnly` 和 `medicationGroups`。每位患者必须且只能匹配一个 `diseasePlan`。
4. 若 `产品类型=器械`，先在 profile 中按疾病建立规范 `surgeryRules`，再配置围手术期用药；无法形成可靠手术方案时停止并说明，不得猜测。
5. 生成 payload：

   ```bash
   python scripts/generate_payload.py \
     --patients patients.json --profile product-profile.json --output payload.json
   ```

6. 使用内置模板生成工作簿。运行时把工作区依赖提供的 `node_modules` 路径放入 `CODEX_NODE_MODULES`：

   ```bash
   CODEX_NODE_MODULES=... node scripts/build_workbooks.mjs \
     --payload payload.json \
     --reminder-template assets/medication-reminder-template.xlsx \
     --medication-template assets/medication-list-template.xlsx \
     --output-dir OUTPUT_DIR
   ```

7. 对脚本返回的两个工作簿运行 `scripts/verify_workbooks.mjs`。检查首段、中段、末段预览；任何 userid、药物映射、频次、时间、疗程或公式错误都必须修复后重跑。
8. 仅在全部校验通过后，把两个最终 `.xlsx` 复制到用户期望的目录。默认输出到输入文件同级目录，文件名分别为 `用药提醒_<产品名称>.xlsx` 和 `用药方案_<产品名称>.xlsx`；若已存在则附加时间戳，不覆盖。

## 不可放宽的规则

- 必须覆盖全部输入 userid，且不得新增、遗漏、改写或重排 userid。
- 每条生成记录只有 `userid`、`combinedMedication`、`prescriptionList`、`surgeryName` 四个键。
- 用药产品的 `combinedMedication` 首项必须是产品名称，`surgeryName` 必须是空字符串。
- `prescriptionList` 与用药清单中的药名及顺序必须和 `combinedMedication` 完全一致，不得出现清单外药物。
- `frequency` 统一为 `每日N次`；`medicationTime` 只写时间点/时段，不含口服、注射、滴注等途径；`treatmentDays` 为正整数。
- 结合疾病、性别、年龄、既往过敏史；对禁忌或过敏不安全的候选药选择有依据的替代药，否则跳过该联合药并标记需临床复核。
- 联合用药是针对当前患者疾病可候选联用的药品，不是表单中所有疾病的通用组合。不得在 schema v2 中使用 `baseCompanions` 或顶层 `conditionalGroups` 绕过疾病匹配。
- 不同疾病可以在各自独立依据支持下生成相同药品组合，但必须分别建立 `diseasePlan`；不得为制造差异而任意换药。
- 不得强制填充联合用药；联合用药数量只由当前疾病依据、安全条件和显式单药规则决定。
- 疾病方案未生成联合药时，只有显式设置 `allowProductOnly: true` 才能继续。
- 所有方案均注明需医师/药师审核，不作疗效承诺。
