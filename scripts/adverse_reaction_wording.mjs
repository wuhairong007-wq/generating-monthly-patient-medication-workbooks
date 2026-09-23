const MANUAL_VERIFICATION_PATTERN = /人工(?:核实|复核|确认|审核)/;
const PRODUCT_REFERENCE_PATTERN = /(?:本品|该产品|本产品|当前产品|目标产品|推广产品|该药品|本药品|该药物|本药物|该药|本药|该器械|本器械)/;
const DOSAGE_FORM_SUFFIX = /(?:肠溶胶囊|缓释胶囊|软胶囊|肠溶片|缓释片|分散片|咀嚼片|泡腾片|口崩片|含片|口服液|混悬液|注射液|注射剂|吸入剂|喷雾剂|滴眼液|滴鼻液|滴耳液|胶囊剂|片剂|胶囊|颗粒剂|颗粒|糖浆|乳膏|软膏|凝胶|贴剂|丸剂|片|丸)$/;
const PRODUCT_PREFIX = /^(?:注射用|吸入用|口服用|外用)/;

function normalizeText(value) {
  return String(value ?? "").normalize("NFKC").replace(/[\s\u200B-\u200D\uFEFF]/g, "").toLowerCase();
}

function addCandidate(candidates, value) {
  const normalized = normalizeText(value);
  if (normalized.length >= 2) candidates.add(normalized);
}

export function productNameCandidates(productName) {
  const raw = String(productName ?? "").normalize("NFKC").trim();
  const candidates = new Set();
  addCandidate(candidates, raw);

  for (const match of raw.matchAll(/[（(]([^（）()]+)[）)]/g)) addCandidate(candidates, match[1]);

  const withoutAliases = raw.replace(/[（(][^（）()]+[）)]/g, "");
  addCandidate(candidates, withoutAliases);

  const withoutPrefix = withoutAliases.replace(PRODUCT_PREFIX, "");
  addCandidate(candidates, withoutPrefix);
  addCandidate(candidates, withoutPrefix.replace(DOSAGE_FORM_SUFFIX, ""));
  addCandidate(candidates, withoutAliases.replace(DOSAGE_FORM_SUFFIX, ""));

  return [...candidates];
}

export function validateAdverseReactionWording(record, productName) {
  const userid = String(record?.userid ?? "").trim() || "未知患者";
  const severity = String(record?.severityGrade ?? "").trim();

  if (severity === "轻度") {
    for (const [field, label] of [
      ["symptomDescription", "不良反应症状描述"],
      ["medicationRelationship", "与用药关系分析"],
      ["treatmentMeasures", "处理措施"],
    ]) {
      if (MANUAL_VERIFICATION_PATTERN.test(normalizeText(record?.[field]))) {
        throw new Error(`${userid}轻度患者的${label}不得出现“人工核实、人工复核、人工确认或人工审核”等人工核验文案`);
      }
    }
  }

  const relationship = normalizeText(record?.medicationRelationship);
  const matchedName = productNameCandidates(productName).find((candidate) => relationship.includes(candidate));
  if (matchedName || PRODUCT_REFERENCE_PATTERN.test(relationship)) {
    throw new Error(`${userid}的与用药关系分析不得包含推广产品正式名、商品名、简称、别名或产品回指文案`);
  }
}
