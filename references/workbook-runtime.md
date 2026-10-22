# Excel运行环境

本技能不要求另外安装 `spreadsheets:Spreadsheets`。月度清单和不良反应清单的四个构建/验证入口自动选择后端：

- `artifact`：找到 `@oai/artifact-tool` 时沿用原有模板、构建、重算及渲染路径。可设置 `CODEX_NODE_MODULES` 指向提供该包的 `node_modules`，也支持Node标准模块解析。
- `portable`：运行库不存在时自动使用内置Python脚本，以 `openpyxl` 读写模板，以 `Pillow` 生成已保存工作簿的首/中/末段预览。两个后端复用相同JS业务校验；独立验证器重读文件并核对值、顺序、药名、给药字段、四项注意事项及AE发生时间等规则。

不要因缺少子技能或没有 `CODEX_NODE_MODULES` 停止；先执行：

```bash
node scripts/check_workbook_environment.mjs
```

需要Node.js 20或更高版本及Python 3.10或更高版本。提取患者本身也使用 `openpyxl`。备用后端依赖在 `requirements-workbooks.txt` 中；检测提示缺失时，用实际运行技能的Python环境安装，不安装来源不明的同名artifact包：

```bash
python -m pip install -r requirements-workbooks.txt
```

Windows PowerShell也可用：

```powershell
py -3 -m pip install -r .\requirements-workbooks.txt
node .\scripts\check_workbook_environment.mjs
```

脚本自动尝试Windows的 `py -3`、`python`、`python3`，macOS/Linux的 `python3`、`python`。已有指定虚拟环境时，将 `PYTHON_BINARY` 设为解释器绝对路径，路径含空格或中文也可。PowerShell示例：

```powershell
$env:PYTHON_BINARY = "C:\Python312\python.exe"
$env:WORKBOOK_BACKEND = "portable"
node .\scripts\check_workbook_environment.mjs
```

`WORKBOOK_BACKEND` 默认 `auto`，可显式指定 `artifact` 或 `portable`；显式指定artifact而运行库缺失时准确报错，不伪装为已完成。中文预览使用Windows微软雅黑/黑体、macOS苹方或Linux Noto CJK等已安装字体；缺少时安装中文字体，或将 `WORKBOOK_PREVIEW_FONT` 设置为字体文件绝对路径。缺少Python、依赖或字体时返回具体原因和修复方法。

构建和验证仍执行 `SKILL.md` 中原命令，备用模式省略 `CODEX_NODE_MODULES=...` 前缀即可，示例：

```bash
node scripts/build_workbooks.mjs --payload payload.json --reminder-template assets/medication-reminder-template.xlsx --medication-template assets/medication-list-template.xlsx --output-dir output
node scripts/verify_workbooks.mjs --payload payload.json --reminder output/用药提醒_产品.xlsx --medication output/用药方案_产品.xlsx --report output/verification.json
```

路径应按实际产品和模拟后缀填写；不要假设文件名。两个流程均保留独立验证与视觉检查。备用预览由Pillow依据最终文件值、列宽和行高绘制，是版式检查辅助图，不是Microsoft Excel原生渲染或重算证明。备用清单仅写静态值，验证器拒绝意外公式；模板出现需计算的公式时应使用artifact或另行核对计算环境，不把缓存值当作已重算。不得以缺少插件为由跳过临床规则、写入虚构证据或改动原始Excel。
