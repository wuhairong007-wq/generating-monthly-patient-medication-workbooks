# 生成洞察报告

规则和实现移植自用户指定的 `full-course-of-disease-tool/generating-patient-full-course-data` 洞察报告流程。运行时仅使用本技能的文件，无需访问原目录。

## 请求与资料

```text
生成洞察报告
产品：产品名称
服务周期：2026-09-01 至 2026-09-30
委托方：委托方名称
服务商：服务商名称
依据以下文件：
/Users/a11/Downloads/AI智能随访/月度患者清单_江苏畅达-4月-300w.xlsx
/Users/a11/Downloads/AI智能随访/患者随访_江苏畅达-4月-300w.xlsx
/Users/a11/Downloads/AI智能随访/症状自评_江苏畅达-4月-300w.xlsx
/Users/a11/Downloads/AI智能随访/用药提醒_江苏畅达-4月-300w.xlsx
/Users/a11/Downloads/AI智能随访/不良反应清单_江苏畅达-4月-300w.xlsx
输出Word文件模板：/绝对路径/视觉参考.docx
```

产品、合法服务周期、月度患者清单、患者随访、症状自评、用药提醒为必填。常用输入为上述五份 Excel；不良反应清单可省略，合计4或5份。无需另外提供健康管理方案、逐药用药清单。委托方、服务商及视觉参考模板可省略；无委托方/服务商时封面相应内容留空。冒号兼容中文和英文，路径中的 Markdown 转义 `\_`、`\.` 会还原。路径不能重复，角色必须按表头核验。

示例中的9月周期与4月文件不能自动视为同一月份：先核对表内日期和主表标题月份。不得自行把请求改为4月；不匹配的提醒汇总标为无法统计，日期明细只纳入请求周期。产品名称、委托方、服务商及“/绝对路径/视觉参考.docx”均为待替换示例，不是实际生成参数。

| 角色 | 必需表头（最小识别集） |
| --- | --- |
| 月度患者清单 | userid、性别、年龄、地区、疾病；提醒总量另需AI用药提醒次数及可识别的标题月份 |
| 患者随访 | 患者ID、随访时间；使用实际十题答卷，含Q6 |
| 症状自评 | 患者ID、自评时间；使用实际六维度答卷 |
| 用药提醒 | userid、联合用药、用药方案确认时间、用药方案、用药周期 |
| 不良反应清单（选填） | 患者ID、不良反应发生时间、不良反应严重程度分级 |

兼容“患者唯一标识→userid”“所属地区→地区”，患者ID与userid用于关联；随访、自评等明细重复含人口学字段时，优先识别其专用角色，不能误判为主表。主表ID必须非空且唯一；日期明细按闭区间筛选，并排除不在主表中的患者，排除数写入诊断信息。源文件只读。

保留原6/7表模式兼容：患者主表、健康管理方案、跟踪提醒、智能随访、症状自评、带日期的逐药用药清单六类必填，加选填不良反应清单。按输入角色自动分流，不混合两种模式。旧跟踪提醒需含体温监测次数、用药提醒次数、患者响应率；旧逐药清单需含用药方案确认时间、药品名称、规格。该兼容分支不影响患者调研访谈原有资料要求。

## 月度五表统计边界

- 提醒总数来自主表 `AI用药提醒次数`；源标题月份必须与请求完整自然月一致。跨月、部分月、月份不明或计数不全均标为无法统计，不记零、不摊分。
- 用药方案登记覆盖按周期内确认记录的唯一患者数计算，分母为主表人数。联合用药仅按明确药名描述登记分布；药名按患者去重，组合按方案记录计数。不能反推药品规格、实际剂量频次、处方适宜性或真实服药。
- 不统计没有资料支持的健康管理方案覆盖、提醒响应率、体温和血压心率监测次数。不从旧用药方案文字生成新临床事实。
- 随访问答使用实际题目及选项分布；A/B仅称选项占比，不能统一称正向回答率。自评只使用完整六维度有效答卷，空周期不生成零分雷达图。
- 九章结构及封面、目录、版式保留；月度模式二三级标题按可用资料调整，不套用参考模板中的注射部位等固定问卷题目。缺少合同阈值时不能给出SLA达标结论。

## 执行

