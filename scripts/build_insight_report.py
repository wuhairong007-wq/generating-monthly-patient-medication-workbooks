#!/usr/bin/env python3
"""Build a data-driven patient insight report using the bundled report contract."""
import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


DEFAULT_REPORT_RULE_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "patient-insight-report-generation-prompt-template.md.docx"


def _set_cell_shading(cell, fill="1F4E78"):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_borders(cell, color="D9D9D9"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        node = borders.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:color"), color)


def _set_run(run, font="宋体", size=12, bold=False, color="000000"):
    # Use installed macOS CJK family names so LibreOffice previews do not
    # substitute missing glyph boxes for the Word-facing Chinese names.
    render_font = {"宋体": "Songti SC", "黑体": "Heiti SC"}.get(font, font)
    run.font.name = render_font
    run._element.rPr.rFonts.set(qn("w:ascii"), render_font)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), render_font)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), render_font)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = __import__("docx").shared.RGBColor.from_string(color)


def _format_paragraph(paragraph, size=12, font="宋体", bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, first_line=True, line=28, before=0, after=0):
    paragraph.alignment = align
    fmt = paragraph.paragraph_format
    fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY if line == 28 else WD_LINE_SPACING.SINGLE
    fmt.line_spacing = Pt(line)
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.first_line_indent = Pt(size * 2) if first_line else Cm(0)
    for run in paragraph.runs:
        _set_run(run, font, size, bold)


def _clear_body(document):
    body = document._element.body
    sect = body.sectPr
    for child in list(body):
        if child is not sect:
            body.remove(child)


def _configure_default_page(document):
    """Use a predictable A4 page when the caller does not provide a template."""
    for section in document.sections:
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)


def _add_para(doc, text, **kwargs):
    p = doc.add_paragraph(text)
    _format_paragraph(p, **kwargs)
    return p


def _add_heading(doc, text, level):
    p = doc.add_paragraph(text)
    p.style = f"Heading {level}"
    if level == 1:
        _format_paragraph(p, size=16, font="黑体", bold=True, first_line=False, before=14, after=14)
    elif level == 2:
        _format_paragraph(p, size=14, font="黑体", bold=True, first_line=False)
    else:
        _format_paragraph(p, size=14, font="黑体", bold=False, first_line=True)
    return p


def _add_field(paragraph, instruction, placeholder=""):
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), instruction)
    run = OxmlElement("w:r")
    if placeholder:
        for index, line in enumerate(str(placeholder).splitlines()):
            if index:
                run.append(OxmlElement("w:br"))
            text = OxmlElement("w:t")
            text.text = line
            run.append(text)
    field.append(run)
    paragraph._p.append(field)


def _set_update_fields(document):
    settings = document.settings._element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")


def _clear_footer(section):
    footer = section.footer
    for paragraph in footer.paragraphs:
        paragraph._element.getparent().remove(paragraph._element)


def _add_page_number(section):
    section.footer.is_linked_to_previous = False
    _clear_footer(section)
    paragraph = section.footer.add_paragraph()
    _format_paragraph(paragraph, size=9, font="宋体", align=WD_ALIGN_PARAGRAPH.CENTER, first_line=False, line=12)
    _add_field(paragraph, "PAGE")
    pg_num = section._sectPr.find(qn("w:pgNumType"))
    if pg_num is None:
        pg_num = OxmlElement("w:pgNumType")
        section._sectPr.append(pg_num)
    pg_num.set(qn("w:start"), "1")


