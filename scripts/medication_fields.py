import re


PRECAUTION_SECTIONS = ("饮食禁忌", "合并用药", "用药观察", "储存保存")
SECTION_LABEL = re.compile(r"(饮食禁忌|合并用药|用药观察|储存保存)[:：]")
PRECAUTION_SEPARATOR = r"(?:[。；，、！？：;,!?:]|\.(?!\d))"
REPEATED_PRECAUTION_PUNCTUATION = re.compile(
    rf"{PRECAUTION_SEPARATOR}(?:\s*{PRECAUTION_SEPARATOR})+")
PRECAUTION_BOUNDARY_PUNCTUATION = re.compile(
    rf"^(?:{PRECAUTION_SEPARATOR}\s*)+|(?:\s*{PRECAUTION_SEPARATOR})+$")
CLOCK = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"
CLOCK_LIST = rf"{CLOCK}(?:、{CLOCK})*"


def medication_plan_dose(value):
    # Only the summary omits conditional notes; detailed dosing remains unchanged.
    return re.sub(
        r"\s*(?:（[^()（）]*(?:疼痛|恶心|呕吐|便秘|发热|发烧|失眠|症状|不适|按需|必要时|需要时|PRN)[^()（）]*）"
        r"|\([^()（）]*(?:疼痛|恶心|呕吐|便秘|发热|发烧|失眠|症状|不适|按需|必要时|需要时|PRN)[^()（）]*\))",
        "", str(value), flags=re.IGNORECASE,
    ).strip()


def normalize_precaution_punctuation(text):
    text = PRECAUTION_BOUNDARY_PUNCTUATION.sub("", text.strip())
    return REPEATED_PRECAUTION_PUNCTUATION.sub(lambda match: match.group()[-1], text)


def precaution_sections(value, context):
    label = f"{context}注意事项"
    if isinstance(value, dict):
        if set(value) != set(PRECAUTION_SECTIONS):
            raise ValueError(f"{label}必须包含饮食禁忌、合并用药、用药观察、储存保存四项")
        sections = dict(value)
    elif isinstance(value, str):
        markers = list(SECTION_LABEL.finditer(value))
        if ([marker.group(1) for marker in markers] != list(PRECAUTION_SECTIONS)
                or value[:markers[0].start()].strip()):
            raise ValueError(f"{label}必须按饮食禁忌、合并用药、用药观察、储存保存顺序填写")
        sections = {
            marker.group(1): value[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(value)]
            for index, marker in enumerate(markers)
        }
    else:
        raise ValueError(f"{label}必须为四项对象或带四项标题的文本")
    for key in PRECAUTION_SECTIONS:
        text = sections[key]
        if not isinstance(text, str) or SECTION_LABEL.search(text):
            raise ValueError(f"{label}的{key}必须为非空文本，不得缺项或重复标题")
        text = normalize_precaution_punctuation(text)
        if not text:
            raise ValueError(f"{label}的{key}必须为非空文本，不得缺项或重复标题")
        if re.search(r"需医师审核|药房核对", text):
            raise ValueError(f"{label}不得包含“需医师审核”“药房核对”，请按药品依据重写对应内容")
        sections[key] = text
    return sections


def format_precautions(sections):
    return "；".join(
        f"{key}：{normalize_precaution_punctuation(sections[key])}" for key in PRECAUTION_SECTIONS)


def append_precaution_note(value, section, note, context):
    sections = precaution_sections(value, context)
    sections[section] += f"；{note}"
    return format_precautions(sections)


def normalize_medication_time(value, context):
    label = f"{context}用药时间"
    if not isinstance(value, str):
        raise ValueError(f"{label}必须为HH:mm时间点，以顿号连接")
    match = re.fullmatch(
        rf"\s*(?P<clocks>{CLOCK}(?:\s*、\s*{CLOCK})*)\s*"
        r"(?:（(?P<cn_note>[^()（）]+)）|\((?P<en_note>[^()（）]+)\))?\s*",
        value,
    )
    if not match:
        raise ValueError(f"{label}必须为HH:mm时间点，以顿号连接；缺少具体时点不得猜测")
    clocks = re.sub(r"\s+", "", match.group("clocks"))
    note = (match.group("cn_note") or match.group("en_note") or "").strip()
    return clocks, note
