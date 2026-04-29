from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field


def get_resource_dir() -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        return Path(bundle_dir)
    return Path(__file__).resolve().parent


APP_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = get_resource_dir()
DATA_DIR = APP_DIR / "data"
STATE_PATH = DATA_DIR / "characters.json"
SCHEMA_PATH = DATA_DIR / "field_schema.json"
STATIC_DIR = RESOURCE_DIR / "static"
TEMPLATES_DIR = RESOURCE_DIR / "templates"

DEFAULT_SETTINGS = {
    "enabled": True,
    "chat_panel_enabled": True,
    "inject_enabled": False,
    "position": "bottom",
    "compact": True,
    "max_visible": 8,
    "title": "角色状态",
    "hide_update_blocks": True,
    # True = 聊天正文里显示一个可展开的调试块，方便确认模型是否输出了 status_panel_update
    "show_update_debug_blocks": False,
    # off = 只隐藏并加入待确认；safe = 自动应用位置/关系/状态增删/摘要；all = 全字段自动应用
    "auto_apply_mode": "safe",
    "show_pending_in_chat": True,
    # False = 详情里显示全部扩展字段；True = 表格中已显示的扩展字段不再重复显示
    "hide_table_extras_in_detail": False,
}

DEFAULT_STATE = {
    "settings": DEFAULT_SETTINGS,
    "characters": [],
    "pending_updates": [],
    "processed_update_ids": [],
}

EXTRA_KEY_ALIASES = {
    "equipment": "装备", "equips": "装备", "item": "装备", "items": "装备", "gear": "装备", "装备": "装备", "物品": "装备", "携带物": "装备",
    "goal": "当前目标", "target": "当前目标", "current_goal": "当前目标", "currenttarget": "当前目标", "objective": "当前目标", "当前目标": "当前目标", "目标": "当前目标",
    "mental": "精神状态", "mental_status": "精神状态", "emotion": "精神状态", "mood": "精神状态", "精神": "精神状态", "精神状态": "精神状态", "情绪": "精神状态",
    "action": "行动状态", "action_status": "行动状态", "current_action": "行动状态", "行动": "行动状态", "行动状态": "行动状态", "当前动作": "行动状态",
    "leg": "腿部状态", "legs": "腿部状态", "leg_status": "腿部状态", "腿部": "腿部状态", "腿部状态": "腿部状态",
}


def normalize_extra_key(key: Any) -> str:
    raw = compact_text(key).replace(" ", "").replace("-", "_")
    if not raw:
        return ""
    lower = raw.lower()
    return EXTRA_KEY_ALIASES.get(raw) or EXTRA_KEY_ALIASES.get(lower) or raw

DEFAULT_FIELD_SCHEMA = {
    "table_columns": [
        {"key": "name", "label": "角色名"},
        {"key": "alive_status", "label": "存活状态"},
        {"key": "hp", "label": "HP"},
        {"key": "mp", "label": "MP"},
        {"key": "location", "label": "地点"},
        {"key": "status_effects", "label": "身体状态"},
    ],
    "detail_fields": [
        {"key": "group", "label": "分组"},
        {"key": "relationship", "label": "关系"},
        {"key": "short_summary", "label": "摘要"},
        {"key": "last_event", "label": "最近变化"},
        {"key": "updated_at", "label": "更新时间"},
        {"key": "extra.*", "label": "扩展资料"},
    ],
}

SAFE_UPDATE_FIELDS = {"location", "relationship", "short_summary", "last_event"}
RISKY_UPDATE_FIELDS = {"alive_status", "hp_current", "hp_max", "mp_current", "mp_max", "status_effects"}
IGNORED_TEXTS = {"", "无", "没有", "未提取", "未知", "?", "？", "?/?", "？/？", "当前值", "上限"}


