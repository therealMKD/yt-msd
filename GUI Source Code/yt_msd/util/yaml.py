# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.yaml).
import re
import json
from typing import List, Tuple



def _yaml_scalar_repr(value) -> str:
    """Render a single scalar the way the export manifest writes it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if value is None:
        return "null"
    text = str(value)
    needs_quotes = (
        text == ""
        or text != text.strip()
        or any(ch in text for ch in ("#", "\n", "\r", '"', "'", "\\"))
        or ": " in text
        or text.endswith(":")
        or text[0] in "-?&*!|>%@`{}[]"
        or text.lower() in ("true", "false", "null", "yes", "no", "on", "off")
    )
    return json.dumps(text) if needs_quotes else text



def yaml_dump(data, indent: int = 0) -> str:
    """Serialize the small YAML subset used by export.yaml."""
    pad = " " * indent
    lines: List[str] = []
    if not isinstance(data, dict):
        return "\n".join(lines)
    for key, value in data.items():
        key = str(key)
        if isinstance(value, dict):
            if value:
                lines.append(f"{pad}{key}:")
                lines.append(yaml_dump(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: {{}}")
        elif isinstance(value, list):
            if value:
                lines.append(f"{pad}{key}:")
                lines.append(_yaml_dump_list(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: []")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar_repr(value)}")
    return "\n".join(lines)



def _yaml_dump_list(items: List, indent: int) -> str:
    pad = " " * indent
    lines: List[str] = []
    for item in items:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
            elif any(isinstance(value, (dict, list)) for value in item.values()):
                lines.append(f"{pad}-")
                lines.append(yaml_dump(item, indent + 2))
            else:
                pairs = list(item.items())
                first_key, first_value = pairs[0]
                lines.append(f"{pad}- {first_key}: {_yaml_scalar_repr(first_value)}")
                for key, value in pairs[1:]:
                    lines.append(f"{pad}  {key}: {_yaml_scalar_repr(value)}")
        elif isinstance(item, list):
            if item:
                lines.append(f"{pad}-")
                lines.append(_yaml_dump_list(item, indent + 2))
            else:
                lines.append(f"{pad}- []")
        else:
            lines.append(f"{pad}- {_yaml_scalar_repr(item)}")
    return "\n".join(lines)



def _yaml_scalar_parse(body: str):
    """Inverse of _yaml_scalar_repr for the scalar shapes export.yaml uses."""
    body = body.strip()
    if body == "[]":
        return []
    if body == "{}":
        return {}
    if body.startswith('"'):
        try:
            return json.loads(body)
        except Exception:
            return body.strip('"')
    lowered = body.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", body):
        return int(body)
    if re.fullmatch(r"-?\d+\.\d+", body):
        return float(body)
    return body



def yaml_load(text: str) -> dict:
    """Parse export.yaml back into a dict (comments and blank lines are ignored)."""
    lines: List[Tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw_line) - len(raw_line.lstrip(" ")), stripped))
    if not lines:
        return {}

    pos = 0

    def parse_mapping(indent: int) -> dict:
        nonlocal pos
        result: dict = {}
        while pos < len(lines):
            current_indent, content = lines[pos]
            if current_indent < indent or content.startswith("-"):
                break
            if current_indent > indent:
                pos += 1
                continue
            key, _, rest = content.partition(":")
            key = key.strip().strip('"')
            rest = rest.strip()
            pos += 1
            if rest:
                result[key] = _yaml_scalar_parse(rest)
                continue
            if pos < len(lines) and lines[pos][0] > indent:
                child_indent = lines[pos][0]
                if lines[pos][1].startswith("-"):
                    result[key] = parse_sequence(child_indent)
                else:
                    result[key] = parse_mapping(child_indent)
            else:
                result[key] = None
        return result

    def parse_sequence(indent: int) -> list:
        nonlocal pos
        result: list = []
        while pos < len(lines):
            current_indent, content = lines[pos]
            if current_indent != indent or not content.startswith("-"):
                break
            body = content[1:].strip()
            pos += 1
            if not body:
                if pos < len(lines) and lines[pos][0] > indent:
                    child_indent = lines[pos][0]
                    if lines[pos][1].startswith("-"):
                        result.append(parse_sequence(child_indent))
                    else:
                        result.append(parse_mapping(child_indent))
                else:
                    result.append(None)
            elif ":" in body and not body.startswith('"'):
                key, _, rest = body.partition(":")
                item = {key.strip(): _yaml_scalar_parse(rest) if rest.strip() else None}
                if pos < len(lines) and lines[pos][0] > indent:
                    item.update(parse_mapping(lines[pos][0]))
                result.append(item)
            else:
                result.append(_yaml_scalar_parse(body))
        return result

    top_indent = lines[0][0]
    if lines[0][1].startswith("-"):
        return {"items": parse_sequence(top_indent)}
    return parse_mapping(top_indent)
