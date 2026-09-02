import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]


class SkillContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.contract = (SKILL_DIR / "references" / "input-output-contract.md").read_text(encoding="utf-8")
        cls.clinical_rules = (SKILL_DIR / "references" / "clinical-generation-rules.md").read_text(encoding="utf-8")
        cls.rules = (SKILL_DIR / "references" / "adverse-reaction-generation-rules.md").read_text(encoding="utf-8")
        cls.agent = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

    def test_description_triggers_adverse_reaction_workflow(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertIn("生成不良反应清单", frontmatter)

    def test_skill_declares_semantic_version(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertIn('version: "1.5.0"', frontmatter)

    def test_documents_automatic_zero_candidate_search_safety(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("AUTO_MEDICATION_SEARCH=0", document)
            self.assertIn("searchAudit", document)
            self.assertIn("搜索摘要", document)
            self.assertIn("白名单", document)
            self.assertIn("字段不完整", document)

    def test_documents_both_patient_input_formats(self):
        for document in [self.skill, self.contract]:
            self.assertIn("monthlyPatient18", document)
            self.assertIn("medicationReminder13", document)
            self.assertIn("sourceConfirmationTime", document)
        self.assertIn("不从旧 `联合用药` 或 `用药方案` 文本反推临床事实", self.skill)
        self.assertIn("不得读取或解析该表已有的 `联合用药`、`用药方案`", self.contract)

    def test_documents_patient_count_scaled_plan_diversity(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("min(患者数, max(10, ceil(sqrt(患者数))))", document)
            self.assertIn("数量越大", document)
            self.assertIn("确定性轮换", document)
            self.assertIn("候选组合不足", document)
            self.assertIn("停止生成", document)
            self.assertIn("不得用无关药品凑数", document)

    def test_documents_concise_medication_plan_field(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("展示名称+每次用量", document)
            self.assertIn("有几种就显示几种", document)
            self.assertIn("displayName", document)
            self.assertIn("drugName", document)
            self.assertIn("不得自行猜测商品名", document)
            self.assertIn("用药方案字段不得包含“用药草案：”", document)
            self.assertIn("prescriptionList", document)

    def test_monthly_medication_rules_require_three_disease_related_medications(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("至少 3 种", document)
            self.assertIn("至少 2 种疾病治疗药", document)
            self.assertIn("直接产品辅助品不计入", document)
        for obsolete_rule in ["单药合理时保留单药", "不得强制填充联合用药", "联合用药数量只由"]:
            self.assertNotIn(obsolete_rule, self.skill)
            self.assertNotIn(obsolete_rule, self.clinical_rules)

    def test_skill_documents_failure_instead_of_unrelated_medication_filling(self):
        for expected in ["停止生成", "不得用无关药品凑数", "过敏", "疾病依据"]:
            self.assertIn(expected, self.skill)

    def test_disease_candidates_require_structured_linkage_evidence(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("diseaseTreatment", document)
            self.assertIn("疾病关联理由", document)
            self.assertIn("药品依据", document)

    def test_adverse_reaction_trigger_requires_product(self):
        self.assertIn("产品：", self.skill)
        self.assertIn("产品：", self.contract)
        self.assertIn("产品：", self.agent)
        self.assertNotIn("不要求产品类型或产品名称", self.skill)
        self.assertNotIn("不要求产品类型或产品名称", self.contract)

    def test_rules_do_not_force_draft_prefixes(self):
        self.assertNotIn("备注必须标注“人工审核草案”", self.rules)
        self.assertIn("不得添加固定", self.rules)

    def test_skill_references_all_adverse_reaction_resources(self):
        for expected in [
            "references/adverse-reaction-generation-rules.md",
            "scripts/generate_adverse_reactions.py",
            "scripts/build_adverse_reaction_workbook.mjs",
            "scripts/verify_adverse_reaction_workbook.mjs",
            "assets/adverse-reaction-template.xlsx",
        ]:
            self.assertIn(expected, self.skill)

    def test_contract_contains_required_fields_and_filtered_coverage_rule(self):
        for field in [
            "userid",
            "symptomDescription",
            "severityGrade",
            "treatmentMeasures",
            "treatmentOutcome",
            "remark",
        ]:
            self.assertIn(field, self.contract)
        self.assertIn("只输出", self.contract)
        self.assertIn("中度患者", self.contract)
        self.assertIn("重度患者", self.contract)

    def test_adverse_reaction_rules_require_age_disease_and_diversity(self):
        for expected in ["实际年龄", "年龄段", "主要症状", "伴随表现", "userid"]:
            self.assertIn(expected, self.rules)
        self.assertIn("重复率", self.rules)
        self.assertIn("实际年龄", self.skill)
        self.assertIn("重复率", self.skill)

    def test_agent_metadata_mentions_adverse_reaction_workbook(self):
        self.assertIn("不良反应", self.agent)


if __name__ == "__main__":
    unittest.main()
