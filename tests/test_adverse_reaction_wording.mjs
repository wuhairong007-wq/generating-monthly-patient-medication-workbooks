import assert from "node:assert/strict";
import test from "node:test";

import {
  productNameCandidates,
  validateAdverseReactionWording,
} from "../scripts/adverse_reaction_wording.mjs";

function record(overrides = {}) {
  return {
    userid: "U001",
    severityGrade: "轻度",
    symptomDescription: "患者反馈出现短暂头晕，建议记录持续时间。",
    medicationRelationship: "上述表现与用药时间可能存在先后关联，现有信息不足以确认因果关系。",
    treatmentMeasures: "建议记录症状变化，必要时联系医师或药师评估。",
    ...overrides,
  };
}

test("轻度患者三个目标字段拒绝人工核验措辞", () => {
  for (const [field, value] of [
    ["symptomDescription", "具体情况需人工核实。"],
    ["medicationRelationship", "因果关系需人工确认。"],
    ["treatmentMeasures", "建议人工复核当前用药。"],
  ]) {
    assert.throws(
      () => validateAdverseReactionWording(record({ [field]: value }), "注射用胰蛋白酶"),
      /轻度患者/,
    );
  }
});

test("中度患者保留风险相称的医师评估建议", () => {
  assert.doesNotThrow(() => validateAdverseReactionWording(record({
    severityGrade: "中度",
    treatmentMeasures: "建议联系医师评估症状及当前用药。",
  }), "注射用胰蛋白酶"));
});

test("关系分析拒绝正式产品名、简称、空格变体和产品代词", () => {
  for (const medicationRelationship of [
    "上述表现与注射用胰蛋白酶可能有关。",
    "上述表现与胰蛋白酶可能有关。",
    "上述表现与注射用 胰蛋白酶可能有关。",
    "上述表现与该产品可能有关。",
  ]) {
    assert.throws(
      () => validateAdverseReactionWording(record({ medicationRelationship }), "注射用胰蛋白酶"),
      /推广产品/,
    );
  }
});

test("关系分析拒绝括号中的商品名和去剂型简称", () => {
  const candidates = productNameCandidates("双歧杆菌四联活菌片(思连康)");
  assert.ok(candidates.includes("思连康"));
  assert.ok(candidates.includes("双歧杆菌四联活菌"));
  for (const medicationRelationship of [
    "思连康使用后可能存在时间关联。",
    "双歧杆菌四联活菌相关性尚不能确认。",
  ]) {
    assert.throws(
      () => validateAdverseReactionWording(record({ medicationRelationship }), "双歧杆菌四联活菌片(思连康)"),
      /推广产品/,
    );
  }
});

test("中性关系分析通过校验", () => {
  assert.doesNotThrow(() => validateAdverseReactionWording(record(), "注射用胰蛋白酶"));
});

test("全部严重程度和可见文案字段拒绝待核对等核验占位语", () => {
  for (const severityGrade of ["轻度", "中度", "重度"]) {
    for (const field of [
      "symptomDescription", "medicationRelationship", "treatmentMeasures",
      "treatmentOutcome", "remark",
    ]) {
      for (const value of [
        "症状待核对。", "具体情况需核对。", "待随访核实。",
        "发生频次尚待确认。", "持续时间尚不明确。",
        "当前资料未提供处理后转归。", "请复核症状是否真实发生。",
      ]) {
        assert.throws(
          () => validateAdverseReactionWording(record({ severityGrade, [field]: value }), "血栓通胶囊"),
          /核验占位文案/,
          `${severityGrade} ${field}: ${value}`,
        );
      }
    }
  }
});

test("直接观察和后续随访安排不伪造转归并保留因果审慎判断", () => {
  assert.doesNotThrow(() => validateAdverseReactionWording(record({
    symptomDescription: "症状观察重点为头晕及伴随乏力，记录发生频次和持续时间。",
    medicationRelationship: "上述表现与用药时间可能存在先后关联，不能据此确认因果关系。",
    treatmentMeasures: "记录症状变化；持续或加重时联系医师或药师评估。",
    treatmentOutcome: "后续随访记录头晕、乏力的变化和处理后转归。",
    remark: "轻度分级依据患者标签，不构成诊断或处方调整结论。",
  }), "血栓通胶囊"));
});