1. 全文阅读 [insight-report-schema.md](insight-report-schema.md)、[insight-report-writing.md](insight-report-writing.md)、[insight-report-template-contract.md](insight-report-template-contract.md)，并读取 `assets/patient-insight-report-generation-prompt-template.md.docx`。该 DOCX 是固定内容与格式的提示词模板，不是直接填充的成品文档。其中“01–05”等文件命名为模板示例；本功能输入角色和份数以本页月度4/5表或兼容6/7表的当前数据契约为准。
2. 在独立任务目录保存请求为 `request.txt`，运行 `node scripts/parse_report_request.mjs --input WORK/request.txt --output WORK/request.json`。解析结果中的 product、period、sourcePaths、client、provider、templatePath用于本次生成。
3. 使用工作区依赖中的 Python（需要 openpyxl、python-docx、lxml、Pillow）执行：

   ```bash
   python scripts/extract_insight_sources.py \
     --source /绝对路径/月度患者清单.xlsx \
     --source /绝对路径/患者随访.xlsx \
     --source /绝对路径/症状自评.xlsx \
     --source /绝对路径/用药提醒.xlsx \
     --source /绝对路径/不良反应清单.xlsx \
     --product 产品名称 --start 2026-09-01 --end 2026-09-30 \
     --output WORK/insight.json
   python scripts/generate_insight_charts.py --insight WORK/insight.json --output-dir WORK/charts
   python scripts/build_insight_report.py --insight WORK/insight.json \
     --charts WORK/charts/chart-manifest.json --output OUTPUT/患者洞察报告_产品名称_2026-09.docx
   python scripts/validate_insight_report.py --insight WORK/insight.json \
     --docx OUTPUT/患者洞察报告_产品名称_2026-09.docx
   ```

   省略不良反应清单时删除对应 `--source`；委托方和服务商分别通过抽取器的 `--client`、`--provider` 传入。自定义视觉参考通过构建器的 `--template` 传入；它只能补充页面、样式及页眉页脚，不能改变固定九章内容。命令中的路径、产品、日期均从本次请求替换，不把示例当作默认值。图表清单文件以图表脚本实际返回路径为准。
4. 核对比例的分子分母、数据来源、日期闭区间、有效答卷数和资料可用性。月度模式不能估算响应率；旧版模式仅按明确的跟踪提醒字段加权计算。省略不良反应清单时保留第六、七章，但不输出事件数、事件率及事件导出的风险分层；提供空清单时可以报告零条登记记录，两种情况不能混同。
5. 生成封面、动态目录和固定九章：报告概述、患者基本特征、用药提醒、智能随访、症状自评、不良反应、风险评估、服务质量与SLA、总结。正文固定28磅行距，标题、表格、图注按模板契约。每个核心小节要有数据、解释和具体行动；不复制模板示例数字，不以相关性代替因果性，不虚构合同阈值或达标结论。
6. 校验脚本通过后，检查可用的 Word 渲染环境。能渲染时用 documents 技能的 `render_docx.py` 生成页图并逐页查看；修复截断、重叠、字体或空白页问题。若 LibreOffice/poppler 或其他渲染依赖缺失，在内部核验记录及交付说明中明确“结构校验已完成，视觉核验未完成”及原因，不把结构检查当作视觉检查。
7. 默认输出到患者主表同级目录，文件名为 `患者洞察报告_<产品>_<YYYY-MM>.docx`；年月取服务周期开始日期。不可写时使用任务输出目录；重名追加时间戳。只交付本次最终 Word，图表、数据和预览留作内部核验。


### macOS 渲染器的中文字体配置

若 Word 中已指定宋体/黑体，但 LibreOffice 页图显示方框或只剩英文数字，先核对字体可用性。不要用通用字体替换模板字体。在独立任务目录创建 `fonts.conf`，让本次渲染进程读取系统字体及可写缓存：

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/System/Library/Fonts</dir>
  <dir>/Library/Fonts</dir>
  <cachedir>/本次任务绝对路径/font-cache</cachedir>
</fontconfig>
```

创建上述缓存目录后，仅在渲染命令前设置 `FONTCONFIG_FILE=/本次任务绝对路径/fonts.conf`，再调用可用的 `render_docx.py`。配置中的目录必须实际存在；其他系统按其真实字体位置配置。该方法只影响本次渲染，不改写模板字体或系统配置。重新渲染后再查看页图，不能将之前缺字的渲染标记为通过。
