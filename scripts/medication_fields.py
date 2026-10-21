import re


PRECAUTION_SECTIONS = ("饮食禁忌", "合并用药", "用药观察", "储存保存")
SECTION_LABEL = re.compile(r"(饮食禁忌|合并用药|用药观察|储存保存)[:：]")
CLOCK = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"
CLOCK_LIST = rf"{CLOCK}(?:、{CLOCK})*"


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
        if not isinstance(text, str) or not text.strip("；; \t\r\n") or SECTION_LABEL.search(text):
            raise ValueError(f"{label}的{key}必须为非空文本，不得缺项或重复标题")
        sections[key] = text.strip("；; \t\r\n")
    return sections


def format_precautions(sections):
    return "；".join(f"{key}：{sections[key]}" for key in PRECAUTION_SECTIONS)


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