def _add_cover(doc, metadata):
    title = _add_para(doc, "患者洞察报告", size=24, font="黑体", bold=True, first_line=False, line=32,
                      align=WD_ALIGN_PARAGRAPH.CENTER, before=165, after=70)
    title.paragraph_format.keep_with_next = True
    period = metadata.get("period", {})
    start, end = period.get("start", ""), period.get("end", "")
    compact_period = f"{start.replace('-', '')}-{end.replace('-', '')}" if start and end else ""
    report_date = metadata.get("reportDate") or f"{date.today().year}年{date.today().month}月"
    rows = [
        ("委托方（甲方）：", metadata.get("client", "")),
        ("服务商（乙方）：", metadata.get("provider", "")),
        ("产品：", metadata.get("product", "")),
        ("服务地区：", metadata.get("serviceRegion", "")),
        ("服务周期：", compact_period),
        ("报告日期：", report_date),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.autofit = False
    for row, (label, value) in zip(table.rows, rows):
        row.cells[0].width = Cm(5.0)
        row.cells[1].width = Cm(9.0)
        for idx, cell in enumerate(row.cells):
            cell.text = label if idx == 0 else value
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_borders(cell, "B7C9D6")
            for paragraph in cell.paragraphs:
                _format_paragraph(paragraph, size=11, font="宋体", bold=idx == 0,
                                  align=WD_ALIGN_PARAGRAPH.CENTER, first_line=False, line=16)
    doc.add_page_break()


def _add_toc(doc, entries):
    p = _add_para(doc, "目录", size=18, font="黑体", bold=True, first_line=False, line=28,
                  align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=18)
    p.paragraph_format.keep_with_next = True
    toc = doc.add_paragraph()
    _format_paragraph(toc, size=11, font="宋体", first_line=False, line=20, before=0, after=0)
    # Keep a cached readable result for renderers that do not recalculate TOC
    # fields; Word still owns the dynamic field and refreshes page numbers.
    _add_field(toc, 'TOC \\o "1-3" \\h \\z \\u', "\n".join(entries))
    doc.add_section(WD_SECTION.NEW_PAGE)


def _add_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = True
    for i, value in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = str(value)
        _set_cell_shading(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_borders(cell)
        for p in cell.paragraphs:
            _format_paragraph(p, size=10, font="宋体", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, first_line=False, line=12)
            for run in p.runs:
                _set_run(run, "宋体", 10, True, "FFFFFF")
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
            cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_borders(cells[i])
            for p in cells[i].paragraphs:
                _format_paragraph(p, size=10, font="宋体", align=WD_ALIGN_PARAGRAPH.CENTER, first_line=False, line=12)
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            mar = tc_pr.first_child_found_in("w:tcMar")
            if mar is None:
                mar = OxmlElement("w:tcMar"); tc_pr.append(mar)
            for edge in ("top", "start", "bottom", "end"):
                node = mar.find(qn("w:" + edge))
                if node is None: node = OxmlElement("w:" + edge); mar.append(node)
                node.set(qn("w:w"), "90"); node.set(qn("w:type"), "dxa")
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for cell in table.rows[-1].cells:
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.keep_with_next = True
    return table


def _add_caption(doc, prefix, index, name):
    p = doc.add_paragraph(f"{prefix}{index}：{name}")
    _format_paragraph(p, size=9, font="宋体", align=WD_ALIGN_PARAGRAPH.CENTER, first_line=False, line=12, before=3, after=8)
    return p


def _add_chart(doc, image_path, manifest_item, index):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.paragraph_format.first_line_indent = Cm(0)
    run = p.add_run()
    run.add_picture(str(image_path), width=Cm(15.5))
    _add_caption(doc, "图", index, f"{manifest_item['caption']}（{manifest_item['type']}）")


def build_report(insight_path, chart_manifest_path, template_path, output_path):
    if not DEFAULT_REPORT_RULE_TEMPLATE.is_file():
        raise FileNotFoundError(f"缺少洞察报告固定模板：{DEFAULT_REPORT_RULE_TEMPLATE}")
    insight = json.loads(Path(insight_path).read_text(encoding="utf-8"))
    if insight.get("metadata", {}).get("inputMode") == "monthly":
        from build_monthly_insight_report import build_monthly_report
        return build_monthly_report(insight, chart_manifest_path, template_path, output_path)
    manifest = json.loads(Path(chart_manifest_path).read_text(encoding="utf-8"))
    # A user template may supply page furniture, but the bundled contract always supplies report content.
    doc = Document(template_path) if template_path else Document()
    if not template_path:
        _configure_default_page(doc)
    _clear_body(doc)
    meta, m = insight["metadata"], insight["metrics"]
    product = meta["product"]
    adverse_events_provided = m["adverseEvents"].get("provided", True)
    for section in doc.sections:
        section.footer.is_linked_to_previous = False
        _clear_footer(section)
    _add_cover(doc, meta)
    toc_entries = [
        "一、报告概述", "（一）执行摘要", "（二）关键指标概览",
        "二、患者基本特征分析", "（一）性别分布", "（二）年龄分布", "（三）性别×年龄交叉", "（四）地区分布", "（五）疾病分型", "（六）过敏史",
        "三、AI用药提醒服务分析", "（一）服务覆盖", "（二）用药方案分析", "（三）联合用药分析", "（四）联合用药模式深度分析",
        "四、AI智能随访服务分析", "（一）随访概况", "（二）用药依从性 Q1-Q2", "（三）症状改善 Q3-Q5", "（四）生活质量与满意度 Q7-Q9", "（五）后续用药意愿 Q10",
        "五、AI症状自评服务分析", "（一）症状自评概况", "（二）六维度详细分析", "（三）按疾病分型评分分析",
        "六、不良反应监测与分析", "（一）不良反应概况", "（二）不良反应特征总结",
        "七、患者风险评估", "（一）风险分级概况", "八、服务质量与SLA达标分析", "九、总结",
    ]
    _add_toc(doc, toc_entries)
    # _add_toc creates the body section, so unlink and clear all newly-created
    # front-matter footers before adding the body PAGE field.
    for section in doc.sections[:-1]:
        section.footer.is_linked_to_previous = False
        _clear_footer(section)
    _add_page_number(doc.sections[-1])
    _set_update_fields(doc)
    period = meta["period"]
    chart_map = {item["id"]: item for item in manifest}
    current_section = 0
    fig_no = 0
    table_no = 0
    def table(headers, rows, name):
        nonlocal table_no
        table_no += 1
        _add_table(doc, headers, rows); _add_caption(doc, "表", f"{current_section}-{table_no}", name)
    def chart(chart_id):
        nonlocal fig_no
        item = chart_map.get(chart_id)
        if item:
            fig_no += 1
            _add_chart(doc, Path(chart_manifest_path).parent / item["file"], item, f"{current_section}-{fig_no}")
    def h1(t):
        nonlocal current_section, fig_no, table_no
        current_section += 1; fig_no = 0; table_no = 0
        _add_heading(doc, t, 1)
    def h2(t): _add_heading(doc, t, 2)
    def h3(t): _add_heading(doc, t, 3)
    def body(t): _add_para(doc, t)
    n = meta["patientCount"]
    def pct(value, denom):
        return f"{(value / denom * 100):.1f}%" if denom else "无记录"
    s = m["serviceExecution"]
    tracking_coverage = m.get("trackingCoverage", {"numerator": s.get("trackingPatients", 0), "value": (s.get("trackingPatients", 0) / n if n else 0), "display": pct(s.get("trackingPatients", 0), n)})

    h1("一、报告概述")
    h2("（一）执行摘要")
    body(f"本报告围绕{product}，分析{period['start']}至{period['end']}服务周期内的患者管理数据。合同目标为{meta['contractGoal']}本周期纳入患者{n:,}人，覆盖{meta['regionCount']}个地区和{meta['diseaseCount']}类疾病。报告中的比例均以对应实际分母计算，提醒响应率采用患者级响应率按提醒总次数加权估算。")
    body(f"服务执行方面，健康管理方案覆盖{m['healthPlanCoverage']['display']}，智能随访覆盖{m['followupCoverage']['display']}，症状自评覆盖{m['symptomCoverage']['display']}；累计推送各类提醒{s['totalPrompts']:,}次，记录智能随访{s['followupRecords']:,}条、症状自评{s['symptomRecords']:,}条。")
    body(f"从服务链路完整性看，方案生成覆盖{m['healthPlanCoverage']['display']}，提醒覆盖{tracking_coverage['display']}，随访和自评均能按患者ID回溯。随访覆盖与方案覆盖相差{(m['healthPlanCoverage']['value'] - m['followupCoverage']['value']) * 100:.1f}个百分点，症状自评覆盖与方案覆盖相差{(m['healthPlanCoverage']['value'] - m['symptomCoverage']['value']) * 100:.1f}个百分点，下一周期应优先关注未形成连续评估记录的患者。")
    body(f"从产品服务视角看，{product}在本周期形成了从方案生成、用药提醒到随访、自评和安全监测的模块组合。健康管理方案覆盖{m['healthPlanCoverage']['numerator']:,}人，跟踪提醒覆盖{tracking_coverage['numerator']:,}人；智能随访尚有{n - m['followupCoverage']['numerator']:,}名患者未覆盖，症状自评尚有{n - m['symptomCoverage']['numerator']:,}名患者未覆盖，后续应把覆盖缺口转化为可追踪的补访名单，而不是只看总体记录量。")
    body(f"本周期提醒总量达到{s['totalPrompts']:,}次，平均每名患者约{s['totalPrompts'] / n:.1f}次。该高频触达为疗程执行和异常发现提供了过程数据，但也需要结合患者响应情况控制重复触达，建议下一周期同时观察患者级覆盖、单人提醒次数和未响应连续天数，形成更细的服务质量判断。")
    body("因此，本报告对服务成效的判断分为三层：第一层看患者是否进入服务流程，第二层看提醒、随访和自评是否实际发生，第三层看异常是否被记录、处理并形成转归。三层指标的分母不同，不能用单一响应率替代全流程质量评价；后续运营复盘也应按这三个层次分别提出改进任务。")
    h2("（二）关键指标概览")
    body(f"本次指标以患者主表中的{n:,}个唯一患者ID作为总体范围，服务记录通过同一ID关联。解读任一百分比前，应先区分患者人数、服务记录条数和题目有效回答数：同一患者可以产生多次服务记录，但患者覆盖分子只计一次。复核时应从指标定位到对应患者及原始行，防止把重复记录误认为新增服务对象。")
    body("本报告按请求指定的开始日和结束日筛选有日期的随访、自评、用药确认和事件记录，两端日期均纳入。跟踪提醒汇总没有逐次发送日期时，次数仍按该表的汇总范围解释；交付复核应确认汇总表覆盖本次服务周期，不能仅因文件名称含有某个月份就断言每次服务均发生在周期内。")
    table(["指标", "数值", "统计口径"], [["服务患者", f"{n:,}人", "患者主表去重"], ["覆盖地区", f"{meta['regionCount']}个", "地区字段去重"], ["提醒总量", f"{s['totalPrompts']:,}次", "三类提醒次数合计"], ["估算响应率", s['estimatedResponseRate']['display'], s['responseRateBasis']]] + ([["不良反应发生率", m['adverseEventRate']['display'], "不良反应患者数/患者数"]] if adverse_events_provided else []), "关键指标概览")
    chart("service")

    h1("二、患者基本特征分析")
    body(f"本章基于{n:,}名患者的基本信息，从性别、年龄、性别与年龄交叉、地区、疾病分型和过敏史六个维度描述患者画像，用于识别重点服务区域、重点年龄层、病种结构与服务安全提示。")
    h2("（一）性别分布")
    body(f"性别分析的总体分母为{n:,}名患者，分布中的每一类别均按主表实际记录汇总。若仅出现一种性别或个别类别人数很少，本节仍可描述样本构成，但不具备组间效果比较条件。执行人员应先核对分类值和患者ID，再决定是否另行提取分组覆盖、响应和补访记录，不用人口学比例推定个体治疗需要。")
    sex = m["sexDistribution"]; body("性别分布为" + "、".join(f"{x['label']}{x['count']}人（{pct(x['count'], n)}）" for x in sex) + "。该结果用于服务人群描述，不作病因推断。")
    if len(sex) >= 2:
        body(f"按两类性别记录计算，{sex[0]['label']}与{sex[1]['label']}人数差为{abs(sex[0]['count']-sex[1]['count']):,}人，比例约为{sex[0]['count']/max(sex[1]['count'],1):.2f}:1。性别差异可用于检查提醒触达是否存在群体间响应差距，但当前汇总未提供分性别响应率，不能据此判断服务效果差异。")
        body(f"从服务配置角度看，两类患者均已纳入同一套方案、提醒和评估框架，当前最需要补充的是分性别的过程指标对照，例如方案确认率、提醒响应率、随访完成率和自评覆盖率。只有在分母一致、观察周期一致的前提下，才能判断是否需要调整触达时间、话术长度或人工跟进方式；本节人数结构本身不代表疾病风险或产品效果差异。")
        body("在实际执行中，性别结构更适合作为服务公平性检查的入口：先确认两类患者是否获得相近的服务机会，再观察响应和完成情况是否存在差异。若后续发现某一群体在连续未响应、随访缺失或自评缺失方面明显集中，应优先核查触达时间、设备使用和信息理解情况，再决定是否调整服务内容。")
    table(["性别", "患者数", "占比"], [[x["label"], x["count"], f"{x['count']/n*100:.1f}%"] for x in sex], "患者性别分布"); chart("sex")
    h2("（二）年龄分布")
    age = m["ageDistribution"]; body("年龄分组显示，" + "、".join(f"{x['label']}{x['count']}人（{pct(x['count'], n)}）" for x in age) + "。年龄结构可用于安排提醒时段和数字化服务内容。")
    young = sum(x['count'] for x in age[:2]); older = sum(x['count'] for x in age[-2:])
    body(f"前两个年龄组累计{young:,}人（{pct(young, n)}），后两个年龄组累计{older:,}人（{pct(older, n)}）。建议对高龄组增加大字号、分步骤的提醒内容，并对年轻组测试更灵活的触达时间；上述建议属于服务设计方向，不代表年龄与疗效存在因果关系。")
    if age:
        largest_age = max(age, key=lambda x: x['count'])
        body(f"当前人数最多的年龄组为{largest_age['label']}，共有{largest_age['count']:,}人，占{pct(largest_age['count'], n)}。年龄结构并非均匀分布，因此服务评估不宜只使用总体平均响应率；下一周期可将人数最多的年龄组作为基准组，再比较其他年龄组的提醒响应和随访覆盖，识别是触达方式还是服务参与度造成的差异。")
    body("年龄分布还提示服务内容需要同时兼顾信息可读性和操作效率。对年龄较大的患者，提醒应减少连续操作步骤，并在关键节点重复显示药品名称、时间和遗漏处理方式；对年轻患者，则可以测试更灵活的触达时段和移动端交互。上述调整应以分组后的响应、完成和补访数据验证，而不是根据年龄标签直接推定患者行为。")
    table(["年龄组", "患者数", "占比"], [[x["label"], x["count"], f"{x['count']/n*100:.1f}%"] for x in age], "患者年龄分组分布"); chart("age")
    h2("（三）性别×年龄交叉")
    body("交叉表中的每个单元格代表同时满足性别和年龄组条件的患者人数，不能把行列占比相加解释为新的覆盖率。对于人数较少的交叉组，应回到患者级记录核实服务完成情况，避免一个人的记录变动造成百分比大幅变化后被误读为趋势。对外展示时还应使用汇总结果，逐人复核名单保留在受控的工作资料中。")
    sex_age = m.get("sexAgeDistribution", [])
    body("性别与年龄交叉结果显示，患者结构并非只由单一人口学维度决定，服务资源应同时考虑不同性别在各年龄组中的人数集中区间。交叉分布为" + "、".join(f"{x['sex']}·{x['age']}{x['count']}人" for x in sex_age[:8]) + "。")
    if sex_age:
        largest_cross = max(sex_age, key=lambda x: x['count'])
        body(f"人数最多的交叉组为{largest_cross['sex']}、{largest_cross['age']}，共{largest_cross['count']:,}人，占患者总数{pct(largest_cross['count'], n)}。该结果只能说明服务人群构成，不能推断性别或年龄导致疾病差异；但可以作为提醒文案、触达时段和补访排班的分层入口。")
        body("下一周期建议在交叉组层面同时记录提醒响应、随访完成和症状自评覆盖，优先比较人数较多的交叉组，再对样本较小的组合采用描述性复核。若某一交叉组连续未响应或补访缺口集中，应先核查触达时点、设备使用和信息可读性，再决定是否调整服务策略。")
    table(["性别", "年龄组", "患者数", "占比"], [[x["sex"], x["age"], x["count"], f"{x['count']/n*100:.1f}%"] for x in sex_age], "性别与年龄交叉分布"); chart("sex-age")
    h2("（四）地区分布")
    body("地区统计以主表地区字段为归属依据，反映的是本次纳入患者的登记范围，不代表当地全部患者或产品使用人群。地区名称粒度不同、同一区域多种写法或跨地区就医都可能影响排序；下一步宜先核对地区编码和归属规则，再将相同层级地区进行比较，并保留归并前后的核验记录，不能直接外推市场份额或区域患病率。")
    region = m["regionDistribution"]; body("患者覆盖" + str(meta['regionCount']) + "个地区，数量较多的地区为" + "、".join(f"{x['label']}（{x['count']}人，{pct(x['count'], n)}）" for x in region[:5]) + "。地区差异可作为资源排班与服务触达优化的参考。")
    if region:
        body(f"首位地区与末位地区相差{region[0]['count'] - region[-1]['count']:,}人，前五地区合计{sum(x['count'] for x in region[:5]):,}人（{pct(sum(x['count'] for x in region[:5]), n)}）。建议将患者量较高地区作为运营监测样本，同时对低覆盖地区核查机构接入、患者入组和数据回传环节。")
        body(f"地区分布呈现长尾特征：前五地区只占全部患者的{pct(sum(x['count'] for x in region[:5]), n)}，其余{max(meta['regionCount'] - 5, 0)}个地区仍承担了主要服务覆盖之外的患者。资源安排上可采用‘重点地区固定运营节奏、长尾地区设置异常监测’的方式，重点核对低人数地区是否存在数据回传延迟、机构接入不足或服务启动时间不一致。")
        body("地区运营不应只按患者数量排序，还应结合每个地区的服务链完成情况。建议建立地区看板，至少同时展示患者数、健康管理方案覆盖、随访覆盖、症状自评覆盖、提醒响应和异常记录完整性；对患者量少但覆盖率异常低的地区，优先检查数据链路，对患者量高但响应率偏低的地区，优先调整触达策略。")
    table(["地区", "患者数", "占比"], [[x["label"], x["count"], f"{x['count']/n*100:.1f}%"] for x in region[:10]], "地区患者分布")
    h2("（五）疾病分型")
    disease = m["diseaseDistribution"]; body("疾病分型共" + str(meta['diseaseCount']) + "类，前五类为" + "、".join(f"{x['label']}（{x['count']}人，{pct(x['count'], n)}）" for x in disease[:5]) + "。疾病结构为产品服务内容和随访重点提供分层依据。")
    top3 = sum(x['count'] for x in disease[:3]); body(f"前3类疾病合计{top3:,}人（{pct(top3, n)}），说明服务资源可先围绕主要病种配置标准化教育与提醒模板，再为小众病种保留个体化补充字段。疾病分型统计反映服务构成，不替代临床诊断或适应症判断。")
    if disease:
        tail = n - top3
        body(f"除前三类疾病外，其余疾病合计{tail:,}人（{pct(tail, n)}），说明报告既需要关注主流病种的规模化执行，也不能用主流病种的服务表现代替全部病种的表现。建议在下一周期的随访和自评结果中增加疾病分型交叉表，分别查看覆盖率、回答结构和风险分层，避免小样本病种被总体均值掩盖。")
    body("疾病结构还决定了服务内容的优先级：主要病种可以使用标准化的用药提醒、疗程节点和随访问题，小样本病种则应保留人工审核入口和个体化备注字段。这样既能提高批量服务效率，也能避免把一个病种的提醒逻辑直接套用到其他疾病，尤其要在联合用药、监测项目和异常升级条件上保留差异化空间。")
    table(["疾病类型", "患者数", "占比"], [[x["label"], x["count"], f"{x['count']/n*100:.1f}%"] for x in disease], "疾病分型分布"); chart("disease")
    h2("（六）过敏史")
    body("过敏史分析属于安全信息的记录质量检查，过敏物质名称、反应描述和既往记录时间应在逐人复核中分别核对。空白、明确否认过敏和已登记过敏不能相互替代；总体分布也不能用于自动认定某个联合用药方案安全。下一步应把有待澄清的记录交由具备相应职责的人员核实，并保留更正依据与时间。")
    allergy = m.get("allergyDistribution", [])
    allergy_total = sum(x["count"] for x in allergy)
    body("既往过敏史记录用于提示用药提醒和人工复核时的安全边界。本周期过敏史分布为" + "、".join(f"{x['label']}{x['count']}人（{pct(x['count'], allergy_total)}）" for x in allergy) + "。过敏史字段反映记录状态，不等同于当前发生过敏反应。")
    known_allergy = allergy_total - next((x['count'] for x in allergy if x['label'] in {'无', '无记录'}), 0)
    body(f"有明确过敏史或非空记录的患者共{known_allergy:,}人，占{pct(known_allergy, n)}；对这部分患者，应在方案审核、用药提醒和不良反应复核中保持患者级关联，避免只在总体统计中稀释安全提示。")
    body("建议下一周期将过敏史作为提醒生成和人工升级的必核字段：先确认过敏物质、既往反应描述和当前用药是否存在需要复核的组合，再决定是否增加人工确认或补充说明。对于标记为‘无记录’的患者，应区分未发现过敏史与字段未填写，避免把数据缺失误判为安全状态。")
    table(["过敏史记录", "患者数", "占比"], [[x["label"], x["count"], f"{x['count']/n*100:.1f}%"] for x in allergy], "患者既往过敏史分布"); chart("allergy")

    h1("三、AI用药提醒服务分析")
    body(f"本章从服务覆盖、用药方案、联合用药和联合用药模式四个维度分析服务数据。服务周期内用药记录{s['medicationReminders']:,}条提醒对应的响应率按患者级响应率加权估算。")
    h2("（一）服务覆盖")
    body(f"用药提醒服务以跟踪提醒清单和用药清单为执行依据，本周期纳入跟踪提醒患者{tracking_coverage['numerator']:,}人，相关提醒总量{s['totalPrompts']:,}次，其中用药提醒{s['medicationReminders']:,}次、体温监测{s['temperatureMonitoring']:,}次、血压心率监测{s['vitalMonitoring']:,}次。")
    body(f"提醒响应率为{s['estimatedResponseRate']['display']}，统计口径为{s['responseRateBasis']}。该口径适合描述整体触达后的响应水平，但不能替代患者级连续未响应、提醒类型响应和疗程节点完成率；提醒次数多也不等同于用药依从性高。")
    body("服务覆盖评价应把‘是否进入提醒流程’与‘进入后是否完成响应’分开。下一周期建议按患者ID保留提醒类型、发送时间、响应时间、连续未响应次数和疗程节点，优先对已覆盖但连续未响应的患者补访，对未形成提醒记录的患者核查数据接入和激活状态。")
    service_rows = [["用药提醒", s['medicationReminders'], f"{s['medicationReminders']/s['totalPrompts']*100:.1f}%"], ["体温监测", s['temperatureMonitoring'], f"{s['temperatureMonitoring']/s['totalPrompts']*100:.1f}%"], ["血压心率监测", s['vitalMonitoring'], f"{s['vitalMonitoring']/s['totalPrompts']*100:.1f}%"]]
    table(["提醒类型", "推送次数", "占总量"], service_rows, "AI用药提醒服务覆盖与执行量"); chart("service")
    h2("（二）用药方案分析")
    body("本章用药明细按药品确认时间纳入观察范围，同一患者在周期内出现多条记录时，应结合药品名称、规格、频次和疗程区分重复登记、方案调整及不同治疗阶段。记录条数只能说明文档中存在相应条目，不能证明患者实际服药次数。核查产品覆盖或组合结构时，应同时保留患者ID和时间信息，避免把先后调整的方案误当作同时使用。")
    meds = m["medications"]; body(f"共记录用药{meds['recordCount']:,}条，涉及{meds['uniqueDrugCount']}种药品，患者人均{meds['averageDrugsPerPatient']:.2f}种。用药记录最多的药品为" + "、".join(f"{x['label']}（{x['count']}条，{pct(x['count'], meds['recordCount'])}）" for x in meds['drugDistribution'][:5]) + "。")
    body(f"核心产品记录{meds['drugDistribution'][0]['count'] if meds['drugDistribution'] else 0:,}条，占全部用药记录{pct(meds['drugDistribution'][0]['count'] if meds['drugDistribution'] else 0, meds['recordCount'])}；前10种药品合计{sum(x['count'] for x in meds['drugDistribution'][:10]):,}条，占{pct(sum(x['count'] for x in meds['drugDistribution'][:10]), meds['recordCount'])}。该集中度可用于识别标准化方案的主要组成，同时应继续核对长尾药品的适应症与规格记录。")
    if meds['productSpecificationDistribution']:
        spec_total = sum(x['count'] for x in meds['productSpecificationDistribution'])
        body("产品规格记录为" + "、".join(f"{x['label']}（{x['count']}条，{pct(x['count'], spec_total)}）" for x in meds['productSpecificationDistribution']) + "。规格分布可以帮助核对不同患者方案的记录完整性，但不能单独说明剂量选择的临床合理性；后续应将规格、疾病分型、疗程和风险标签放在同一张复核表中。")
    body(f"前10种药品之外的长尾记录为{max(meds['recordCount'] - sum(x['count'] for x in meds['drugDistribution'][:10]), 0):,}条，占{pct(max(meds['recordCount'] - sum(x['count'] for x in meds['drugDistribution'][:10]), 0), meds['recordCount'])}。长尾药品数量不大但更容易出现规格、频次或疗程填写不一致，建议将其作为处方字段完整性和药品提醒文案的抽查对象。")
    body("用药记录的集中度还可以转化为服务内容分层：核心产品和高频辅助药品适合形成固定提醒模板，低频药品适合采用药品名称、规格、频次和疗程逐条展示的个体化提醒。对同一患者存在多种药品时，应在提醒中明确先后顺序和时间点，避免患者只记住核心产品而忽略辅助治疗记录。")
    table(["药品名称", "用药记录数", "占比"], [[x["label"], x["count"], f"{x['count']/meds['recordCount']*100:.1f}%"] for x in meds['drugDistribution'][:10]], "TOP10药品用药记录")
    chart("medications")
    h2("（三）联合用药分析")
    body("患者级药品组合用于展示登记的治疗结构，不能凭组合人数判断药物间相互作用、适应证是否充分或是否需要停换药。对同一组合的后续复核，应先比较疾病、剂型、给药途径与治疗阶段，再核对原始处方和患者反馈；只有明确记录的临床事实才能支持个体化判断，统计上的高频组合不自动成为其他患者的推荐方案。")
    comb = meds['combinationCountDistribution']; body("联合用药品种数分布为" + "、".join(f"{x['label']}种（{x['count']}人，{pct(x['count'], n)}）" for x in comb) + "。该分布反映服务周期内记录的联合用药结构，不能单独推断临床疗效。")
    if comb:
        broad = sum(x['count'] for x in comb if int(float(x['label'])) >= 3); body(f"联合用药3种及以上患者{broad:,}人（{pct(broad, n)}），提示提醒内容需要同时覆盖核心产品、辅助药品和疗程节点；对于多药并用患者，应在提醒中明确药品名称、时间和遗漏处理方式，以降低执行歧义。")
        single_drug = next((x['count'] for x in comb if x['label'] == '1'), 0)
        multi_drug = n - single_drug
        body(f"联合用药2种及以上患者共{multi_drug:,}人，占比{pct(multi_drug, n)}；单药患者{single_drug:,}人。该结构说明服务设计需要同时覆盖单药和联合用药场景，并对多药并用患者增加时间间隔、重复用药核对和疗程结束提醒。")
    table(["联合用药品种数", "患者数", "占比"], [[x["label"], x["count"], f"{x['count']/n*100:.1f}%"] for x in comb], "联合用药品种数分布"); chart("combination-modes")
    h2("（四）联合用药模式深度分析")
    modes = meds.get("combinationModeDistribution", [])
    body("联合用药模式按患者实际药品组合归并，能够补充‘用了几种药’之外的组合结构信息。本周期主要模式为" + "、".join(f"{x['label']}（{x['count']}人，{pct(x['count'], n)}）" for x in modes[:8]) + "。该统计反映患者级记录组合，不用于判断组合疗效或因果关系。")
    if modes:
        top_mode = modes[0]
        body(f"人数最多的组合模式为{top_mode['label']}，涉及{top_mode['count']:,}人，占{pct(top_mode['count'], n)}；前五种模式合计{sum(x['count'] for x in modes[:5]):,}人，占{pct(sum(x['count'] for x in modes[:5]), n)}。组合越分散，越需要在提醒中逐条显示药品名称、规格、频次、时间和疗程，避免患者只记住核心产品。")
        body("下一周期建议把高频组合设为标准化提醒模板，把低频组合保留个体化字段，并对同一患者存在多种药品时增加先后顺序、间隔和重复用药核对。若某组合同时出现非正向随访回答、不良反应或连续未响应，应进入患者级复核清单，而不是仅按组合人数排序。")
    table(["联合用药模式", "患者数", "占比"], [[x['label'], x['count'], f"{x['count']/n*100:.1f}%"] for x in modes], "联合用药模式分布"); chart("combination-modes")

    h1("四、AI智能随访服务分析")
    h2("（一）随访概况")
    body("随访问卷汇总应保留原始题目、选项及每题实际有效回答数。某题空白不能算作正向回答，也不能仅因同一患者完成了一次随访就认定十题均完整；跨题比较前需检查跳题和无效值。服务人员可据此分别安排未完成整份问卷的补访和单题澄清，汇总结果不作为已经开展线下或电话访谈的证据。")
    body(f"本周期完成智能随访{s['followupRecords']:,}条，覆盖患者{m['followupCoverage']['display']}。问卷包含十个维度，数据用于观察症状、功能、用药体验和服务接受度。")
    body(f"随访覆盖率与健康管理方案覆盖率相差{(m['healthPlanCoverage']['value'] - m['followupCoverage']['value']) * 100:.1f}个百分点，说明已有基础方案的患者中仍有一部分尚未进入标准化问卷评估。随访记录数为{s['followupRecords']:,}，覆盖患者数为{m['followupCoverage']['numerator']:,}；本周期数据更适合解释为有效评估的完成情况，不能据此判断所有患者的持续随访频次。")
    body("从服务闭环看，随访结果应与前置的用药提醒和后置的症状自评进行患者级串联。下一周期可优先对未随访患者设置补访任务，对已随访但自评缺失的患者设置衔接提醒，并按疾病分型复核问卷完成率，减少‘有方案、无评估’的断点。")
    body("十个问题覆盖病灶变化、疼痛、活动限制、身体不适、功能恢复、炎症表现、睡眠、情绪、整体效果评价和推荐意愿等内容，能够从不同角度描述患者体验。由于各问题的选项含义不同，本报告统一采用A/B作为正向回答仅用于服务统计，解读时仍需回到每个问题的原始选项，不能把十个百分比直接当作同一种临床指标。")
    table(["指标", "数值"], [["随访记录", s['followupRecords']], ["随访覆盖率", m['followupCoverage']['display']], ["评估维度", "10个"]], "智能随访覆盖概况"); chart("followup")
    h2("（二）用药依从性 Q1-Q2")
    followup_titles = ["症状改善情况", "注射部位反应", "睡眠状态", "消化系统反应", "疗程完成度", "日常活动影响", "体温监测", "满意度评价", "注意事项知晓度", "继续治疗意愿"]
    for i, q in enumerate(m['followups']['questions'], 1):
        if i == 3:
            h2("（三）症状改善 Q3-Q5")
        elif i == 6:
            continue
        elif i == 7:
            h2("（四）生活质量与满意度 Q7-Q9")
        elif i == 10:
            h2("（五）后续用药意愿 Q10")
        title = followup_titles[i - 1] if i <= len(followup_titles) else f"随访问卷维度{i}"
        h3(f"{i}、维度{i}：{title}（Q{i}）")
        dist = q['distribution']; body(f"该维度有效回答{q['positiveRate']['denominator']}条，按A/B作为正向回答的比例为{q['positiveRate']['display']}。回答分布为" + "、".join(f"{x['label']}（{x['count']}条）" for x in dist) + "。")
        top_two = sum(x['count'] for x in dist[:2])
        body(f"该维度回答主要集中在前两项，共{top_two:,}条，占有效回答{pct(top_two, q['positiveRate']['denominator'])}；其余选项合计{q['positiveRate']['denominator'] - top_two:,}条。这个结构能够帮助服务团队区分‘整体回答稳定’与‘仍有少量边界人群’两种情况，后续应保留原始选项分布，避免只保留一个汇总比例。")
        non_positive = q['positiveRate']['denominator'] - q['positiveRate']['numerator']
        if non_positive:
            body(f"该维度有{non_positive}条非正向回答（{pct(non_positive, q['positiveRate']['denominator'])}），建议在下一轮随访中对非正向选项进行原因追问，并与患者的用药提醒响应、症状自评总分进行关联复核。")
        else:
            body("该维度未出现非正向回答，建议继续保持问题表述和触达节奏稳定，并关注后续周期是否出现结构性变化。")
        body(f"对该维度的后续管理可分为两类：对A/B回答维持常规随访节奏，重点观察后续回答是否发生变化；对其余{non_positive:,}条回答建立复核标记，核对同一患者是否同时存在提醒未响应、自评高分或不良反应记录。该分层用于确定服务优先级，不直接形成临床结论。")
        table(["回答选项", "次数", "占比"], [[x['label'], x['count'], f"{x['count']/q['positiveRate']['denominator']*100:.1f}%"] for x in dist], f"Q{i}随访回答分布")
    positives = [[f"Q{i+1}", q['positiveRate']['display'], q['positiveRate']['denominator']] for i, q in enumerate(m['followups']['questions'])]
    rates = [q['positiveRate']['value'] for q in m['followups']['questions'] if q['positiveRate']['value'] is not None]
    low_rate = min(rates) if rates else None; high_rate = max(rates) if rates else None
    body("十个维度的正向回答率均以有效回答数为分母计算。" + (f"本周期各维度正向率范围为{low_rate * 100:.1f}%至{high_rate * 100:.1f}%，最大差异为{(high_rate - low_rate) * 100:.1f}个百分点。" if rates else "") + "该汇总用于定位需要加强解释、提醒或复访的维度，不将问卷结果直接等同于临床结局。")
    body("质量评估建议优先关注正向率相对较低的维度和有效回答数偏少的维度，先核查样本量、问题理解和触达时点，再决定是否调整服务策略。")
    if rates:
        low_questions = [f"Q{i + 1}" for i, q in enumerate(m['followups']['questions']) if q['positiveRate']['value'] == low_rate]
        high_questions = [f"Q{i + 1}" for i, q in enumerate(m['followups']['questions']) if q['positiveRate']['value'] == high_rate]
        body(f"本周期相对较低的正向率出现在{'、'.join(low_questions)}，最高正向率出现在{'、'.join(high_questions)}。由于各维度有效回答数相同，差异主要来自少量非正向选项，建议下一周期保留这些边界回答的患者ID和原始选项，进行回访原因核实，而不是仅依据四舍五入后的百分比排序。")
        body(f"十个维度共形成{s['followupRecords'] * len(m['followups']['questions']):,}个有效回答单元，所有维度的分母均为{s['followupRecords']:,}。完整分母有利于横向比较，但高度集中的正向率也需要关注问卷选项设计、触达时点和重复回答模式；下一周期可以在不改变问题含义的前提下，增加回答耗时、跳题情况和复访一致性等质量指标。")
    table(["维度", "正向回答率", "有效回答数"], positives, "随访十维度关键指标汇总")
    chart("followup")

    h1("五、AI症状自评服务分析")
    h2("（一）症状自评概况")
    body("症状自评按六个维度均具有有效分值的答卷计算完整评分，单题均分与总分均值需要保留各自的有效答卷口径。复核时应检查选项到分值的映射是否一致，并区分缺答、超出范围的值和真实高分。对同一患者的多次答卷，可另建配对序列观察变化，但不能将不同患者、不同日期的总体均值差直接解释为个体症状改善。")
    body(f"本周期症状自评完成{s['symptomRecords']:,}条，有效六维度评分{m['symptoms']['validAssessments']:,}条，覆盖患者{m['symptomCoverage']['display']}。每个维度按1至5分记录，分数越高代表症状负担越重。")
    body(f"症状自评记录数高于覆盖患者数，说明部分患者在服务周期内进行了重复评估，平均每名已覆盖患者约{s['symptomRecords'] / m['symptomCoverage']['numerator']:.2f}次。重复评估为观察变化趋势提供了条件，但当前汇总数据尚未区分首次与复测，因此本报告主要描述总体分布，不把记录次数增加解释为症状改善或恶化。")
    body(f"仍有{n - m['symptomCoverage']['numerator']:,}名患者未形成自评覆盖。下一周期应区分‘从未完成自评’与‘已经完成但缺少复测’两类缺口：前者需要优化首次引导，后者需要根据疗程节点安排复测；两类患者的运营动作和评价分母不应混在一起。")
    h2("（二）六维度详细分析")
    rows = [[q, f"{v:.2f}" if v is not None else "无记录"] for q, v in zip(m['symptoms']['questions'], m['symptoms']['dimensionMeans'])]
    means = [v for v in m['symptoms']['dimensionMeans'] if v is not None]
    body("六维度均值范围为" + f"{min(means):.2f}至{max(means):.2f}分" + "，各维度均值见表。均值差异可用于确定下一轮随访的重点提问方向，但不能替代个体化临床评估。")
    if means:
        high_dim = rows[max(range(len(means)), key=lambda i: means[i])][0]
        low_dim = rows[min(range(len(means)), key=lambda i: means[i])][0]
        body(f"当前均值最高维度为“{high_dim}”，最低维度为“{low_dim}”，两者相差{max(means)-min(means):.2f}分。建议对高分维度设置复测提醒，对低分维度保持常规观察，并结合疾病分型判断是否存在结构性差异。")
        body(f"六个维度均值均接近量表低分端，最高均值也仅为{max(means):.2f}分；这一结果说明本周期自评记录的总体分布较集中，但不能单独推断产品疗效或病情改善。更稳妥的做法是把同一患者的首次与后续评分配对，观察变化方向，并把高分维度、随访非正向回答和提醒未响应记录一并纳入复核。")
    table(["评估维度", "均分"], rows, "症状自评六维度评分统计"); chart("symptoms")
    h2("（三）按疾病分型评分分析")
    bands = m['symptoms']['scoreBands']; valid_scores = m['symptoms']['validAssessments']; body("按疾病分型的症状自评评分用于识别不同病种的症状负担结构。本周期各病种有效评估与总分均值为" + "、".join(f"{x['label']}{x['validAssessments']}条、{x['totalMean']:.2f}分" for x in m['symptoms'].get('diseaseDistribution', [])) + "。总分和维度均值只能用于服务分层，不能替代临床判断。")
    disease_scores = m['symptoms'].get('diseaseDistribution', [])
    if disease_scores:
        high_disease = max(disease_scores, key=lambda x: x['totalMean'])
        body(f"当前总分均值最高的疾病分型为{high_disease['label']}（{high_disease['totalMean']:.2f}分，{high_disease['validAssessments']}条有效评估），应优先核查其高分维度、随访非正向回答和提醒响应情况。不同病种样本量存在差异时，应同时查看有效评估数，避免小样本均值被过度解读。")
    body("下一周期建议按疾病分型建立复测队列：对均值较高或非正向回答较集中的病种增加复测提醒，对评估量较少的病种先补齐样本，再判断是否存在稳定差异。患者级复核仍需回到具体题项、评估时间和联合用药结构。")
    table(["疾病分型", "有效评估数", "总分均值"], [[x['label'], x['validAssessments'], f"{x['totalMean']:.2f}"] for x in disease_scores], "按疾病分型的症状自评评分"); chart("disease-symptom")

    h1("六、不良反应监测与分析")
    h2("（一）不良反应概况")
    if adverse_events_provided:
        ae = m['adverseEvents']; body(f"本周期记录不良反应{ae['recordCount']}例，涉及患者{ae['patientCount']}人，患者发生率为{m['adverseEventRate']['display']}。记录数与涉及患者数{('一致，当前未见同一患者多条事件记录。' if ae['recordCount'] == ae['patientCount'] else '不一致，提示存在患者多事件记录，需要按患者维度复核。')}")
        body(f"按患者总数计算，未记录不良反应的患者为{n - ae['patientCount']:,}人，占{pct(n - ae['patientCount'], n)}。该比例只能说明当前清单中的记录状态，不能等同于所有患者均经过相同强度的主动安全随访；评价安全监测质量时，还应同时查看随访覆盖、异常上报及时性和事件字段完整性。")
        body("不良反应监测的管理重点是闭环而非单纯追求低发生率。每条事件都应能够回溯患者、相关药品、发生时间、严重程度、是否人工干预、处理措施和转归；对于没有事件的患者，也应保留是否完成过安全性询问的过程记录，以区分‘确认无异常’和‘没有形成评估记录’。")
        table(["指标", "数值"], [["不良反应记录", ae['recordCount']], ["涉及患者", ae['patientCount']], ["患者发生率", m['adverseEventRate']['display']]], "不良反应概况"); chart("adverse-events")
        h2("（二）不良反应特征总结")
        sev = ae['severityDistribution'] or [{"label":"无记录", "count":0}]; body("严重程度分布为" + "、".join(f"{x['label']}（{x['count']}例，{pct(x['count'], ae['recordCount'])}）" for x in sev) + "。应持续核对严重程度分级、发生时间和处理结果是否完整，避免仅凭事件数量判断安全性。")
        severe_count = sum(item['count'] for item in sev if item['label'] in {'重度', '严重', '危及生命', '高度'})
        body(f"本周期严重程度最高的记录为{sev[0]['label'] if sev else '无记录'}，高严重程度事件{severe_count:,}例。该分布只能描述当前服务周期的记录状态，不能外推为长期安全性结论；建议继续保持发生时间、关联药品、处理措施和转归四类字段的完整填写，以便后续按事件类型比较变化。")
        table(["严重程度", "例数"], [[x['label'], x['count']] for x in sev], "不良反应严重程度分布")
        body("不良反应记录按疾病、发生时间、严重程度和处理结果进行关联复核。现有数据支持对记录进行描述性归因，不足以单独确认产品与事件之间的因果关系。")
        manual_yes = next((x['count'] for x in ae['manualInterventionDistribution'] if x['label'] == '是'), 0)
        body("从疾病分布看，事件涉及" + "、".join(f"{x['label']}{x['count']}例" for x in ae['diseaseDistribution']) + f"；触发人工干预{manual_yes:,}例。下一周期应继续检查事件是否与具体联合用药、用药时间或疾病类型重复出现，重复模式才适合进入专项复核。")
        table(["关联维度", "分布"], [["相关疾病", "、".join(f"{x['label']}（{x['count']}例）" for x in ae['diseaseDistribution']) or "无记录"], ["是否人工干预", "、".join(f"{x['label']}（{x['count']}例）" for x in ae['manualInterventionDistribution']) or "无记录"]], "不良反应与用药关系复核")
        body("处理结果与转归字段用于记录事件处置后的状态。当前数据的转归分布为" + "、".join(f"{x['label']}（{x['count']}例）" for x in ae['outcomeDistribution']) + "。建议将未好转、重复发生或触发人工干预的记录设置为次周期优先复核对象。")
        body(f"当前共有{sum(x['count'] for x in ae['outcomeDistribution']):,}条转归记录。转归分布可用于检查事件处理记录是否闭环，但不应替代对具体患者的医学判断；建议保留每条事件的原始描述，并在下一周期追踪是否复发或再次触发提醒。")
        table(["处理结果/转归", "例数"], [[x['label'], x['count']] for x in ae['outcomeDistribution']] or [["无记录", 0]], "不良反应处理措施与转归")

    else:
        body("本节采用不良反应清单选填模式，展示安全监测的服务要求，不计算事件例数、发生率及严重程度分布。选填模式不构成零事件或已确认安全的结论，问卷中的身体不适回答也不能直接替代经登记的不良反应事件。")
        body("安全监测应与用药提醒、智能随访和症状自评建立患者级联系。服务团队可先复核出现不适、症状负担较高或持续未响应的患者，核对题项、回答时间及用药安排，再确定是否需要进一步询问或建立事件记录。")
        body("后续新增事件时，应逐条记录患者ID、发生时间、症状描述、相关药品、严重程度、处理措施和转归。只有采用一致的事件登记范围和观察周期，才适合计算发生率或比较不同月份的安全监测结果。")
        h2("（二）不良反应特征总结")
        body("不良反应特征分析需围绕具体事件展开，不能从没有附清单这一操作推断患者没有不适，也不能将某项主观回答直接认定为产品导致的不良反应。分析时应区分患者体验、事件登记与因果关系评价三个层次。")
        body("事件复核可依次核对症状出现与给药的时间关系、同一患者的联合用药、既往反应及后续处理经过。对于可能涉及多个药品的记录，应保留原始描述与时间信息，避免仅凭产品名称或疾病名称作归因判断。")
        body("安全服务的改进重点是可追溯的处置流程：发现异常后记录评估结果，执行相应处理并追踪转归；恢复常规管理前核对是否反复出现相同症状。统计展示应与记录完整性相结合，不能把较少的事件数量作为唯一质量目标。")

    h1("七、患者风险评估")
    h2("（一）风险分级概况")
    if adverse_events_provided:
        risk = m['riskDistribution']; body("风险分层规则基于不良反应、人工干预和可观察服务数据。" + "、".join(f"{x['label']}{x['count']}人（{x['count']/n*100:.1f}%）" for x in risk) + "。风险结果不等同于临床诊断。")
        body(f"本周期低风险患者占{pct(next((x['count'] for x in risk if x['label'] == '低风险'), 0), n)}，中风险和高风险合计{sum(x['count'] for x in risk if x['label'] != '低风险'):,}人。由于风险分层主要受不良反应和人工干预记录影响，低风险占比高并不表示所有患者都完成了随访或症状自评，仍需将风险结果与服务覆盖缺口并行查看。")
        table(["风险等级", "患者数", "占比"], [[x['label'], x['count'], f"{x['count']/n*100:.1f}%"] for x in risk], "患者风险分层分布"); chart("risk")
        midhigh = sum(x['count'] for x in risk if x['label'] != '低风险'); body(f"本周期中高风险患者共{midhigh}人，占患者总数{pct(midhigh, n)}。建议对相关患者核对不良反应记录、处理结果、随访连续性和症状自评高分维度，并根据复核结果安排加强随访或人工介入。")
        body(f"中高风险患者数量较少但具有明确的复核价值，当前{midhigh}名患者均应建立患者级跟踪清单，至少记录事件发生日期、涉及药品、处置结果、下一次随访时间和是否再次出现异常。对于低风险患者，则可保持标准化提醒，同时用覆盖率和未响应连续次数作为升级人工服务的触发条件。")
        body("风险管理可采用动态升级和回落机制：新发生不良反应、需要人工干预或出现连续异常时提高复核优先级；完成处置、转归明确且后续无重复异常时，再由服务团队确认是否恢复常规管理。这样能够避免风险标签长期固定，也能保证每次等级变化都有数据依据和处理记录。")

    else:
        body("本周期不输出依赖不良反应事件的低、中、高风险人数及比例。服务复核可继续围绕人工干预标记、随访回答、症状评分和提醒响应开展，但这些过程信号用于安排核查顺序，不替代患者风险等级或临床诊断。")
        body(f"当前智能随访覆盖{m['followupCoverage']['display']}，症状自评覆盖{m['symptomCoverage']['display']}。应把已经完成评估与尚待补访的患者分别管理，优先核对人工干预标记和异常题项；覆盖缺口意味着服务链存在待完成环节，不等同于某一临床风险等级。")
        body("对已触发人工干预的患者，应保留触发原因、评估日期、处理结果和下一次复核时间。对持续未响应的患者，应先检查触达是否成功、联系方式是否有效以及操作理解情况，再依据实际复核结果决定后续服务安排。")
        body("风险管理应在新的事件或评估信息进入后动态更新，明确每次调整所依据的患者事实。恢复常规服务也应有处置完成、转归和后续观察记录支持，不能将不良反应清单选填自动转化为全体患者低风险。")

    h1("八、服务质量与SLA达标分析")
    goals = m['serviceGoals']; body("本报告以实际数据对服务覆盖、方案生成、随访、自评和安全监测进行对照。由于输入资料未提供具体合同阈值，表中目标采用数据契约规定的全量覆盖或持续提升口径，不对未提供阈值作确定性达标判断。")
    h2("（一）AI服务覆盖率")
    body("服务质量复盘应为每项指标指定数据来源、统计周期、分子分母和责任环节。覆盖不足时先核对入组、激活、方案生成、消息送达及结果回传是否衔接，再确定补访责任人和复核日期；覆盖完整时仍应检查重复触达和答卷质量。没有明确合同阈值的指标只作现状分析，不能用默认目标文字代替已签约的验收条件。")
    table(["指标", "实际值", "目标口径"], [[x['label'], x['actual']['display'], x['goal']] for x in goals], "AI服务覆盖率与目标口径")
    body("SLA解读应区分覆盖率、过程量和结果指标：覆盖率反映触达范围，提醒次数反映执行量，随访和自评记录反映评估深度。健康管理方案覆盖完整，但智能随访和症状自评仍存在患者级缺口；建议将缺口直接转化为补访名单和完成时限。")
    body(f"按当前服务数据，健康管理方案覆盖{m['healthPlanCoverage']['numerator']:,}名患者；智能随访仍有{n - m['followupCoverage']['numerator']:,}人的覆盖缺口，症状自评仍有{n - m['symptomCoverage']['numerator']:,}人的覆盖缺口。")
    if adverse_events_provided:
        body(f"不良反应监测指标按‘未记录不良反应患者数/患者总数’计算为{m['serviceGoals'][-1]['actual']['display']}，该指标反映事件记录结果，不代表主动安全询问的实际覆盖率。")
    chart("service")
    h2("（二）各模块按疾病覆盖率")
    body("同一疾病组的各模块覆盖率应共用该组主表患者数，模块分子分别按唯一患者ID计数。分析缺口时，应进一步求出未覆盖患者名单及不同模块之间的交集，区分同一批患者连续缺失和不同患者分散缺失；两种情况需要不同的补访安排。汇总表本身不提供这些交集，实施前须完成患者级对账而非根据比例猜测。")
    disease_cov = m.get('moduleCoverageByDisease', [])
    body("按疾病分型查看模块覆盖率，可以识别总体覆盖率背后的病种差异。当前各疾病分型的患者数与模块覆盖情况为" + "、".join(f"{x['label']}{x['patientCount']}人" for x in disease_cov[:8]) + "。小样本病种的覆盖率波动应结合患者数解读。")
    body("建议将健康管理方案、用药提醒、智能随访和症状自评四类模块放在同一疾病分型表中，优先检查随访或自评覆盖明显低于方案覆盖的病种，再回溯机构接入、服务启动和数据回传环节。")
    table(["疾病分型", "患者数", "方案覆盖", "用药提醒", "智能随访", "症状自评"], [[x['label'], x['patientCount'], x['modules']['健康管理方案']['display'], x['modules']['用药提醒']['display'], x['modules']['智能随访']['display'], x['modules']['症状自评']['display']] for x in disease_cov], "各疾病分型服务模块覆盖率"); chart("disease-coverage")
    h2("（三）各模块按年龄覆盖率")
    body("年龄组覆盖结果应与患者人数同时阅读，尤其避免将人数极少组的百分比波动直接当作数字化服务障碍。复核可先定位未覆盖患者，再核对联系方式、服务开始日期和已完成的其他模块，确认属于等待执行、信息未回传还是实际未参与。完成核查后，按相同年龄分组和观察窗口复算指标，才能评价后续措施是否填补原有缺口。")
    age_cov = m.get('moduleCoverageByAge', [])
    body("按年龄组拆分模块覆盖率，可用于判断数字化服务是否对不同年龄层保持相近的服务机会。当前年龄组患者数为" + "、".join(f"{x['label']}{x['patientCount']}人" for x in age_cov) + "。该比较反映服务触达差异，不直接推断年龄与响应行为的因果关系。")
    body("若高龄组在随访或症状自评覆盖方面持续偏低，应优先核查提醒可读性、操作步骤和设备使用；若年轻组覆盖偏低，则应核查触达时段和消息频次。所有调整均应在下一周期用同一分母口径复核。")
    table(["年龄组", "患者数", "方案覆盖", "用药提醒", "智能随访", "症状自评"], [[x['label'], x['patientCount'], x['modules']['健康管理方案']['display'], x['modules']['用药提醒']['display'], x['modules']['智能随访']['display'], x['modules']['症状自评']['display']] for x in age_cov], "各年龄组服务模块覆盖率"); chart("age-coverage")

    h1("九、总结")
    conclusions = [
        ("1、服务覆盖与数据链完整性", f"本周期覆盖{n:,}名患者、{meta['regionCount']}个地区和{meta['diseaseCount']}类疾病，形成方案、提醒、随访和自评{'及安全监测' if adverse_events_provided else ''}的数据链。健康管理方案覆盖{m['healthPlanCoverage']['display']}，智能随访和症状自评仍存在患者级缺口，下一周期应优先补齐服务链断点。"),
        ("2、提醒服务执行量与响应情况", f"三类提醒累计{s['totalPrompts']:,}次，按患者级响应率加权估算响应率为{s['estimatedResponseRate']['display']}。后续应同时观察总体响应率、单人触达频次和连续未响应情况，避免用提醒总量代替服务参与度。"),
        ("3、用药结构与疗程记录", f"用药记录{meds['recordCount']:,}条、涉及{meds['uniqueDrugCount']}种药品；产品规格、频次和疗程分布需要结合具体分布复核，联合用药结构见本报告明细。下一周期可将长尾药品、规格字段和联合用药提醒作为抽查重点。"),
        ("4、随访、自评与安全监测", (f"智能随访{s['followupRecords']:,}条、症状自评{s['symptomRecords']:,}条，不良反应涉及患者{ae['patientCount']}人，严重程度最高记录为{sev[0]['label'] if sev else '无记录'}。建议持续关注非正向随访选项、高分自评记录和中高风险患者的连续复核。" if adverse_events_provided else f"智能随访{s['followupRecords']:,}条、症状自评{s['symptomRecords']:,}条。安全监测采用清单选填模式，不作零事件或全体低风险判断；建议对不适回答、人工干预标记及高分自评记录进行患者级复核，并保留处置过程和转归。")),
        ("5、下一周期服务建议", "建议保持患者ID和统计分母口径一致，提升随访与症状自评的连续覆盖，根据患者级复核结果安排差异化复访，并在合同阈值明确后补充严格的SLA达标判定和异常升级规则。"),
    ]
    for title, text in conclusions:
        h3(title); body(text)
    doc.core_properties.title = "患者洞察报告"
    doc.save(output_path)
    with ZipFile(output_path) as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("输出DOCX缺少word/document.xml")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--insight", required=True); parser.add_argument("--charts", required=True); parser.add_argument("--template"); parser.add_argument("--output", required=True); args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    print(build_report(args.insight, args.charts, args.template, args.output))


if __name__ == "__main__":
    main()
