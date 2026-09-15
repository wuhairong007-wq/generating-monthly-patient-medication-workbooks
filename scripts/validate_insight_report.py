#!/usr/bin/env python3
"""Validate structural and source-reconciliation requirements for insight reports."""
import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
REPORT_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "patient-insight-report-generation-prompt-template.md.docx"


def validate_report(docx_path, insight_path):
    errors = []
    if not REPORT_TEMPLATE.is_file():
        errors.append("缺少洞察报告固定提示词模板资产")
    insight = json.loads(Path(insight_path).read_text(encoding="utf-8"))
    monthly = insight.get("metadata", {}).get("inputMode") == "monthly"
    with ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        root = etree.fromstring(zf.read("word/document.xml"))
        text = "".join(root.xpath("//w:t/text()", namespaces=NS))
        paras = ["".join(p.xpath(".//w:t/text()", namespaces=NS)).strip() for p in root.xpath("//w:p", namespaces=NS)]

        if not insight.get("metrics", {}).get("adverseEvents", {}).get("provided", True):
            event_assertions = r"(?:不良反应[\d,]+例|不良反应涉及患者[\d,]+人|患者发生率为[\d.]+%|(?:低|中|高)风险[\d,]+人|未记录不良反应的患者为[\d,]+人)"
            statistic_labels = {"不良反应发生率", "患者发生率", "不良反应记录", "不良反应监测", "风险等级"}
            if re.search(event_assertions, text) or statistic_labels.intersection(paras):
                errors.append("不良反应清单选填模式不得输出事件统计或风险分层结论")
            if any(re.match(r"^图\d+-\d+：(?:不良反应严重程度分布|患者风险分层分布)", p) for p in paras):
                errors.append("不良反应清单选填模式不得输出事件或风险图表")

        # The cover is front matter and must carry the request-specific metadata.
        metadata = insight.get("metadata", {})
        period = metadata.get("period", {})
        compact_period = f"{period.get('start', '').replace('-', '')}-{period.get('end', '').replace('-', '')}"
        cover_values = {
            "委托方（甲方）：": metadata.get("client", ""),
            "服务商（乙方）：": metadata.get("provider", ""),
            "产品：": metadata.get("product", ""),
            "服务地区：": metadata.get("serviceRegion", ""),
            "服务周期：": compact_period,
            "报告日期：": metadata.get("reportDate", ""),
        }
        tables_in_doc = root.xpath("//w:tbl", namespaces=NS)
        cover_text = "".join("".join(cell.xpath(".//w:t/text()", namespaces=NS)) for table in tables_in_doc[:1] for cell in table.xpath("./w:tr/w:tc", namespaces=NS)) if tables_in_doc else ""
        if "患者洞察报告" not in text or not tables_in_doc:
            errors.append("缺少患者洞察报告封面或封面表格")
        for label, value in cover_values.items():
            if label not in cover_text:
                errors.append(f"封面缺少字段：{label}")
            elif value and value not in cover_text:
                errors.append(f"封面字段未与insight.json对账：{label}")

        toc_fields = root.xpath("//w:fldSimple[contains(translate(@w:instr, 'toc', 'TOC'), 'TOC')]", namespaces=NS)
        toc_instr_text = root.xpath("//w:instrText[contains(translate(text(), 'toc', 'TOC'), 'TOC')]/text()", namespaces=NS)
        if not toc_fields and not toc_instr_text:
            errors.append("缺少动态目录字段")

        if "图表说明：" in text:
            errors.append("正文不得包含图表说明段")

        page_field_found = False
        footer_names = [name for name in names if name.startswith("word/footer") and name.endswith(".xml")]
        for footer_name in footer_names:
            footer_root = etree.fromstring(zf.read(footer_name))
            if footer_root.xpath("//w:fldSimple[contains(translate(@w:instr, 'page', 'PAGE'), 'PAGE')]", namespaces=NS) or footer_root.xpath("//w:instrText[contains(translate(text(), 'page', 'PAGE'), 'PAGE')]/text()", namespaces=NS):
                page_field_found = True
                break
        if not page_field_found:
            errors.append("正文缺少PAGE页码字段")
        page_starts = root.xpath("//w:sectPr/w:pgNumType[@w:start='1']", namespaces=NS)
        if not page_starts:
            errors.append("正文页码未从1开始")

        expected = [f"{x}、" for x in "一二三四五六七八九"]
        top = [p for p in paras if re.match(r"^[一二三四五六七八九]、[^、]+$", p)]
        if len(top) != 9 or [p[:2] for p in top] != expected:
            errors.append("一级标题必须按一、至九、连续出现")
        expected_headings = [
            "一、报告概述", "（一）执行摘要", "（二）关键指标概览",
            "二、患者基本特征分析", "（一）性别分布", "（二）年龄分布", "（三）性别×年龄交叉", "（四）地区分布", "（五）疾病分型", "（六）过敏史",
            "三、AI用药提醒服务分析", "（一）服务覆盖", "（二）用药方案分析", "（三）联合用药分析", "（四）联合用药模式深度分析",
            "四、AI智能随访服务分析", "（一）随访概况", "（二）用药依从性 Q1-Q2",
            "1、维度1：症状改善情况（Q1）", "2、维度2：注射部位反应（Q2）",
            "（三）症状改善 Q3-Q5", "3、维度3：睡眠状态（Q3）", "4、维度4：消化系统反应（Q4）", "5、维度5：疗程完成度（Q5）",
            "（四）生活质量与满意度 Q7-Q9", "7、维度7：体温监测（Q7）", "8、维度8：满意度评价（Q8）", "9、维度9：注意事项知晓度（Q9）",
            "（五）后续用药意愿 Q10", "10、维度10：继续治疗意愿（Q10）",
            "五、AI症状自评服务分析", "（一）症状自评概况", "（二）六维度详细分析", "（三）按疾病分型评分分析",
            "六、不良反应监测与分析", "（一）不良反应概况", "（二）不良反应特征总结",
            "七、患者风险评估", "（一）风险分级概况",
            "八、服务质量与SLA达标分析", "（一）AI服务覆盖率", "（二）各模块按疾病覆盖率", "（三）各模块按年龄覆盖率", "九、总结",
        ]
        if monthly:
            expected_headings = [
                "一、报告概述", "（一）执行摘要", "（二）关键指标概览",
                "二、患者基本特征分析", "（一）性别分布", "（二）年龄分布", "（三）地区分布", "（四）疾病分型", "（五）过敏史", "（六）性别与年龄交叉",
                "三、AI用药提醒服务分析", "（一）提醒次数与统计月份", "（二）用药方案登记与周期", "（三）登记药名与组合",
                "四、AI智能随访服务分析", "（一）随访概况", "（二）实际随访题目与回答",
                "五、AI症状自评服务分析", "（一）自评概况与有效答卷", "（二）实际六维度评分", "（三）按疾病分型评分分析",
                "六、不良反应监测与分析", "（一）事件登记概况", "七、患者风险评估", "（一）服务复核优先级",
                "八、服务质量与SLA达标分析", "（一）模块覆盖与合同边界", "（二）疾病与年龄分组覆盖", "（三）源资料核验", "九、总结",
            ]
            unsupported = r"(?:健康管理方案覆盖率?|(?:估算)?响应率|体温监测(?:次数)?|血压心率监测(?:次数)?)[：:为达约共计\s]*[\d,.]+[%％次]?"
            if re.search(unsupported, text):
                errors.append("月度资料不得补造健康方案、响应率或生命体征监测统计")
            for q in insight["metrics"]["followups"]["questions"]:
                if not any(p.endswith(q["question"]) for p in paras):
                    errors.append("未使用源表实际随访题目：" + q["question"])
            for q in insight["metrics"]["symptoms"]["questions"]:
                if q not in paras:
                    errors.append("未使用源表实际自评题目：" + q)
            rows = [["".join(cell.xpath(".//w:t/text()", namespaces=NS)) for cell in row.xpath("./w:tc", namespaces=NS)] for row in root.xpath("//w:tbl/w:tr", namespaces=NS)]
            measures = insight['metrics']
            expected_values = {'用药提醒总数': f"{measures['serviceExecution']['medicationReminders']:,}次" if measures['serviceExecution']['medicationReminders'] is not None else '无法统计'}
            for label, key in [('用药方案登记覆盖', 'reminderPlanCoverage'), ('智能随访覆盖', 'followupCoverage'), ('症状自评覆盖', 'symptomCoverage')]:
                value = measures[key]
                expected_values[label] = f"{value['numerator']:,}/{value['denominator']:,}（{value['value']:.1%}）"
            for label, value in expected_values.items():
                found = [row[1] for row in rows if len(row) > 1 and row[0] == label]
                if not found or any(actual != value for actual in found):
                    errors.append("月度指标未与insight.json对账：" + label)
            if not measures['monthlySummary']['matchesPeriod'] and '不计入本期' not in text:
                errors.append("未说明源表月份不匹配的统计边界")
        actual_headings = [p for p in paras if p in expected_headings or re.match(r"^[一二三四五六七八九]、", p) or re.match(r"^（[一二三四]）", p) or re.match(r"^\d+、维度", p)]
        actual_relevant = [p for p in actual_headings if p in expected_headings]
        if actual_relevant != expected_headings:
            missing = [h for h in expected_headings if h not in actual_relevant]
            errors.append("模板目录标题缺失或顺序不一致" + (f"：{missing[0]}" if missing else ""))
        figures = [(int(m.group(1)), int(m.group(2))) for p in paras if (m := re.match(r"^图(\d+)-(\d+)：", p))]
        tables = [(int(m.group(1)), int(m.group(2))) for p in paras if (m := re.match(r"^表(\d+)-(\d+)：", p))]
        def continuous(items):
            by_section = {}
            for section, number in items:
                by_section.setdefault(section, []).append(number)
            return bool(items) and all(values == list(range(1, len(values) + 1)) for values in by_section.values())
        if not continuous(figures):
            errors.append("图注编号不连续或缺失")
        if not continuous(tables):
            errors.append("表注编号不连续或缺失")
        media = [n for n in names if n.startswith("word/media/")]
        drawings = root.xpath("//w:drawing", namespaces=NS)
        if not media or len(drawings) < len(figures):
            errors.append("图表媒体或图片关系数量不足")
        forbidden_template_text = [
            "237名患者", "福建省9个地级市", "6809次", "提示词正文",
            "将【】内参数替换为当次任务实际内容", "本内容由 Coze AI 生成",
        ]
        if any(value in text for value in forbidden_template_text):
            errors.append("残留模板示例文本或数值")
        patient_count = insight["metadata"]["patientCount"]
        if f"{patient_count:,}人" not in text:
            errors.append("患者总数未与insight.json对账")
        total_prompts = insight["metrics"]["serviceExecution"]["totalPrompts"]
        if total_prompts is not None and f"{total_prompts:,}次" not in text:
            errors.append("提醒总数未与insight.json对账")
        blue_headers = root.xpath("//w:tbl/w:tr[1]//w:shd[@w:fill='1F4E78']", namespaces=NS)
        if len(blue_headers) < len(tables):
            errors.append("存在未使用蓝色底纹的表头")
        body_paras = root.xpath("//w:p[not(ancestor::w:tbl) and .//w:t]", namespaces=NS)
        narrative_texts = [
            "".join(p.xpath(".//w:t/text()", namespaces=NS)).strip()
            for p in body_paras
        ]
        substantial_narratives = [p for p in narrative_texts if len(p) >= 40]
        if monthly:
            # Fewer sources require different subsections; require analysis in every chapter,
            # instead of padding with legacy health-plan/response metrics.
            chapter_sizes = []
            current_size = 0
            in_chapter = False
            for p in narrative_texts:
                if re.match(r"^[一二三四五六七八九]、[^、]+$", p):
                    if in_chapter: chapter_sizes.append(current_size)
                    in_chapter, current_size = True, 0
                elif in_chapter and len(p) >= 40:
                    current_size += 1
            if in_chapter: chapter_sizes.append(current_size)
            if len(chapter_sizes) != 9 or min(chapter_sizes, default=0) < 2 or len(substantial_narratives) < 30:
                errors.append("月度九章缺少完整的数据解读、统计边界与服务动作")
        elif len(substantial_narratives) < 110 or sum(map(len, substantial_narratives)) < 11500:
            errors.append("正文分析密度不足，需按数据陈述、结构解读和服务动作扩充")
        exact_28 = 0
        for p in body_paras:
            if p.xpath("./w:pPr/w:spacing[@w:line='560' and @w:lineRule='exact']", namespaces=NS):
                exact_28 += 1
        if exact_28 < 20:
            errors.append("正文固定28磅行距覆盖不足")

        def heading_uses_font_and_size(heading, east_asia_font, half_points):
            accepted_fonts = {"宋体": "Songti SC", "黑体": "Heiti SC"}.get(east_asia_font, east_asia_font)
            matches = [p for p in root.xpath("//w:p", namespaces=NS) if "".join(p.xpath(".//w:t/text()", namespaces=NS)).strip() == heading]
            return bool(matches) and all(
                p.xpath(f".//w:rPr/w:rFonts[@w:eastAsia='{east_asia_font}' or @w:eastAsia='{accepted_fonts}']", namespaces=NS)
                and p.xpath(f".//w:rPr/w:sz[@w:val='{half_points}']", namespaces=NS)
                for p in matches
            )

        for heading in [p for p in expected_headings if re.match(r"^[一二三四五六七八九]、", p)]:
            if not heading_uses_font_and_size(heading, "黑体", "32"):
                errors.append("一级标题未使用黑体16pt格式")
                break
        for heading in [p for p in expected_headings if p.startswith("（")]:
            if not heading_uses_font_and_size(heading, "黑体", "28"):
                errors.append("二级标题未使用黑体14pt格式")
                break
    return errors


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--docx", required=True); parser.add_argument("--insight", required=True); args = parser.parse_args()
    errors = validate_report(args.docx, args.insight)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
