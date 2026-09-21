import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


SKILL_DIR = Path(__file__).resolve().parents[1]


class SkillContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.contract = (SKILL_DIR / "references" / "input-output-contract.md").read_text(encoding="utf-8")
        cls.clinical_rules = (SKILL_DIR / "references" / "clinical-generation-rules.md").read_text(encoding="utf-8")
        cls.rules = (SKILL_DIR / "references" / "adverse-reaction-generation-rules.md").read_text(encoding="utf-8")
        cls.interview_workflow = (SKILL_DIR / "references" / "patient-interview-workflow.md").read_text(encoding="utf-8")
        cls.interview_contract = (SKILL_DIR / "references" / "deep-interview-template-contract.md").read_text(encoding="utf-8")
        cls.agent = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

    def test_description_triggers_adverse_reaction_workflow(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertIn("生成不良反应清单", frontmatter)

    def test_skill_declares_semantic_version(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertIn('version: "1.22.0"', frontmatter)

    def test_documents_source_metadata_input_and_output_columns(self):
        for document in [self.skill, self.contract]:
            for expected in ["用户类型", "来源任务ID", "来源月份", "medicationReminder16", "medicationReminder18"]:
                self.assertIn(expected, document)
            self.assertIn("用药提醒固定输出 18 列", document)
            self.assertIn("用药方案固定输出 13 列", document)
            self.assertIn("空值保持为空", document)

    def test_interview_records_title_and_overview_exclude_product_name(self):
        for document in [self.skill, self.interview_workflow, self.interview_contract]:
            self.assertIn("主标题固定为“患者访谈记录明细”", document)
            self.assertIn("调研对象概述", document)
            self.assertIn("不得包含产品名称", document)
            self.assertIn("本次调研访谈14位发生中度不良反应的患者", document)
        self.assertIn("<产品>_患者访谈记录明细_<YYYY-MM>", self.interview_workflow)
        self.assertIn("<产品>_患者访谈记录明细_<YYYY-MM>", self.interview_contract)

        template = SKILL_DIR / "assets" / "patient-interview-records-template.docx"
        with ZipFile(template) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = [
            "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
            for paragraph in root.findall(".//w:body/w:p", namespace)
        ]
        paragraphs = [text for text in paragraphs if text]
        self.assertEqual(paragraphs[0], "患者访谈记录明细")
        overview_index = paragraphs.index("一、调研对象概述")
        overview = paragraphs[overview_index + 1]
        self.assertNotIn("腔内连发施夹器", overview)
        self.assertNotIn("均使用了", overview)

    def test_documents_special_company_consumable_rules(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("公司：", document)
            self.assertIn("companyName", document)
            self.assertIn("商联医药(河南)有限公司（器械）", document)
            self.assertIn("耗材名称", document)
            self.assertIn("处方清单不能包含当前产品名称", document)

    def test_documents_normal_patient_tag_compatibility(self):
        for document in [self.skill, self.contract]:
            self.assertIn("患者标签", document)
            self.assertIn("正常", document)
            self.assertIn("兼容旧值", document)

    def test_adverse_reactions_require_service_period_and_follow_activation(self):
        for document in [self.skill, self.contract, self.rules]:
            self.assertIn("服务周期", document)
            self.assertIn("严格晚于", document)
            self.assertIn("--service-start", document)
            self.assertIn("--service-end", document)
            self.assertIn("07:30:00", document)
            self.assertIn("12:00:00", document)
            self.assertIn("加1天", document)
            self.assertIn("加2天", document)
            self.assertIn("11:59:59", document)
            self.assertIn("21:59:59", document)
            self.assertIn("occurrenceTimesMatchActivationPeriodRule", document)
            self.assertIn("停止生成", document)
            self.assertNotIn("早于激活时间", document)
            self.assertNotIn("小于激活时间", document)
        self.assertIn("服务周期：", self.agent)

    def test_documents_patient_level_allergy_screening_for_every_output_drug(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("当前产品", document)
            self.assertIn("直接产品辅助品", document)
            self.assertIn("最终输出前", document)
            self.assertIn("停止生成", document)

    def test_documents_automatic_zero_candidate_search_safety(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("AUTO_MEDICATION_SEARCH=0", document)
            self.assertIn("searchAudit", document)
            self.assertIn("搜索摘要", document)
            self.assertIn("白名单", document)
            self.assertIn("字段不完整", document)

    def test_documents_supported_patient_input_formats(self):
        for document in [self.skill, self.contract]:
            self.assertIn("monthlyPatient18", document)
            self.assertIn("medicationReminder13", document)
            self.assertIn("medicationReminder14", document)
            self.assertIn("medicationReminder15", document)
            self.assertIn("sourceConfirmationTime", document)
            self.assertIn(
                "不从旧 `手术名称`、`耗材名称`、`联合用药` 或 `用药方案` 文本反推临床事实",
                self.skill,
            )
            self.assertIn(
                "不得读取或解析旧 `手术名称`、`耗材名称`、`联合用药`、`用药方案`",
                self.contract,
            )

    def test_documents_patient_count_scaled_plan_diversity(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("ceil(患者数/100)", document)
            self.assertIn("数量越大", document)
            self.assertIn("确定性轮换", document)
            self.assertIn("候选组合不足", document)
            self.assertIn("regimenVariants", document)
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

    def test_monthly_medication_rules_document_evidenced_plan_minimums(self):
        for document in [self.skill, self.contract, self.clinical_rules]:
            self.assertIn("minimumCombinedMedicationCount", document)
            self.assertIn("minimumDiseaseMedicationCount", document)
            self.assertIn("medicationCountRationale", document)
            self.assertIn("默认", document)
            self.assertIn("直接产品辅助品不计入", document)
            self.assertIn("不得用无关药品凑数", document)
        self.assertIn("念珠菌性阴道炎", self.skill)
        self.assertIn("单药或双药", self.clinical_rules)

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
        self.assertIn("轻度患者", self.contract)
        self.assertIn("中度患者", self.contract)
        self.assertIn("重度患者", self.contract)

    def test_adverse_reaction_rules_require_age_disease_and_diversity(self):
        for expected in ["实际年龄", "年龄段", "主要症状", "伴随表现", "userid"]:
            self.assertIn(expected, self.rules)
        self.assertIn("重复率", self.rules)
        self.assertIn("实际年龄", self.skill)
        self.assertIn("重复率", self.skill)

    def test_adverse_reaction_symptoms_exclude_current_product_information(self):
        for document in [self.skill, self.contract, self.rules]:
            self.assertIn("症状描述不得包含当前产品信息", document)
            self.assertNotIn("症状描述和关系分析必须包含当前产品名称", document)
            self.assertNotIn("症状描述必须包含产品名称", document)

    def test_agent_metadata_mentions_adverse_reaction_workbook(self):
        self.assertIn("不良反应", self.agent)


if __name__ == "__main__":
    unittest.main()
