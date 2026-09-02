#!/usr/bin/env python3
import argparse
import base64
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


ALLOWED_DOMAINS = (
    "nmpa.gov.cn",
    "nhc.gov.cn",
    "gov.cn",
    "cma.org.cn",
    "csu.org.cn",
)
MAX_RESPONSE_BYTES = 1024 * 1024
REQUIRED_FIELDS = (
    "specification",
    "singleDose",
    "route",
    "frequency",
    "medicationTime",
    "treatmentDays",
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = ""
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href", "")
        self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or not self._href:
            return
        title = " ".join(self._text).strip()
        self.links.append((self._href.strip(), title))
        self._href = ""
        self._text = []


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        return re.sub(r"\s+", " ", unescape(" ".join(self.parts))).strip()


def is_allowed_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in ALLOWED_DOMAINS)


def normalize_result_url(url):
    url = unescape(url)
    parsed = urlparse(url)
    if parsed.hostname and parsed.hostname.lower().endswith("bing.com") and parsed.path.startswith("/ck/a"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            try:
                decoded = base64.urlsafe_b64decode(encoded[2:] + "===").decode("utf-8")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            except (ValueError, UnicodeDecodeError):
                pass
    return url


def _default_opener(url, timeout):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 codex-medication-search"})
    return urlopen(request, timeout=timeout)


def _read_response(response):
    data = response.read() if hasattr(response, "read") else response
    if not isinstance(data, (bytes, bytearray)):
        data = str(data).encode("utf-8")
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"响应超过{MAX_RESPONSE_BYTES}字节限制")
    return bytes(data)


def _decode(data):
    return data.decode("utf-8", errors="replace")


def _field(text, labels):
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{label_pattern})\s*[:：]\s*([^；;。\n]+)", text)
    return match.group(1).strip() if match else ""


def _integer_days(value):
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def parse_source_page(html, source_url, source_title, disease):
    parser = TextParser()
    parser.feed(html)
    text = parser.text()
    if disease not in text:
        return [], [], "来源页未明确提及目标疾病"
    if not re.search(r"用于|适用于|治疗|治疗或|症状管理|通便|补液", text):
        return [], [], "来源页未明确提供疾病治疗关联"

    drug_name = _field(text, ("药品名称", "药物名称", "通用名"))
    if not drug_name:
        return [], [], "来源页未提供结构化药品名称"
    values = {
        "drugName": drug_name,
        "specification": _field(text, ("规格",)),
        "singleDose": _field(text, ("每次用量", "单次剂量", "用量")),
        "route": _field(text, ("给药途径", "用法", "给药方式")),
        "frequency": _field(text, ("频次", "用药频次", "每日次数")),
        "medicationTime": _field(text, ("用药时间", "服用时间", "给药时间")),
        "treatmentDays": _integer_days(_field(text, ("疗程", "治疗天数"))),
    }
    missing = [field for field in REQUIRED_FIELDS if not values.get(field)]
    rationale = _field(text, ("疾病关联", "适应证", "适应症", "治疗关联"))
    if not rationale:
        rationale = f"来源页明确描述该药用于{disease}相关治疗或症状管理"
    if missing:
        incomplete = {"drugName": drug_name, "missingFields": missing, "sourceUrl": source_url}
        return [], [incomplete], "来源页药品字段不完整"

    candidate = {
        **values,
        "role": "diseaseTreatment",
        "diseaseRationale": rationale,
        "precautions": "仅在医师或药师确认当前疾病指征后使用；实际剂量和疗程须复核；不作疗效承诺",
        "evidence": [{"title": source_title or "白名单临床来源", "url": source_url, "scope": f"{disease}候选药及用法字段"}],
    }
    return [candidate], [], "parsed"


def search_candidates(product_name, disease, opener=None, timeout=15, max_results=8):
    opener = opener or _default_opener
    query = f'"{product_name}" "{disease}" 药品名称 规格 每次用量 用法'
    search_urls = [
        f"https://www.bing.com/search?q={quote_plus(query)}",
        f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
    ]
    result = {
        "status": "error",
        "query": query,
        "candidates": [],
        "incompleteCandidates": [],
        "sources": [],
        "errors": [],
    }
    seen_urls = set()
    links = []
    for search_url in search_urls:
        try:
            search_html = _decode(_read_response(opener(search_url, timeout)))
            parser = LinkParser()
            parser.feed(search_html)
        except Exception as exc:
            result["errors"].append(f"搜索请求失败：{exc}")
            continue
        for raw_url, title in parser.links:
            url = normalize_result_url(raw_url)
            if url in seen_urls or not is_allowed_url(url):
                continue
            seen_urls.add(url)
            links.append((url, title))
            if len(links) >= max_results:
                break
        if len(links) >= max_results:
            break
    if not links:
        if result["errors"]:
            result["status"] = "error"
        else:
            result["status"] = "no_results"
            result["errors"].append("搜索结果没有白名单来源链接")
        return result

    for source_url, source_title in links:
        source_record = {"url": source_url, "title": source_title, "status": "error"}
        try:
            source_html = _decode(_read_response(opener(source_url, timeout)))
            candidates, incomplete, status = parse_source_page(source_html, source_url, source_title, disease)
            result["candidates"].extend(candidates)
            result["incompleteCandidates"].extend(incomplete)
            source_record["status"] = status
            if status != "parsed":
                result["errors"].append(f"{source_url}：{status}")
        except Exception as exc:
            source_record["status"] = "error"
            source_record["error"] = str(exc)
            result["errors"].append(f"{source_url}：抓取失败：{exc}")
        result["sources"].append(source_record)

    deduped = {}
    for candidate in result["candidates"]:
        deduped.setdefault(candidate["drugName"], candidate)
    result["candidates"] = list(deduped.values())
    result["status"] = "success" if result["candidates"] else ("incomplete" if result["incompleteCandidates"] else "error")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True)
    parser.add_argument("--disease", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--max-results", type=int, default=8)
    args = parser.parse_args()
    result = search_candidates(args.product, args.disease, timeout=args.timeout, max_results=args.max_results)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "candidateCount": len(result["candidates"]), "sourceCount": len(result["sources"])}, ensure_ascii=False))
    if result["status"] != "success":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
