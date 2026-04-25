from __future__ import annotations

import copy
from typing import Any
from uuid import uuid4

DEFAULT_PRESET_MODULES = {
    "no_user_speaking": True,
    "short_paragraph": False,
    "long_paragraph": False,
    "second_person": False,
    "third_person": False,
    "anti_repeat": True,
    "no_closing_feel": True,
}

PRESET_MODULE_RULES: dict[str, dict[str, str]] = {
    "no_user_speaking": {
        "label": "防抢话",
        "prompt": (
            "【防抢话硬规则】\n"
            "严禁替用户补写任何动作、台词、心理、决定、情绪结论和身体反应。\n"
            "除非用户在本轮输入中明确要求你代写，否则用户只能作为被观察对象存在。\n"
            "你只能描写非用户角色、环境和场景变化，不能推进用户行为。"
        ),
    },
    "short_paragraph": {
        "label": "短段落模式",
        "prompt": (
            "【短段落硬规则】\n"
            "每个自然段尽量控制在1到2句。\n"
            "对白必须尽量单独成段。\n"
            "不要连续输出大段长段落。"
        ),
    },
    "long_paragraph": {
        "label": "长段落模式",
        "prompt": (
            "【长段落硬规则】\n"
            "以长自然段为主。\n"
            "单段应尽量包含完整动作、观察、回应和延续。\n"
            "不要把一句话拆成很多零碎短段。"
        ),
    },
    "second_person": {
        "label": "第二人称",
        "prompt": (
            "【第二人称硬规则】\n"
            "涉及用户时，必须使用“你”来称呼用户。\n"
            "不得将用户写成“他”“她”“对方”“那个人”。"
        ),
    },
    "third_person": {
        "label": "第三人称",
        "prompt": (
            "【第三人称硬规则】\n"
            "涉及用户时，不得直接使用“你”称呼用户。\n"
            "必须使用第三人称方式描述用户。"
        ),
    },
    "anti_repeat": {
        "label": "抗重复",
        "prompt": (
            "【抗重复硬规则】\n"
            "避免重复前文已经高频出现的桥段、句式、修辞和收尾方式。\n"
            "同一轮回复中，不要反复用相似句子表达同一个意思。"
        ),
    },
    "no_closing_feel": {
        "label": "避免强收尾感",
        "prompt": (
            "【弱收尾硬规则】\n"
            "结尾禁止写成总结、升华、回顾、落幕或明显收束。\n"
            "回复必须停在一个仍在继续的进行中节点。"
        ),
    },
}

PRESET_MODULE_MUTEX: dict[str, list[str]] = {
    "short_paragraph": ["long_paragraph"],
    "long_paragraph": ["short_paragraph"],
    "second_person": ["third_person"],
    "third_person": ["second_person"],
}

