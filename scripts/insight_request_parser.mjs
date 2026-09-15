function extractValue(text, label) {
  const pattern = new RegExp(`^${label}[：:][ \\t]*(.*)$`, 'm');
  const value = text.match(pattern)?.[1]?.trim();
  if (!value) throw new Error(`${label}不能为空`);
  return value;
}

function extractOptionalValue(text, label) {
  const pattern = new RegExp(`^${label}[：:][ \\t]*(.*)$`, 'm');
  return text.match(pattern)?.[1]?.trim() || null;
}

export function parseInsightRequest(text) {
  if (!text.includes('生成洞察报告')) throw new Error('缺少“生成洞察报告”触发词');

  const product = extractValue(text, '产品');
  const periodText = extractValue(text, '服务周期');
  const periodMatch = periodText.match(/^(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})$/);
  if (!periodMatch) throw new Error('服务周期格式应为 YYYY-MM-DD 至 YYYY-MM-DD');
  const [, start, end] = periodMatch;
  if (start > end) throw new Error('服务周期开始日期不能晚于结束日期');

  const templateMatch = text.match(/^输出Word文件模板[：:][ \t]*(.*)$/m);
  const templatePath = templateMatch?.[1]?.trim() || null;
  if (templatePath && !templatePath.toLowerCase().endsWith('.docx')) throw new Error('输出Word文件模板必须为 .docx');

  const client = extractOptionalValue(text, '委托方');
  const provider = extractOptionalValue(text, '服务商');

  const sourceStart = text.search(/依据以下文件[：:]/);
  const sourceTail = sourceStart >= 0 ? text.slice(sourceStart).replace(/^依据以下文件[：:]\s*/, '') : '';
  const sourceBlock = sourceTail.split(/输出Word文件模板[：:]/)[0];
  const sourcePaths = sourceBlock
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/\\+([_.])/g, '$1'))
    .filter((line) => line.toLowerCase().endsWith('.xlsx'));

  if (new Set(sourcePaths).size !== sourcePaths.length) throw new Error('依据文件路径存在重复');
  if (![4, 5, 6, 7].includes(sourcePaths.length)) throw new Error(`月度洞察需要4或5个 .xlsx 路径，兼容原6或7份资料，当前为${sourcePaths.length}个`);

  return { product, period: { start, end }, sourcePaths, templatePath, client, provider };
}

export function parseDeepInterviewRequest(text) {
  text = text.replace(/\\+[ \t]*$/gm, '');
  if (!['生成患者调研访谈', '生成深度访谈'].some(trigger => text.includes(trigger))) throw new Error('缺少“生成患者调研访谈”触发词');
  const researchTime = extractValue(text, '调研时间');
  const modeMatch = text.match(/^内容模式[：:][ \t]*(.*)$/m);
  const modeText = modeMatch ? modeMatch[1].trim() : '模拟访谈';
  const modes = { '模拟访谈': 'simulated', '真实访谈': 'actual', '访谈提纲': 'outline' };
  if (!Object.hasOwn(modes, modeText)) throw new Error('内容模式只能为模拟访谈、真实访谈或访谈提纲');
  const dialogueMode = modes[modeText];
  const methodMatches = [...text.matchAll(/^[ \t]*调研方式[ \t]*[：:=][ \t]*(.*)$/gm)];
  if (methodMatches.length > 1) throw new Error('调研方式不能重复填写');
  const researchMethod = methodMatches.length ? methodMatches[0][1].trim() : '深度访谈';
  if (!['电话随访', '深度访谈'].includes(researchMethod)) throw new Error('调研方式只能填写“电话随访”或“深度访谈”');
  const outputKinds = researchMethod === '电话随访' ? ['records'] : ['analysis', 'records'];
  const countMatch = extractValue(text, '调研数量').match(/^(\d+)\s*人?$/);
  if (!countMatch || Number(countMatch[1]) < 1) throw new Error('调研数量必须为正整数，可带“人”');
  const mildMatch = text.match(/^是否轻度[：:][ \t]*(.*)$/m);
  const mildText = mildMatch ? mildMatch[1].trim() : '否';
  if (!['是', '否'].includes(mildText)) throw new Error('是否轻度只能填写“是”或“否”');
  const normalizePath = (line) => line.trim().replace(/\\+([_.])/g, '$1').replace(/\\+$/, '').trim();
  const sourceTail = text.split(/依据以下文件[：:]/)[1] || '';
  const blocks = sourceTail.split(/输出文件模板[：:]/);
  const sourcePaths = blocks[0].split(/\r?\n/).map(normalizePath).filter(Boolean);
  if (sourcePaths.some((p) => !p.toLowerCase().endsWith('.xlsx'))) throw new Error('依据文件必须为 .xlsx');
  if (new Set(sourcePaths).size !== sourcePaths.length) throw new Error('依据文件路径存在重复');
  if (![5, 6].includes(sourcePaths.length)) throw new Error(`深度访谈须提供5或6个 .xlsx 文件，当前为${sourcePaths.length}个`);
  const templatePaths = (blocks[1] || '').split(/\r?\n/).map(normalizePath).filter(Boolean);
  const allowedTemplateCounts = researchMethod === '电话随访' ? [1, 2] : [2];
  if (templatePaths.length && (!allowedTemplateCounts.includes(templatePaths.length) || templatePaths.some((p) => !p.toLowerCase().endsWith('.docx')))) {
    throw new Error(researchMethod === '电话随访' ? '输出文件模板须为一份明细 .docx 或原有两份 .docx' : '输出文件模板须为两份 .docx');
  }
  return { researchTime, researchMethod, dialogueMode, simulationAuthorized: dialogueMode === 'simulated', outputKinds, count: Number(countMatch[1]), includeMild: mildText === '是', sourcePaths, templatePaths };
}