class StatusPanelPayload(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    pending_updates: list[dict[str, Any]] = Field(default_factory=list)
    processed_update_ids: list[str] = Field(default_factory=list)


class ApplyUpdatePayload(BaseModel):
    update: dict[str, Any] = Field(default_factory=dict)
    mode: str | None = None


class ResolvePendingPayload(BaseModel):
    update_id: str
    action: str = "apply"


class FieldSchemaPayload(BaseModel):
    table_columns: list[dict[str, Any]] = Field(default_factory=list)
    detail_fields: list[dict[str, Any]] = Field(default_factory=list)


app = FastAPI(title="Xuqi Status Panel Mod")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def clone_default(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return clone_default(default)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return clone_default(default)
    return payload if isinstance(payload, dict) else clone_default(default)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def compact_text(value: Any) -> str:
    return str(value or "").strip()


def is_emptyish(value: Any) -> bool:
    text = compact_text(value)
    if text in IGNORED_TEXTS:
        return True
    if any(mark in text for mark in ["当前值/上限", "未知则写", "用逗号", "一句话说明"]):
        return True
    return False


def normalize_list(value: Any, *, keep_none: bool = False) -> list[str]:
    if isinstance(value, list):
        source = value
    else:
        source = str(value or "").replace("、", ",").replace("，", ",").split(",")
    result: list[str] = []
    for item in source:
        text = compact_text(item)
        if not text:
            continue
        if not keep_none and text in {"无", "没有", "未提取", "未知"}:
            continue
        if text not in result:
            result.append(text)
    return result


def normalize_extra(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, raw_val in value.items():
        name = normalize_extra_key(key)
        if not name or name.startswith("_"):
            continue
        if isinstance(raw_val, (list, tuple)):
            text = "、".join(compact_text(item) for item in raw_val if compact_text(item))
        elif isinstance(raw_val, dict):
            text = json.dumps(raw_val, ensure_ascii=False)
        else:
            text = compact_text(raw_val)
        if text and not is_emptyish(text):
            result[name] = text
    return result


def normalize_field_schema(raw: dict[str, Any] | None) -> dict[str, Any]:
    schema = clone_default(DEFAULT_FIELD_SCHEMA)
    if not isinstance(raw, dict):
        return schema

    if isinstance(raw.get("table_columns"), list):
        columns: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw["table_columns"]:
            if not isinstance(item, dict):
                continue
            key = compact_text(item.get("key"))
            label = compact_text(item.get("label")) or key
            if not key or key in seen:
                continue
            seen.add(key)
            columns.append({"key": key, "label": label})
        if columns:
            schema["table_columns"] = columns

    if isinstance(raw.get("detail_fields"), list):
        details: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw["detail_fields"]:
            if not isinstance(item, dict):
                continue
            key = compact_text(item.get("key"))
            label = compact_text(item.get("label")) or key
            if not key or key in seen:
                continue
            seen.add(key)
            details.append({"key": key, "label": label})
        if details:
            schema["detail_fields"] = details
    return schema


def get_field_schema() -> dict[str, Any]:
    raw = read_json(SCHEMA_PATH, DEFAULT_FIELD_SCHEMA)
    return normalize_field_schema(raw)


def save_field_schema(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_field_schema()
    raw = {
        "table_columns": payload.get("table_columns", current.get("table_columns", [])),
        "detail_fields": payload.get("detail_fields", current.get("detail_fields", [])),
    }
    schema = normalize_field_schema(raw)
    write_json(SCHEMA_PATH, schema)
    return schema


def split_pair(value: Any) -> tuple[str, str]:
    text = compact_text(value)
    if not text or is_emptyish(text):
        return "", ""
    if "/" not in text:
        return text, ""
    left, right = text.split("/", 1)
    left = compact_text(left)
    right = compact_text(right)
    return ("" if is_emptyish(left) else left), ("" if is_emptyish(right) else right)


def normalize_character(raw: dict[str, Any], index: int) -> dict[str, Any]:
    char_id = compact_text(raw.get("id")) or f"char-{uuid4().hex[:8]}"

    hp_current = compact_text(raw.get("hp_current"))
    hp_max = compact_text(raw.get("hp_max"))
    if not hp_current and not hp_max and raw.get("hp"):
        hp_current, hp_max = split_pair(raw.get("hp"))

    mp_current = compact_text(raw.get("mp_current"))
    mp_max = compact_text(raw.get("mp_max"))
    if not mp_current and not mp_max and raw.get("mp"):
        mp_current, mp_max = split_pair(raw.get("mp"))

    return {
        "id": char_id,
        "name": compact_text(raw.get("name")) or f"角色 {index}",
        "group": compact_text(raw.get("group")) or "未分组",
        "visible": bool(raw.get("visible", True)),
        "alive_status": compact_text(raw.get("alive_status")) or "未知",
        "hp_current": "" if is_emptyish(hp_current) else hp_current,
        "hp_max": "" if is_emptyish(hp_max) else hp_max,
        "mp_current": "" if is_emptyish(mp_current) else mp_current,
        "mp_max": "" if is_emptyish(mp_max) else mp_max,
        "location": "" if is_emptyish(raw.get("location")) else compact_text(raw.get("location")),
        "relationship": "" if is_emptyish(raw.get("relationship")) else compact_text(raw.get("relationship")),
        "status_effects": normalize_list(raw.get("status_effects", raw.get("effects", []))),
        "short_summary": compact_text(raw.get("short_summary", raw.get("summary", ""))),
        "last_event": compact_text(raw.get("last_event", raw.get("recent_event", ""))),
        "private_note": compact_text(raw.get("private_note")),
        "extra": normalize_extra(raw.get("extra", raw.get("extras", raw.get("custom", {})))),
        "updated_at": compact_text(raw.get("updated_at")) or now_string(),
    }


def normalize_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    if settings.get("auto_apply_mode") not in {"off", "safe", "all"}:
        settings["auto_apply_mode"] = "safe"
    try:
        settings["max_visible"] = max(1, min(50, int(settings.get("max_visible") or 8)))
    except (TypeError, ValueError):
        settings["max_visible"] = 8
    return settings


def get_state() -> dict[str, Any]:
    raw = read_json(STATE_PATH, DEFAULT_STATE)
    settings = normalize_settings(raw.get("settings") if isinstance(raw.get("settings"), dict) else None)

    characters: list[dict[str, Any]] = []
    for index, item in enumerate(raw.get("characters", []), start=1):
        if isinstance(item, dict):
            characters.append(normalize_character(item, index))

    pending_updates = [item for item in raw.get("pending_updates", []) if isinstance(item, dict)]
    processed_update_ids = [compact_text(item) for item in raw.get("processed_update_ids", []) if compact_text(item)]

    return {
        "settings": settings,
        "characters": characters,
        "pending_updates": pending_updates,
        "processed_update_ids": processed_update_ids,
    }


def save_state(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_state()
    settings = normalize_settings(payload.get("settings") if isinstance(payload.get("settings"), dict) else current.get("settings"))

    characters: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("characters", []), start=1):
        if isinstance(item, dict):
            characters.append(normalize_character(item, index))

    pending_updates = payload.get("pending_updates", current.get("pending_updates", []))
    if not isinstance(pending_updates, list):
        pending_updates = []
    pending_updates = [item for item in pending_updates if isinstance(item, dict)]

    processed_update_ids = payload.get("processed_update_ids", current.get("processed_update_ids", []))
    if not isinstance(processed_update_ids, list):
        processed_update_ids = []
    processed_update_ids = [compact_text(item) for item in processed_update_ids if compact_text(item)]

    state = {
        "settings": settings,
        "characters": characters,
        "pending_updates": pending_updates,
        "processed_update_ids": processed_update_ids,
    }
    write_json(STATE_PATH, state)
    return state


def build_status_summary(state: dict[str, Any]) -> str:
    settings = state.get("settings", {})
    characters = state.get("characters", [])
    if not settings.get("enabled", True):
        return ""

    visible_characters = [item for item in characters if isinstance(item, dict) and item.get("visible", True)]
    if not visible_characters:
        return ""

    lines = ["【角色状态摘要】"]
    for item in visible_characters:
        name = compact_text(item.get("name")) or "未命名角色"
        alive = compact_text(item.get("alive_status")) or "未知"
        hp_current = compact_text(item.get("hp_current")) or "?"
        hp_max = compact_text(item.get("hp_max")) or "?"
        mp_current = compact_text(item.get("mp_current")) or "?"
        mp_max = compact_text(item.get("mp_max")) or "?"
        has_hp = bool(compact_text(item.get("hp_current")) or compact_text(item.get("hp_max")))
        has_mp = bool(compact_text(item.get("mp_current")) or compact_text(item.get("mp_max")))
        hp = f"HP {hp_current}/{hp_max}" if has_hp else "HP 未记录"
        mp = f"MP {mp_current}/{mp_max}" if has_mp else "MP 未记录"
        location = compact_text(item.get("location"))
        relation = compact_text(item.get("relationship"))
        effects = normalize_list(item.get("status_effects", []))
        effects_text = "、".join(effects) if effects else "无明显异常"
        summary = compact_text(item.get("short_summary"))
        parts = [
            f"{name}：{alive}", hp, mp,
            f"位置：{location}" if location else "",
            f"关系：{relation}" if relation else "",
            f"状态：{effects_text}", summary,
        ]
        lines.append("，".join(part for part in parts if part))
    return "\n".join(lines).strip()


def normalize_update(raw: dict[str, Any]) -> dict[str, Any]:
    update = normalize_character(raw, 1)
    # status_panel_update 里的 summary 表示“本轮变化说明”，不再默认覆盖角色长期摘要。
    event_summary = compact_text(raw.get("last_event", raw.get("summary", raw.get("recent_event", ""))))
    explicit_summary = compact_text(raw.get("short_summary", ""))
    if event_summary:
        update["last_event"] = event_summary
    if explicit_summary:
        update["short_summary"] = explicit_summary
    elif "summary" in raw or "last_event" in raw or "recent_event" in raw:
        update["short_summary"] = ""
    update["kind"] = compact_text(raw.get("kind")) or "status_panel_update"
    update["source"] = compact_text(raw.get("source")) or "聊天"
    update["raw_text"] = compact_text(raw.get("raw_text"))
    update["effects_add"] = normalize_list(raw.get("effects_add", []))
    update["effects_remove"] = normalize_list(raw.get("effects_remove", []))
    update["effects_clear"] = bool(raw.get("effects_clear", False))
    update["no_change_guard"] = bool(raw.get("no_change_guard", False))
    update["guard_reason"] = compact_text(raw.get("guard_reason"))

    # status_panel_update 没写 alive_status 时，不要因为 normalize_character 默认值而变成“未知”。
    if "alive_status" not in raw and "生存状态" not in raw:
        update["alive_status"] = ""

    payload_for_hash = json.dumps({
        "id": update.get("id"),
        "name": update.get("name"),
        "source": update.get("source"),
        "raw_text": update.get("raw_text"),
        "location": update.get("location"),
        "effects_add": update.get("effects_add"),
        "effects_remove": update.get("effects_remove"),
        "effects_clear": update.get("effects_clear"),
        "summary": update.get("short_summary"),
        "last_event": update.get("last_event"),
        "extra": update.get("extra"),
    }, ensure_ascii=False, sort_keys=True)
    update_id = compact_text(raw.get("update_id")) or "xsp-" + hashlib.sha256(payload_for_hash.encode("utf-8")).hexdigest()[:20]
    update["update_id"] = update_id
    return update


def find_character(characters: list[dict[str, Any]], update: dict[str, Any]) -> dict[str, Any] | None:
    update_id = compact_text(update.get("id"))
    update_name = compact_text(update.get("name"))
    for item in characters:
        item_id = compact_text(item.get("id"))
        item_name = compact_text(item.get("name"))
        if update_id and item_id and update_id == item_id:
            return item
        if update_name and item_name and update_name == item_name:
            return item
    return None


def ensure_character(characters: list[dict[str, Any]], update: dict[str, Any]) -> dict[str, Any]:
    target = find_character(characters, update)
    if target is not None:
        return target
    target = {
        "id": compact_text(update.get("id")) or f"char-{uuid4().hex[:8]}",
        "name": compact_text(update.get("name")) or "未命名角色",
        "group": compact_text(update.get("group")) or "自动更新",
        "visible": True,
        "alive_status": compact_text(update.get("alive_status")) or "未知",
        "hp_current": compact_text(update.get("hp_current")),
        "hp_max": compact_text(update.get("hp_max")),
        "mp_current": compact_text(update.get("mp_current")),
        "mp_max": compact_text(update.get("mp_max")),
        "location": "",
        "relationship": "",
        "status_effects": [],
        "short_summary": "",
        "last_event": "",
        "private_note": "",
        "extra": normalize_extra(update.get("extra", {})),
        "updated_at": now_string(),
    }
    characters.append(target)
    return target


def update_has_risky_fields(update: dict[str, Any]) -> bool:
    if compact_text(update.get("alive_status")):
        return True
    if compact_text(update.get("hp_current")) or compact_text(update.get("hp_max")):
        return True
    if compact_text(update.get("mp_current")) or compact_text(update.get("mp_max")):
        return True
    if normalize_list(update.get("status_effects", [])):
        return True
    return False


def add_pending_update(state: dict[str, Any], update: dict[str, Any], pending_fields: list[str]) -> None:
    pending = state.setdefault("pending_updates", [])
    update_id = compact_text(update.get("update_id"))
    if not update_id:
        return
    for item in pending:
        if compact_text(item.get("update_id")) == update_id:
            return
    pending.append({
        "update_id": update_id,
        "created_at": now_string(),
        "pending_fields": pending_fields,
        "source": compact_text(update.get("source")) or "聊天",
        "update": update,
    })


def mark_processed(state: dict[str, Any], update_id: str) -> None:
    processed = state.setdefault("processed_update_ids", [])
    if update_id and update_id not in processed:
        processed.append(update_id)
    # 防止无限增长，保留最近 500 条。
    if len(processed) > 500:
        del processed[:-500]



EFFECT_REMOVE_ALIASES = {
    "紧张": ["紧张", "轻微紧张", "高度紧张", "非常紧张"],
    "警戒": ["警戒", "警惕", "高度警戒", "戒备"],
    "警惕": ["警戒", "警惕", "高度警戒", "戒备"],
    "兴奋": ["兴奋", "兴致勃勃", "兴致高", "兴致很好"],
    "兴致勃勃": ["兴奋", "兴致勃勃"],
    "受惊": ["受惊", "惊吓", "被吓到", "吓了一跳"],
    "疲惫": ["疲惫", "轻微疲惫", "疲劳", "劳累"],
    "受伤": ["受伤", "轻伤", "轻微擦伤", "擦伤"],
}


def normalize_effect_key(value: str) -> str:
    return compact_text(value).replace(" ", "").replace("　", "")


def should_remove_effect(effect: str, remove_item: str) -> bool:
    effect_key = normalize_effect_key(effect)
    remove_key = normalize_effect_key(remove_item)
    if not effect_key or not remove_key:
        return False
    if effect_key == remove_key:
        return True
    aliases = EFFECT_REMOVE_ALIASES.get(remove_key, [])
    if effect_key in {normalize_effect_key(item) for item in aliases}:
        return True
    # 宽松包含：remove“紧张”时可移除“轻微紧张”，remove“警戒”时可移除“高度警戒”。
    if remove_key in effect_key or effect_key in remove_key:
        return True
    return False


def should_clear_effects(update: dict[str, Any]) -> bool:
    if update.get("effects_clear"):
        return True
    full_effects = normalize_list(update.get("status_effects", []))
    if len(full_effects) == 1 and normalize_effect_key(full_effects[0]) in {"无", "无异常", "正常", "无明显异常"}:
        return True
    return False

def apply_update_fields(target: dict[str, Any], update: dict[str, Any], *, allow_risky: bool) -> list[str]:
    applied: list[str] = []

    for field in ["location", "relationship", "short_summary", "last_event"]:
        value = compact_text(update.get(field))
        if value and not is_emptyish(value):
            target[field] = value
            applied.append(field)

    # extra.* 是开源扩展字段，默认按安全字段处理。
    extra_update = normalize_extra(update.get("extra", {}))
    if extra_update:
        target_extra = normalize_extra(target.get("extra", {}))
        for key, value in extra_update.items():
            target_extra[key] = value
        target["extra"] = target_extra
        applied.append("extra")

    # effects_add / effects_remove 作为安全字段自动处理。
    effects = normalize_list(target.get("status_effects", []))
    changed_effects = False

    if should_clear_effects(update):
        if effects:
            effects = []
            changed_effects = True

    for effect in normalize_list(update.get("effects_add", [])):
        if normalize_effect_key(effect) in {"无", "无异常", "正常", "无明显异常"}:
            if effects:
                effects = []
                changed_effects = True
            continue
        if effect not in effects:
            effects.append(effect)
            changed_effects = True

    remove_items = normalize_list(update.get("effects_remove", []))
    if remove_items:
        next_effects = [
            effect for effect in effects
            if not any(should_remove_effect(effect, remove_item) for remove_item in remove_items)
        ]
        if next_effects != effects:
            effects = next_effects
            changed_effects = True

    if changed_effects:
        target["status_effects"] = effects
        applied.append("status_effects")

    if allow_risky:
        for field in ["alive_status", "hp_current", "hp_max", "mp_current", "mp_max"]:
            value = compact_text(update.get(field))
            if value and not is_emptyish(value):
                target[field] = value
                applied.append(field)
        full_effects = normalize_list(update.get("status_effects", []))
        if full_effects and not should_clear_effects(update):
            target["status_effects"] = full_effects
            if "status_effects" not in applied:
                applied.append("status_effects")

    if applied:
        target["updated_at"] = now_string()
    return applied


def apply_update_to_state(state: dict[str, Any], raw_update: dict[str, Any], mode: str) -> dict[str, Any]:
    update = normalize_update(raw_update)
    update_id = compact_text(update.get("update_id"))
    processed = state.setdefault("processed_update_ids", [])
    if update_id and update_id in processed:
        return {"status": "skipped", "reason": "already_processed", "update_id": update_id, "applied_fields": [], "pending_fields": []}

    if update.get("no_change_guard"):
        mark_processed(state, update_id)
        return {
            "status": "guarded",
            "reason": update.get("guard_reason") or "用户消息明确表示无状态变化，已跳过自动应用。",
            "update_id": update_id,
            "applied_fields": [],
            "pending_fields": [],
        }

    if mode not in {"off", "safe", "all"}:
        mode = "safe"

    risky_fields: list[str] = []
    for field in ["alive_status", "hp_current", "hp_max", "mp_current", "mp_max"]:
        if compact_text(update.get(field)) and not is_emptyish(update.get(field)):
            risky_fields.append(field)
    if normalize_list(update.get("status_effects", [])):
        risky_fields.append("status_effects")

    if mode == "off":
        add_pending_update(state, update, ["all"])
        mark_processed(state, update_id)
        return {"status": "pending", "update_id": update_id, "applied_fields": [], "pending_fields": ["all"]}

    target = ensure_character(state.setdefault("characters", []), update)
    applied = apply_update_fields(target, update, allow_risky=(mode == "all"))

    pending_fields: list[str] = []
    if mode == "safe" and risky_fields:
        pending_fields = risky_fields
        add_pending_update(state, update, pending_fields)

    # 已经进入 pending，也要标记处理，避免刷新历史聊天时重复塞 pending。
    mark_processed(state, update_id)

    if pending_fields and applied:
        status = "partial"
    elif pending_fields:
        status = "pending"
    elif applied:
        status = "applied"
    else:
        status = "noop"
    return {"status": status, "update_id": update_id, "applied_fields": applied, "pending_fields": pending_fields}


def resolve_pending_update(state: dict[str, Any], update_id: str, action: str) -> dict[str, Any]:
    pending = state.setdefault("pending_updates", [])
    target_item = None
    for item in pending:
        if compact_text(item.get("update_id")) == update_id:
            target_item = item
            break
    if target_item is None:
        return {"status": "missing", "update_id": update_id}

    pending.remove(target_item)
    result: dict[str, Any]
    if action == "ignore":
        mark_processed(state, update_id)
        result = {"status": "ignored", "update_id": update_id}
    else:
        update = dict(target_item.get("update") or {})
        update["update_id"] = update_id
        target = ensure_character(state.setdefault("characters", []), update)
        applied = apply_update_fields(target, normalize_update(update), allow_risky=True)
        mark_processed(state, update_id)
        result = {"status": "applied", "update_id": update_id, "applied_fields": applied}
    return result


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"request": request, "state": get_state()})


@app.get("/api/state")
async def api_get_state() -> dict[str, Any]:
    return {"ok": True, **get_state()}


@app.post("/api/state")
async def api_save_state(payload: StatusPanelPayload) -> dict[str, Any]:
    try:
        state = save_state(payload.model_dump())
    except OSError as exc:
        raise HTTPException(status_code=500, detail="角色状态保存失败，请检查文件权限。") from exc
    return {"ok": True, **state}


@app.get("/api/field-schema")
async def api_get_field_schema() -> dict[str, Any]:
    return {"ok": True, "schema": get_field_schema()}


@app.post("/api/field-schema")
async def api_save_field_schema(payload: FieldSchemaPayload) -> dict[str, Any]:
    try:
        schema = save_field_schema(payload.model_dump())
    except OSError as exc:
        raise HTTPException(status_code=500, detail="表格列配置保存失败，请检查文件权限。") from exc
    return {"ok": True, "schema": schema}


@app.get("/api/summary")
async def api_get_summary() -> dict[str, Any]:
    state = get_state()
    return {"ok": True, "summary": build_status_summary(state)}


@app.post("/api/apply-update")
async def api_apply_update(payload: ApplyUpdatePayload) -> dict[str, Any]:
    state = get_state()
    mode = payload.mode or state.get("settings", {}).get("auto_apply_mode", "safe")
    result = apply_update_to_state(state, payload.update, mode)
    try:
        write_json(STATE_PATH, state)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="状态更新保存失败，请检查文件权限。") from exc
    return {"ok": True, "result": result, **state}


@app.get("/api/pending-updates")
async def api_pending_updates() -> dict[str, Any]:
    state = get_state()
    return {"ok": True, "pending_updates": state.get("pending_updates", [])}


@app.post("/api/pending-updates/resolve")
async def api_resolve_pending(payload: ResolvePendingPayload) -> dict[str, Any]:
    state = get_state()
    action = payload.action if payload.action in {"apply", "ignore"} else "apply"
    result = resolve_pending_update(state, payload.update_id, action)
    try:
        write_json(STATE_PATH, state)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="待确认更新保存失败，请检查文件权限。") from exc
    return {"ok": True, "result": result, **state}