def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def parse_int(value: Any, default: int = 0, *, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if min_value is not None:
        result = max(min_value, result)
    if max_value is not None:
        result = min(max_value, result)
    return result


def generate_preset_id() -> str:
    return f"preset_{uuid4().hex[:10]}"


def generate_prompt_group_id() -> str:
    return f"preset_group_{uuid4().hex[:10]}"


def generate_prompt_group_item_id() -> str:
    return f"preset_group_item_{uuid4().hex[:10]}"


def default_extra_prompts() -> list[dict[str, Any]]:
    return [
        {
            "id": "style-core",
            "name": "核心风格",
            "enabled": True,
            "content": "使用自然、流畅、地道的简体中文；优先直接描写行动、对白与场景，不要堆砌解释性总结。",
            "order": 100,
        },
        {
            "id": "dialogue-core",
            "name": "对白节奏",
            "enabled": True,
            "content": "对白要贴合角色身份与当下情绪，避免空泛说教；在场景允许时，多用自然对话推动情节。",
            "order": 200,
        },
    ]


def default_prompt_groups() -> list[dict[str, Any]]:
    return []


def default_single_preset(preset_id: str = "preset_default", name: str = "默认预设") -> dict[str, Any]:
    return {
        "id": preset_id,
        "name": name,
        "enabled": True,
        "base_system_prompt": "",
        "modules": dict(DEFAULT_PRESET_MODULES),
        "extra_prompts": default_extra_prompts(),
        "prompt_groups": default_prompt_groups(),
    }


def default_preset_store() -> dict[str, Any]:
    preset = default_single_preset()
    return {
        "active_preset_id": preset["id"],
        "presets": [preset],
    }


def sanitize_prompt_item(raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    prompt_id = str(raw.get("id", "")).strip() or f"preset-block-{index}"
    name = str(raw.get("name", "")).strip()[:64] or f"规则块 {index}"
    content = str(raw.get("content", "")).strip()[:12000]
    return {
        "id": prompt_id,
        "name": name,
        "enabled": parse_bool(raw.get("enabled"), True),
        "content": content,
        "order": parse_int(raw.get("order"), index * 100, min_value=0, max_value=999999),
    }


def normalize_selection_mode(value: Any) -> str:
    text = str(value or "single").strip().lower()
    if text in {"multi", "multiple", "checkbox", "checkboxes"}:
        return "multiple"
    return "single"


def sanitize_prompt_group_item(raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("id", "")).strip() or generate_prompt_group_item_id()
    name = str(raw.get("name", "")).strip()[:64] or f"规则项 {index}"
    content = str(raw.get("content", "")).strip()[:12000]
    return {
        "id": item_id,
        "name": name,
        "enabled": parse_bool(raw.get("enabled"), True),
        "content": content,
    }


def sanitize_prompt_group(raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    group_id = str(raw.get("id", "")).strip() or generate_prompt_group_id()
    selection_mode = normalize_selection_mode(raw.get("selection_mode"))

    raw_items = raw.get("items", [])
    items: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    if isinstance(raw_items, list):
        for item_index, item in enumerate(raw_items, start=1):
            cleaned = sanitize_prompt_group_item(item, item_index)
            if not cleaned:
                continue
            if cleaned["id"] in seen_item_ids:
                cleaned["id"] = generate_prompt_group_item_id()
            seen_item_ids.add(cleaned["id"])
            items.append(cleaned)

    valid_ids = {item["id"] for item in items}
    selected_ids_raw = raw.get("selected_ids", [])
    selected_ids: list[str] = []
    if isinstance(selected_ids_raw, list):
        for value in selected_ids_raw:
            item_id = str(value or "").strip()
            if item_id in valid_ids and item_id not in selected_ids:
                selected_ids.append(item_id)

    if not selected_ids:
        for item_raw, cleaned in zip(raw_items if isinstance(raw_items, list) else [], items):
            if isinstance(item_raw, dict) and parse_bool(item_raw.get("selected") if "selected" in item_raw else item_raw.get("checked"), False):
                if cleaned["id"] not in selected_ids:
                    selected_ids.append(cleaned["id"])

    if selection_mode == "single" and len(selected_ids) > 1:
        selected_ids = selected_ids[:1]

    return {
        "id": group_id,
        "name": str(raw.get("name", "")).strip()[:64] or f"规则组 {index}",
        "enabled": parse_bool(raw.get("enabled"), True),
        "selection_mode": selection_mode,
        "selected_ids": selected_ids,
        "items": items,
        "order": parse_int(raw.get("order"), index * 100, min_value=0, max_value=999999),
    }


def apply_module_mutex(modules: dict[str, bool]) -> dict[str, bool]:
    normalized = dict(DEFAULT_PRESET_MODULES)
    normalized.update({key: parse_bool(value, normalized.get(key, False)) for key, value in modules.items() if key in normalized})
    for key, opposites in PRESET_MODULE_MUTEX.items():
        if normalized.get(key):
            for other in opposites:
                normalized[other] = False
    return normalized


def sanitize_single_preset(raw: Any, *, fallback_name: str = "默认预设", fallback_id: str | None = None) -> dict[str, Any]:
    base = default_single_preset(fallback_id or generate_preset_id(), fallback_name)
    if not isinstance(raw, dict):
        return base
    sanitized = {
        "id": str(raw.get("id", "")).strip() or base["id"],
        "name": str(raw.get("name", fallback_name)).strip()[:64] or fallback_name,
        "enabled": parse_bool(raw.get("enabled"), True),
        "base_system_prompt": str(raw.get("base_system_prompt", "")).strip()[:16000],
        "modules": apply_module_mutex(raw.get("modules", {})) if isinstance(raw.get("modules", {}), dict) else dict(DEFAULT_PRESET_MODULES),
        "extra_prompts": [],
        "prompt_groups": [],
    }
    raw_prompts = raw.get("extra_prompts", [])
    if isinstance(raw_prompts, list):
        for index, item in enumerate(raw_prompts, start=1):
            cleaned = sanitize_prompt_item(item, index)
            if cleaned:
                sanitized["extra_prompts"].append(cleaned)
    raw_groups = raw.get("prompt_groups", [])
    seen_group_ids: set[str] = set()
    if isinstance(raw_groups, list):
        for index, item in enumerate(raw_groups, start=1):
            cleaned = sanitize_prompt_group(item, index)
            if not cleaned:
                continue
            if cleaned["id"] in seen_group_ids:
                cleaned["id"] = generate_prompt_group_id()
            seen_group_ids.add(cleaned["id"])
            sanitized["prompt_groups"].append(cleaned)
    has_explicit_extra = "extra_prompts" in raw
    has_explicit_groups = "prompt_groups" in raw
    if not sanitized["extra_prompts"] and not sanitized["prompt_groups"] and not has_explicit_extra and not has_explicit_groups:
        sanitized["extra_prompts"] = default_extra_prompts()
    return sanitized


def sanitize_preset_store(raw: Any) -> dict[str, Any]:
    default_store = default_preset_store()
    if isinstance(raw, dict) and "presets" not in raw and any(
        key in raw for key in ("name", "modules", "base_system_prompt", "extra_prompts", "prompt_groups")
    ):
        single = sanitize_single_preset(raw, fallback_name="默认预设", fallback_id="preset_default")
        return {"active_preset_id": single["id"], "presets": [single]}
    if not isinstance(raw, dict):
        return default_store
    presets_raw = raw.get("presets", [])
    presets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    if isinstance(presets_raw, list):
        for index, item in enumerate(presets_raw, start=1):
            preset = sanitize_single_preset(item, fallback_name=f"预设 {index}")
            if preset["id"] in seen_ids:
                preset["id"] = generate_preset_id()
            seen_ids.add(preset["id"])
            presets.append(preset)
    if not presets:
        presets = [default_single_preset()]
    active_preset_id = str(raw.get("active_preset_id", "")).strip()
    if not active_preset_id or active_preset_id not in {item["id"] for item in presets}:
        active_preset_id = presets[0]["id"]
    return {"active_preset_id": active_preset_id, "presets": presets}


def get_active_preset_from_store(store: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_preset_store(store)
    active_id = sanitized["active_preset_id"]
    for item in sanitized["presets"]:
        if item["id"] == active_id:
            return item
    return sanitized["presets"][0]


def build_selected_prompt_group_blocks(groups: list[dict[str, Any]]) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    for group_index, group in enumerate(groups, start=1):
        if not isinstance(group, dict) or not parse_bool(group.get("enabled"), True):
            continue
        group_name = str(group.get("name", "")).strip() or f"规则组 {group_index}"
        selected_ids = [str(item_id).strip() for item_id in group.get("selected_ids", []) if str(item_id).strip()]
        if not selected_ids:
            continue
        selected_set = set(selected_ids)
        order = parse_int(group.get("order"), group_index * 100, min_value=0, max_value=999999)
        items = group.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            if item_id not in selected_set:
                continue
            if not parse_bool(item.get("enabled"), True):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            item_name = str(item.get("name", "")).strip() or "规则项"
            blocks.append((order, f"[规则组：{group_name} / {item_name}]\n{content}"))
    return blocks


def build_preset_prompt_from_preset(preset: dict[str, Any]) -> str:
    sanitized = sanitize_single_preset(preset)
    if not sanitized.get("enabled", True):
        return ""
    sections: list[str] = []
    base_prompt = str(sanitized.get("base_system_prompt", "")).strip()
    if base_prompt:
        sections.append(base_prompt)
    module_statements: list[str] = []
    modules = sanitized.get("modules", {})
    for key, meta in PRESET_MODULE_RULES.items():
        if modules.get(key):
            prompt = str(meta.get("prompt", "")).strip()
            if prompt:
                module_statements.append(prompt)
    if module_statements:
        sections.append("预设模块规则（必须执行）：\n\n" + "\n\n".join(module_statements))

    ordered_blocks: list[tuple[int, int, str]] = []
    block_seq = 0
    for order, block in build_selected_prompt_group_blocks(sanitized.get("prompt_groups", [])):
        block_seq += 1
        ordered_blocks.append((order, block_seq, block))
    for item_index, item in enumerate(sanitized.get("extra_prompts", []), start=1):
        if not isinstance(item, dict) or not parse_bool(item.get("enabled"), True):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        name = str(item.get("name", "")).strip() or "规则块"
        order = parse_int(item.get("order"), item_index * 100, min_value=0, max_value=999999)
        block_seq += 1
        ordered_blocks.append((order, block_seq, f"[{name}]\n{content}"))
    if ordered_blocks:
        ordered_blocks.sort(key=lambda item: (item[0], item[1]))
        sections.append("\n\n".join(block for _, _, block in ordered_blocks))
    return "\n\n".join(section for section in sections if section).strip()


def create_preset_in_store(store: dict[str, Any], name: str = "") -> dict[str, Any]:
    sanitized = sanitize_preset_store(store)
    new_name = str(name or "").strip()[:64] or f"预设 {len(sanitized['presets']) + 1}"
    new_preset = default_single_preset(generate_preset_id(), new_name)
    sanitized["presets"].append(new_preset)
    return sanitized


def activate_preset_in_store(store: dict[str, Any], preset_id: str) -> dict[str, Any]:
    sanitized = sanitize_preset_store(store)
    target = str(preset_id or "").strip()
    if any(item["id"] == target for item in sanitized["presets"]):
        sanitized["active_preset_id"] = target
    return sanitized


def duplicate_preset_in_store(store: dict[str, Any], preset_id: str) -> dict[str, Any]:
    sanitized = sanitize_preset_store(store)
    target = get_active_preset_from_store(sanitized)
    requested = str(preset_id or "").strip()
    for item in sanitized["presets"]:
        if item["id"] == requested:
            target = item
            break
    duplicated = copy.deepcopy(target)
    duplicated["id"] = generate_preset_id()
    duplicated["name"] = (str(target.get("name", "预设")).strip() or "预设") + "（副本）"
    sanitized["presets"].append(duplicated)
    return sanitized


def delete_preset_from_store(store: dict[str, Any], preset_id: str) -> dict[str, Any]:
    sanitized = sanitize_preset_store(store)
    target = str(preset_id or "").strip()
    if len(sanitized["presets"]) <= 1:
        return sanitized
    sanitized["presets"] = [item for item in sanitized["presets"] if item["id"] != target]
    if not sanitized["presets"]:
        sanitized = default_preset_store()
    elif sanitized["active_preset_id"] == target:
        sanitized["active_preset_id"] = sanitized["presets"][0]["id"]
    return sanitized
