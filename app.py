import asyncio
import json
import logging
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request


def get_runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        try:
            exe_dir.mkdir(parents=True, exist_ok=True)
            probe_path = exe_dir / ".xuqi_write_test"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink(missing_ok=True)
            return exe_dir
        except OSError:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                return Path(local_app_data) / "XuqiLLMChat"
            return Path.home() / "AppData" / "Local" / "XuqiLLMChat"
    return Path(__file__).resolve().parent


def get_resource_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


BASE_DIR = get_runtime_base_dir()
RESOURCE_DIR = get_resource_dir()
DATA_DIR = BASE_DIR / "data"
SLOTS_DIR = DATA_DIR / "slots"
STATIC_DIR = BASE_DIR / "static"
RESOURCE_STATIC_DIR = RESOURCE_DIR / "static"
TEMPLATES_DIR = RESOURCE_DIR / "templates"
UPLOAD_DIR = STATIC_DIR / "uploads"
SPRITES_DIR = STATIC_DIR / "sprites"
CARDS_DIR = BASE_DIR / "cards"
RESOURCE_CARDS_DIR = RESOURCE_DIR / "cards"
ROLE_CARD_EXTENSIONS = {".json", ".txt"}
SLOT_META_PATH = DATA_DIR / "save_slots.json"
EXPORT_DIR = BASE_DIR / "exports"
LEGACY_PERSONA_PATH = DATA_DIR / "persona.json"
LEGACY_CONVERSATION_PATH = DATA_DIR / "conversations.json"
LEGACY_SETTINGS_PATH = DATA_DIR / "settings.json"
LEGACY_MEMORIES_PATH = DATA_DIR / "memories.json"
LEGACY_WORLDBOOK_PATH = DATA_DIR / "worldbook.json"
LEGACY_CURRENT_CARD_PATH = DATA_DIR / "current_role_card.json"
SLOT_MIGRATION_MARKER_PATH = DATA_DIR / ".slot_migration_done"

ALLOWED_EMBEDDING_FIELDS = ("title", "content", "tags", "notes")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_BACKGROUND_SCHEMES = {"http", "https"}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
REQUEST_RETRY_ATTEMPTS = 5
REQUEST_RETRY_BASE_DELAY_SECONDS = 1.0
DEFAULT_SPRITE_BASE_PATH = "/static/sprites"
DEFAULT_SLOT_IDS = ("slot_1", "slot_2", "slot_3")

logger = logging.getLogger("xuqi_llm_chat")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)


def bootstrap_runtime_layout() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if RESOURCE_STATIC_DIR.exists() and not (STATIC_DIR / "styles.css").exists():
        shutil.copytree(RESOURCE_STATIC_DIR, STATIC_DIR, dirs_exist_ok=True)

    if RESOURCE_CARDS_DIR.exists() and not CARDS_DIR.exists():
        shutil.copytree(RESOURCE_CARDS_DIR, CARDS_DIR, dirs_exist_ok=True)

    if (RESOURCE_DIR / "data").exists() and not DATA_DIR.exists():
        shutil.copytree(RESOURCE_DIR / "data", DATA_DIR, dirs_exist_ok=True)

DEFAULT_PERSONA = {
    "name": "Xuxu",
    "system_prompt": (
        "You are a gentle, patient, and attentive AI companion. "
        "Respond naturally, show care, and avoid overly templated phrasing."
    ),
    "greeting": "What would you like to talk about today? I am here with you.",
}

DEFAULT_SETTINGS = {
    "llm_base_url": "",
    "llm_api_key": "",
    "llm_model": "",
    "theme": "light",
    "temperature": 0.85,
    "history_limit": 20,
    "request_timeout": 120,
    "demo_mode": False,
    "ui_opacity": 0.84,
    "background_image_url": "",
    "background_overlay": 0.42,
    "embedding_base_url": "",
    "embedding_api_key": "",
    "embedding_model": "",
    "embedding_fields": ["title", "content", "tags"],
    "retrieval_top_k": 4,
    "rerank_enabled": False,
    "rerank_base_url": "",
    "rerank_api_key": "",
    "rerank_model": "",
    "rerank_top_n": 3,
    "sprite_enabled": True,
    "sprite_base_path": DEFAULT_SPRITE_BASE_PATH,
}


def default_slot_registry() -> dict[str, Any]:
    slots = [{"id": slot_id, "name": f"Slot {index}"} for index, slot_id in enumerate(DEFAULT_SLOT_IDS, start=1)]
    return {"active_slot": DEFAULT_SLOT_IDS[0], "slots": slots}


def default_sprite_base_path_for_slot(slot_id: str | None = None) -> str:
    target = sanitize_slot_id(slot_id, DEFAULT_SLOT_IDS[0] if DEFAULT_SLOT_IDS else "slot_1")
    return f"{DEFAULT_SPRITE_BASE_PATH}/{target}"


def sprite_dir_path(slot_id: str | None = None) -> Path:
    target = sanitize_slot_id(slot_id, DEFAULT_SLOT_IDS[0] if DEFAULT_SLOT_IDS else "slot_1")
    return SPRITES_DIR / target


def sanitize_sprite_filename_tag(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    return text[:64].strip(" ._")


def list_sprite_assets(slot_id: str | None = None) -> list[dict[str, Any]]:
    directory = sprite_dir_path(slot_id)
    if not directory.exists():
        return []

    items: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            continue
        items.append(
            {
                "filename": path.name,
                "tag": path.stem,
                "url": f"{default_sprite_base_path_for_slot(slot_id)}/{path.name}",
                "size": path.stat().st_size,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def default_role_card() -> dict[str, Any]:
    return {
        "name": "",
        "description": "",
        "personality": "",
        "first_mes": "",
        "mes_example": "",
        "scenario": "",
        "creator_notes": "",
        "tags": [],
        "plotStages": {
            "A": {"description": "", "rules": ""},
            "B": {"description": "", "rules": ""},
            "C": {"description": "", "rules": ""},
        },
        "personas": {
            "1": {
                "name": "",
                "description": "",
                "personality": "",
                "scenario": "",
                "creator_notes": "",
            },
            "2": {
                "name": "",
                "description": "",
                "personality": "",
                "scenario": "",
                "creator_notes": "",
            },
            "3": {
                "name": "",
                "description": "",
                "personality": "",
                "scenario": "",
                "creator_notes": "",
            },
        },
    }


def load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("读取 JSON 失败，使用默认值: %s (%s)", path, exc)
        return default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def persist_json(path: Path, payload: Any, *, detail: str, status_code: int = 500) -> None:
    try:
        write_json(path, payload)
    except OSError as exc:
        logger.exception("写入 JSON 失败: %s", path)
        raise HTTPException(status_code=status_code, detail=detail) from exc


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def sanitize_background_image_url(value: Any, *, strict: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if text.startswith("/static/uploads/"):
        return text

    parsed = urlparse(text)
    if parsed.scheme in ALLOWED_BACKGROUND_SCHEMES and parsed.netloc:
        return text

    if strict:
        raise HTTPException(
            status_code=400,
            detail="背景图地址只允许 http/https 远程地址或 /static/uploads/ 本地图片路径。",
        )
    return ""


def sanitize_embedding_fields(value: Any) -> list[str]:
    raw_fields = value if isinstance(value, list) else DEFAULT_SETTINGS["embedding_fields"]
    normalized_fields: list[str] = []
    for field_name in raw_fields:
        field_value = str(field_name).strip()
        if field_value in ALLOWED_EMBEDDING_FIELDS and field_value not in normalized_fields:
            normalized_fields.append(field_value)
    return normalized_fields or list(DEFAULT_SETTINGS["embedding_fields"])


def sanitize_settings(raw: dict[str, Any] | None, *, strict: bool = False, slot_id: str | None = None) -> dict[str, Any]:
    settings = DEFAULT_SETTINGS.copy()
    if raw:
        settings.update(raw)

    default_sprite_path = default_sprite_base_path_for_slot(slot_id)
    sprite_base_path = str(settings.get("sprite_base_path", default_sprite_path)).strip() or default_sprite_path
    if sprite_base_path == DEFAULT_SPRITE_BASE_PATH:
        sprite_base_path = default_sprite_path

    return {
        "llm_base_url": str(settings.get("llm_base_url", "")).strip(),
        "llm_api_key": str(settings.get("llm_api_key", "")).strip(),
        "llm_model": str(settings.get("llm_model", "")).strip(),
        "theme": "dark" if str(settings.get("theme", "light")).strip() == "dark" else "light",
        "temperature": clamp_float(settings.get("temperature"), 0.0, 2.0, 0.85),
        "history_limit": clamp_int(settings.get("history_limit"), 1, 100, 20),
        "request_timeout": clamp_int(settings.get("request_timeout"), 10, 600, 120),
        "demo_mode": parse_bool(settings.get("demo_mode"), False),
        "ui_opacity": clamp_float(settings.get("ui_opacity"), 0.2, 1.0, 0.84),
        "background_image_url": sanitize_background_image_url(
            settings.get("background_image_url", ""),
            strict=strict,
        ),
        "background_overlay": clamp_float(settings.get("background_overlay"), 0.0, 0.85, 0.42),
        "sprite_enabled": parse_bool(settings.get("sprite_enabled"), True),
        "sprite_base_path": sprite_base_path,
        "embedding_base_url": str(settings.get("embedding_base_url", "")).strip(),
        "embedding_api_key": str(settings.get("embedding_api_key", "")).strip(),
        "embedding_model": str(settings.get("embedding_model", "")).strip(),
        "embedding_fields": sanitize_embedding_fields(settings.get("embedding_fields")),
        "retrieval_top_k": clamp_int(settings.get("retrieval_top_k"), 1, 12, 4),
        "rerank_enabled": parse_bool(settings.get("rerank_enabled"), False),
        "rerank_base_url": str(settings.get("rerank_base_url", "")).strip(),
        "rerank_api_key": str(settings.get("rerank_api_key", "")).strip(),
        "rerank_model": str(settings.get("rerank_model", "")).strip(),
        "rerank_top_n": clamp_int(settings.get("rerank_top_n"), 1, 12, 3),
    }


def sanitize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_tags = value.replace("?", ",").split(",")
    elif isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = []

    tags: list[str] = []
    for item in raw_tags:
        text = str(item).strip()
        if text and text not in tags:
            tags.append(text)
    return tags


def sanitize_memories(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        memory_id = str(item.get("id", "")).strip() or f"memory-{index}"
        items.append(
            {
                "id": memory_id,
                "title": str(item.get("title", "")).strip(),
                "content": str(item.get("content", "")).strip(),
                "tags": sanitize_tags(item.get("tags", [])),
                "notes": str(item.get("notes", "")).strip(),
            }
        )
    return items


DEFAULT_WORLDBOOK_SETTINGS = {
    "enabled": True,
    "max_hits": 3,
    "default_case_sensitive": False,
    "default_whole_word": False,
    "default_match_mode": "any",
    "default_secondary_mode": "all",
}


def default_worldbook_store() -> dict[str, Any]:
    return {"settings": dict(DEFAULT_WORLDBOOK_SETTINGS), "entries": []}


def sanitize_worldbook_settings(raw: Any) -> dict[str, Any]:
    settings = dict(DEFAULT_WORLDBOOK_SETTINGS)
    if not isinstance(raw, dict):
        return settings

    settings["enabled"] = bool(raw.get("enabled", settings["enabled"]))
    try:
        settings["max_hits"] = max(1, min(20, int(raw.get("max_hits", settings["max_hits"]))))
    except (TypeError, ValueError):
        settings["max_hits"] = DEFAULT_WORLDBOOK_SETTINGS["max_hits"]

    settings["default_case_sensitive"] = bool(raw.get("default_case_sensitive", settings["default_case_sensitive"]))
    settings["default_whole_word"] = bool(raw.get("default_whole_word", settings["default_whole_word"]))

    default_match_mode = str(raw.get("default_match_mode", settings["default_match_mode"])).strip().lower()
    settings["default_match_mode"] = default_match_mode if default_match_mode in {"any", "all"} else "any"

    default_secondary_mode = str(raw.get("default_secondary_mode", settings["default_secondary_mode"])).strip().lower()
    settings["default_secondary_mode"] = default_secondary_mode if default_secondary_mode in {"any", "all"} else "all"
    return settings


def sanitize_worldbook_entry(raw: Any, *, index: int, settings: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    trigger = str(raw.get("trigger", "")).strip()
    content = str(raw.get("content", "")).strip()
    if not trigger or not content:
        return None

    title = str(raw.get("title", "")).strip() or f"词条 {index}"
    secondary_trigger = str(raw.get("secondary_trigger", "")).strip()
    comment = str(raw.get("comment", "")).strip()
    entry_id = str(raw.get("id", "")).strip() or f"worldbook-{index}"

    match_mode = str(raw.get("match_mode", settings["default_match_mode"])).strip().lower()
    if match_mode not in {"any", "all"}:
        match_mode = settings["default_match_mode"]

    secondary_mode = str(raw.get("secondary_mode", settings["default_secondary_mode"])).strip().lower()
    if secondary_mode not in {"any", "all"}:
        secondary_mode = settings["default_secondary_mode"]

    try:
        priority = int(raw.get("priority", 100))
    except (TypeError, ValueError):
        priority = 100

    return {
        "id": entry_id,
        "title": title[:80],
        "trigger": trigger,
        "secondary_trigger": secondary_trigger,
        "content": content,
        "enabled": bool(raw.get("enabled", True)),
        "priority": max(0, min(9999, priority)),
        "case_sensitive": bool(raw.get("case_sensitive", settings["default_case_sensitive"])),
        "whole_word": bool(raw.get("whole_word", settings["default_whole_word"])),
        "match_mode": match_mode,
        "secondary_mode": secondary_mode,
        "comment": comment[:240],
    }


def sanitize_worldbook_store(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and ("settings" in raw or "entries" in raw):
        settings = sanitize_worldbook_settings(raw.get("settings", {}))
        raw_entries = raw.get("entries", [])
    elif isinstance(raw, dict):
        settings = sanitize_worldbook_settings({})
        raw_entries = [{"trigger": key, "content": value} for key, value in raw.items()]
    elif isinstance(raw, list):
        settings = sanitize_worldbook_settings({})
        raw_entries = raw
    else:
        return default_worldbook_store()

    entries: list[dict[str, Any]] = []
    if isinstance(raw_entries, list):
        for index, item in enumerate(raw_entries, start=1):
            cleaned = sanitize_worldbook_entry(item, index=index, settings=settings)
            if cleaned:
                entries.append(cleaned)

    return {"settings": settings, "entries": entries}


def sanitize_worldbook(raw: Any) -> dict[str, str]:
    store = sanitize_worldbook_store(raw)
    cleaned: dict[str, str] = {}
    for item in store["entries"]:
        if item.get("enabled", True):
            cleaned[str(item["trigger"]).strip()] = str(item["content"]).strip()
    return cleaned


def normalize_match_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.strip().lower()
    return re.sub(r"\s+", "", text)


def _deprecated_split_trigger_aliases(trigger: Any) -> list[str]:
    text = unicodedata.normalize("NFKC", str(trigger or ""))
    aliases = [part.strip() for part in re.split(r"[|,，、/\n]+", text) if part.strip()]
    return aliases or ([text.strip()] if text.strip() else [])


def sanitize_slot_id(value: Any, default: str | None = None) -> str:
    slot_id = str(value or "").strip()
    if slot_id in DEFAULT_SLOT_IDS:
        return slot_id
    return default or DEFAULT_SLOT_IDS[0]


def sanitize_slot_registry(raw: Any) -> dict[str, Any]:
    default = default_slot_registry()
    if not isinstance(raw, dict):
        return default

    raw_slots = raw.get("slots", [])
    seen: set[str] = set()
    slots: list[dict[str, str]] = []
    if isinstance(raw_slots, list):
        for index, item in enumerate(raw_slots, start=1):
            if not isinstance(item, dict):
                continue
            slot_id = sanitize_slot_id(item.get("id"), "")
            if not slot_id or slot_id in seen:
                continue
            seen.add(slot_id)
            name = str(item.get("name", "")).strip() or f"存档 {index}"
            slots.append({"id": slot_id, "name": name[:32]})

    for index, slot_id in enumerate(DEFAULT_SLOT_IDS, start=1):
        if slot_id not in seen:
            slots.append({"id": slot_id, "name": f"存档 {index}"})

    active_slot = sanitize_slot_id(raw.get("active_slot"), DEFAULT_SLOT_IDS[0])
    return {"active_slot": active_slot, "slots": slots}


def get_slot_registry() -> dict[str, Any]:
    return sanitize_slot_registry(read_json(SLOT_META_PATH, default_slot_registry()))


def save_slot_registry(registry: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_slot_registry(registry)
    persist_json(
        SLOT_META_PATH,
        sanitized,
        detail="存档列表保存失败，请检查磁盘空间或文件权限。",
    )
    return sanitized


def get_active_slot_id() -> str:
    return get_slot_registry()["active_slot"]


def get_slot_name(slot_id: str | None = None) -> str:
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    for item in get_slot_registry()["slots"]:
        if item["id"] == target:
            return item["name"]
    return target


def slot_summary(slot_id: str | None = None) -> dict[str, Any]:
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    current_card = get_current_card(target)
    return {
        "id": target,
        "name": get_slot_name(target),
        "persona_name": get_persona(target).get("name", ""),
        "memory_count": len(get_memories(target)),
        "worldbook_count": len(get_worldbook(target)),
        "conversation_count": len(get_conversation(target)),
        "current_card_name": current_card.get("source_name", ""),
    }


def get_slot_dir(slot_id: str | None = None) -> Path:
    return SLOTS_DIR / sanitize_slot_id(slot_id, get_active_slot_id())


def persona_path(slot_id: str | None = None) -> Path:
    return get_slot_dir(slot_id) / "persona.json"


def conversation_path(slot_id: str | None = None) -> Path:
    return get_slot_dir(slot_id) / "conversations.json"


def settings_path(slot_id: str | None = None) -> Path:
    return get_slot_dir(slot_id) / "settings.json"


def memories_path(slot_id: str | None = None) -> Path:
    return get_slot_dir(slot_id) / "memories.json"


def worldbook_path(slot_id: str | None = None) -> Path:
    return get_slot_dir(slot_id) / "worldbook.json"


def current_card_path(slot_id: str | None = None) -> Path:
    return get_slot_dir(slot_id) / "current_role_card.json"


def reset_slot_data(slot_id: str) -> dict[str, Any]:
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    persist_json(persona_path(target), DEFAULT_PERSONA, detail="存档重置失败：无法重置人设。")
    persist_json(conversation_path(target), [], detail="存档重置失败：无法清空聊天记录。")
    persist_json(settings_path(target), sanitize_settings(DEFAULT_SETTINGS, slot_id=target), detail="存档重置失败：无法重置配置。")
    persist_json(memories_path(target), [], detail="存档重置失败：无法清空记忆库。")
    persist_json(worldbook_path(target), {}, detail="存档重置失败：无法清空世界书。")
    persist_json(current_card_path(target), {}, detail="存档重置失败：无法清空角色卡记录。")
    return slot_summary(target)


def normalize_role_card(raw: Any) -> dict[str, Any]:
    card = default_role_card()
    if not isinstance(raw, dict):
        return card

    for key in [
        "name",
        "description",
        "personality",
        "first_mes",
        "mes_example",
        "scenario",
        "creator_notes",
    ]:
        card[key] = str(raw.get(key, "")).strip()

    card["tags"] = sanitize_tags(raw.get("tags", []))

    plot_stages = raw.get("plotStages", {})
    if isinstance(plot_stages, dict):
        for key in card["plotStages"]:
            value = plot_stages.get(key, {})
            if isinstance(value, dict):
                card["plotStages"][key]["description"] = str(value.get("description", "")).strip()
                card["plotStages"][key]["rules"] = str(value.get("rules", "")).strip()

    personas = raw.get("personas", {})
    if isinstance(personas, dict):
        persona_items: list[tuple[str, Any]]
        if any(str(key) in card["personas"] for key in personas):
            persona_items = [(key, personas.get(key, {})) for key in card["personas"]]
        else:
            persona_items = list(personas.items())[: len(card["personas"])]

        for slot, item in zip(card["personas"], persona_items):
            source_key, value = item
            if isinstance(value, dict):
                source_name = str(source_key).strip()
                raw_name = str(value.get("name", "")).strip()
                display_name = raw_name or source_name
                if not display_name or re.fullmatch(r"[A-Z]", display_name):
                    extracted_name = extract_persona_name_from_fields(
                        str(value.get("description", "")).strip(),
                        str(value.get("scenario", "")).strip(),
                        str(value.get("personality", "")).strip(),
                    )
                    if extracted_name:
                        display_name = extracted_name
                    elif source_name and source_name not in {"1", "2", "3"}:
                        display_name = source_name
                card["personas"][slot]["name"] = display_name
                card["personas"][slot]["description"] = str(value.get("description", "")).strip()
                card["personas"][slot]["personality"] = str(value.get("personality", "")).strip()
                card["personas"][slot]["scenario"] = str(value.get("scenario", "")).strip()
                card["personas"][slot]["creator_notes"] = str(value.get("creator_notes", "")).strip()

    return card


def extract_persona_name_from_fields(*texts: str) -> str:
    patterns = [
        r"姓名[：:]\s*([^\n（(，,。；;]{1,16})",
        r"名为([^\n（(，,。；;]{1,16})",
        r"^([^\n（(，,。；;]{1,16})（",
        r"^([^\n（(，,。；;]{1,16})，",
    ]
    for text in texts:
        content = str(text or "").strip()
        if not content:
            continue
        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1).strip()
    return ""

def is_legacy_demo_reply(content: str) -> bool:
    text = str(content or "").strip()
    if not text:
        return False

    markers = [
        "收到啦：",
        "我现在处于本地演示模式",
        "Config 页面填写聊天模型",
        "鏀跺埌鍟",
        "鏈湴演示模式",
        "Config 椤甸潰",
    ]
    return any(marker in text for marker in markers)


def is_garbled_placeholder_message(content: str) -> bool:
    text = str(content or "").strip()
    if len(text) < 3:
        return False
    return set(text) <= {"?", "？"}


def normalize_legacy_message_content(role: str, content: str) -> str:
    text = str(content or "")
    if role != "assistant":
        return text

    stripped = text.lstrip()
    if stripped.startswith("??????") or stripped.startswith("？？？？？？"):
        remainder = stripped.lstrip("?？").lstrip(":：").lstrip()
        return f"出错了：{remainder}" if remainder else "出错了。"
    return text


def sanitize_conversation(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    cleaned: list[dict[str, Any]] = []
    changed = False
    skip_next_assistant = False

    for item in raw:
        if not isinstance(item, dict):
            changed = True
            continue

        role = str(item.get("role", "")).strip()
        content = normalize_legacy_message_content(role, str(item.get("content", "")))
        created_at = str(item.get("created_at", "")).strip()

        if role not in {"user", "assistant", "system"}:
            changed = True
            continue

        if role == "assistant" and skip_next_assistant:
            changed = True
            skip_next_assistant = False
            continue

        if role == "user" and is_garbled_placeholder_message(content):
            changed = True
            skip_next_assistant = True
            continue

        if role == "assistant" and is_legacy_demo_reply(content):
            changed = True
            continue

        cleaned.append(
            {
                "role": role,
                "content": content,
                "created_at": created_at,
            }
        )

    if changed:
        logger.info("检测到旧演示消息，已从聊天记录中过滤。")
    return cleaned


def slot_looks_uninitialized(slot_id: str) -> bool:
    return (
        get_persona(slot_id) == DEFAULT_PERSONA
        and get_conversation(slot_id) == []
        and get_settings(slot_id) == sanitize_settings(DEFAULT_SETTINGS, slot_id=slot_id)
        and get_memories(slot_id) == []
        and get_worldbook(slot_id) == {}
        and read_json(current_card_path(slot_id), {}) == {}
    )


def has_legacy_root_data() -> bool:
    return any(
        path.exists()
        for path in (
            LEGACY_PERSONA_PATH,
            LEGACY_CONVERSATION_PATH,
            LEGACY_SETTINGS_PATH,
            LEGACY_MEMORIES_PATH,
            LEGACY_WORLDBOOK_PATH,
            LEGACY_CURRENT_CARD_PATH,
        )
    )


def migrate_legacy_root_to_primary_slot() -> None:
    if SLOT_MIGRATION_MARKER_PATH.exists():
        return
    if not has_legacy_root_data():
        SLOT_MIGRATION_MARKER_PATH.write_text("no-legacy-data", encoding="utf-8")
        return
    if not slot_looks_uninitialized(DEFAULT_SLOT_IDS[0]):
        SLOT_MIGRATION_MARKER_PATH.write_text("slot-1-already-in-use", encoding="utf-8")
        return

    persist_json(
        persona_path(DEFAULT_SLOT_IDS[0]),
        read_json(LEGACY_PERSONA_PATH, DEFAULT_PERSONA),
        detail="旧版 persona 迁移失败，请检查磁盘空间或文件权限。",
    )
    persist_json(
        conversation_path(DEFAULT_SLOT_IDS[0]),
        sanitize_conversation(read_json(LEGACY_CONVERSATION_PATH, [])),
        detail="旧版聊天记录迁移失败，请检查磁盘空间或文件权限。",
    )
    persist_json(
        settings_path(DEFAULT_SLOT_IDS[0]),
        sanitize_settings(read_json(LEGACY_SETTINGS_PATH, {}), slot_id=DEFAULT_SLOT_IDS[0]),
        detail="旧版 settings 迁移失败，请检查磁盘空间或文件权限。",
    )
    persist_json(
        memories_path(DEFAULT_SLOT_IDS[0]),
        sanitize_memories(read_json(LEGACY_MEMORIES_PATH, [])),
        detail="旧版记忆库迁移失败，请检查磁盘空间或文件权限。",
    )
    persist_json(
        worldbook_path(DEFAULT_SLOT_IDS[0]),
        sanitize_worldbook(read_json(LEGACY_WORLDBOOK_PATH, {})),
        detail="旧版世界书迁移失败，请检查磁盘空间或文件权限。",
    )
    persist_json(
        current_card_path(DEFAULT_SLOT_IDS[0]),
        read_json(LEGACY_CURRENT_CARD_PATH, {}),
        detail="旧版角色卡迁移失败，请检查磁盘空间或文件权限。",
    )
    SLOT_MIGRATION_MARKER_PATH.write_text("migrated-slot-1", encoding="utf-8")
    logger.info("已将旧版 data 根目录内容迁移到 slot_1。")


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SPRITES_DIR.mkdir(parents=True, exist_ok=True)
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    if not SLOT_META_PATH.exists():
        write_json(SLOT_META_PATH, default_slot_registry())

    registry = get_slot_registry()
    if registry != read_json(SLOT_META_PATH, {}):
        write_json(SLOT_META_PATH, registry)

    for slot_id in DEFAULT_SLOT_IDS:
        slot_dir = get_slot_dir(slot_id)
        slot_dir.mkdir(parents=True, exist_ok=True)
        sprite_dir_path(slot_id).mkdir(parents=True, exist_ok=True)
        if not persona_path(slot_id).exists():
            write_json(persona_path(slot_id), DEFAULT_PERSONA)
        if not conversation_path(slot_id).exists():
            write_json(conversation_path(slot_id), [])
        if not settings_path(slot_id).exists():
            write_json(settings_path(slot_id), sanitize_settings(DEFAULT_SETTINGS, slot_id=slot_id))
        else:
            normalized_settings = sanitize_settings(read_json(settings_path(slot_id), {}), slot_id=slot_id)
            if normalized_settings != read_json(settings_path(slot_id), {}):
                write_json(settings_path(slot_id), normalized_settings)
        if not memories_path(slot_id).exists():
            write_json(memories_path(slot_id), [])
        if not worldbook_path(slot_id).exists():
            write_json(worldbook_path(slot_id), {})
        if not current_card_path(slot_id).exists():
            write_json(current_card_path(slot_id), {})
    migrate_legacy_root_to_primary_slot()


def get_persona(slot_id: str | None = None) -> dict[str, Any]:
    persona = DEFAULT_PERSONA.copy()
    persona.update(read_json(persona_path(slot_id), {}))
    return persona


def get_conversation(slot_id: str | None = None) -> list[dict[str, Any]]:
    path = conversation_path(slot_id)
    history = sanitize_conversation(read_json(path, []))
    stored = read_json(path, [])
    if history != stored:
        persist_json(
            path,
            history,
            detail="聊天记录整理失败，请检查磁盘空间或文件权限。",
        )
    return history


def get_settings(slot_id: str | None = None) -> dict[str, Any]:
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    return sanitize_settings(read_json(settings_path(target), {}), slot_id=target)


def get_memories(slot_id: str | None = None) -> list[dict[str, Any]]:
    return sanitize_memories(read_json(memories_path(slot_id), []))


def get_worldbook(slot_id: str | None = None) -> dict[str, str]:
    return sanitize_worldbook(get_worldbook_store(slot_id))


def get_worldbook_store(slot_id: str | None = None) -> dict[str, Any]:
    return sanitize_worldbook_store(read_json(worldbook_path(slot_id), {}))


def get_worldbook_entries(slot_id: str | None = None) -> list[dict[str, Any]]:
    return get_worldbook_store(slot_id)["entries"]


def get_worldbook_settings(slot_id: str | None = None) -> dict[str, Any]:
    return get_worldbook_store(slot_id)["settings"]


def save_memories(items: list[dict[str, Any]], slot_id: str | None = None) -> list[dict[str, Any]]:
    sanitized = sanitize_memories(items)
    persist_json(
        memories_path(slot_id),
        sanitized,
        detail="记忆库保存失败，请检查磁盘空间或文件权限。",
    )
    return sanitized


def save_worldbook(entries: dict[str, str], slot_id: str | None = None) -> dict[str, str]:
    sanitized = sanitize_worldbook(entries)
    persist_json(
        worldbook_path(slot_id),
        {"settings": get_worldbook_settings(slot_id), "entries": [{"trigger": key, "content": value} for key, value in sanitized.items()]},
        detail="世界书保存失败，请检查磁盘空间或文件权限。",
    )
    return sanitized


def save_worldbook_store(store: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    sanitized = sanitize_worldbook_store(store)
    persist_json(
        worldbook_path(slot_id),
        sanitized,
        detail="世界书保存失败，请检查磁盘空间或文件权限。",
    )
    return sanitized


def save_worldbook_entries(entries: list[dict[str, Any]], slot_id: str | None = None) -> list[dict[str, Any]]:
    store = get_worldbook_store(slot_id)
    store["entries"] = entries
    return save_worldbook_store(store, slot_id)["entries"]


def save_worldbook_settings(settings: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    store = get_worldbook_store(slot_id)
    store["settings"] = settings
    return save_worldbook_store(store, slot_id)["settings"]


def get_current_card(slot_id: str | None = None) -> dict[str, Any]:
    data = read_json(current_card_path(slot_id), {})
    if not isinstance(data, dict):
        return {"source_name": "", "raw": default_role_card()}
    return {
        "source_name": str(data.get("source_name", "")).strip(),
        "raw": normalize_role_card(data.get("raw", {})),
    }

def list_role_card_files() -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for path in sorted(CARDS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ROLE_CARD_EXTENSIONS:
            continue
        cards.append({"filename": path.name, "path": str(path)})
    return cards


def read_role_card_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise HTTPException(status_code=500, detail="角色卡文件读取失败。") from exc
    raise HTTPException(status_code=400, detail="角色卡文件编码无法识别，请改成 UTF-8 或 UTF-8 with BOM。")


def repair_deepseek_card_json(text: str) -> str:
    repaired = text.strip()
    if not repaired:
        return repaired

    if not repaired.startswith("{"):
        repaired = "{\n" + repaired

    if not repaired.endswith("}"):
        repaired = repaired.rstrip(", \r\n\t") + "\n}"

    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    marker = '"plotStages"'
    if marker in repaired:
        marker_index = repaired.find(marker)
        close_index = repaired.rfind("}", 0, marker_index)
        open_index = repaired.rfind("{", 0, marker_index)
        if close_index != -1 and open_index != -1 and close_index > open_index:
            repaired = repaired[:close_index] + repaired[close_index + 1 :]
            repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    return repaired


def extract_role_card_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    candidate = data
    if isinstance(data.get("data"), dict):
        candidate = data["data"]
    else:
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get("data"), dict):
                candidate = value["data"]
                break

    if not isinstance(candidate, dict):
        return {}

    merged = dict(candidate)
    for key in ["name", "description", "personality", "first_mes", "mes_example", "scenario", "creator_notes", "tags", "plotStages", "personas"]:
        if not merged.get(key) and data.get(key):
            merged[key] = data.get(key)

    return merged


def parse_role_card_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="角色卡 JSON 不能为空。")

    try:
        data = json.loads(raw)
    except ValueError:
        repaired = repair_deepseek_card_json(raw)
        try:
            data = json.loads(repaired)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"角色卡 JSON 解析失败：{exc}") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="角色卡 JSON 顶层必须是对象。")
    return normalize_role_card(extract_role_card_payload(data))

def build_persona_from_role_card(card: dict[str, Any]) -> dict[str, str]:
    sections: list[str] = []

    description = str(card.get("description", "")).strip()
    personality = str(card.get("personality", "")).strip()
    scenario = str(card.get("scenario", "")).strip()
    creator_notes = str(card.get("creator_notes", "")).strip()
    mes_example = str(card.get("mes_example", "")).strip()

    if description:
        sections.append(f"Character Description: {description}")
    if personality:
        sections.append(f"Personality: {personality}")
    if scenario:
        sections.append(f"Scenario: {scenario}")
    if creator_notes:
        sections.append(f"Creator Notes: {creator_notes}")
    if mes_example:
        sections.append(f"Dialogue Example: {mes_example}")

    plot_stages = card.get("plotStages", {})
    if isinstance(plot_stages, dict):
        stage_lines = []
        for key, value in plot_stages.items():
            if not isinstance(value, dict):
                continue
            desc = str(value.get("description", "")).strip()
            rules = str(value.get("rules", "")).strip()
            if desc or rules:
                line = f"Stage {key}"
                if desc:
                    line += f": {desc}"
                if rules:
                    line += f"; Rules: {rules}"
                stage_lines.append(line)
        if stage_lines:
            sections.append("Plot Stages:\n" + "\n".join(stage_lines))

    personas = card.get("personas", {})
    if isinstance(personas, dict):
        persona_lines = []
        persona_names = []
        for key, value in personas.items():
            if not isinstance(value, dict):
                continue
            name = str(value.get("name", "")).strip() or f"Persona {key}"
            persona_names.append(name)
            desc = str(value.get("description", "")).strip()
            personality_text = str(value.get("personality", "")).strip()
            scenario_text = str(value.get("scenario", "")).strip()
            details = [item for item in [desc, personality_text, scenario_text] if item]
            if details:
                persona_lines.append(f"{name}: {'; '.join(details)}")
        if persona_lines:
            if len(persona_names) >= 3:
                ordered_names = ", ".join(persona_names)
                sections.append(
                    "Multi-Character Cast Rules:\n"
                    "This role card contains multiple active characters.\n"
                    f"Every assistant turn must include all of these characters speaking: {ordered_names}.\n"
                    "Do not omit any of them.\n"
                    "Do not merge different characters into one voice.\n"
                    "Write each speaker in a separate paragraph.\n"
                    "Use the exact format `Name: dialogue` for every paragraph.\n"
                    "Keep the speaking order stable across turns unless the user clearly asks for a different order.\n"
                    "Do not say that only one or two characters are present unless the user explicitly removes the others from the scene."
                )
            else:
                sections.append(
                    "Multi-Character Cast Rules:\n"
                    "This role card contains multiple active characters.\n"
                    "When the scene fits, any of them may appear and speak in the same conversation.\n"
                    "Keep each character's name exactly as listed.\n"
                    "Do not merge different characters into one voice.\n"
                    "Write each speaker in separate paragraphs."
                )
            sections.append("Character Cast:\n" + "\n".join(persona_lines))

    return {
        "name": str(card.get("name", "")).strip() or "Unnamed Character",
        "greeting": str(card.get("first_mes", "")).strip() or "Hello, let's start chatting.",
        "system_prompt": "\n\n".join(section for section in sections if section).strip(),
    }

def build_memories_from_role_card(card: dict[str, Any]) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []

    tags = sanitize_tags(card.get("tags", []))
    base_content = "\n".join(
        part
        for part in [
            str(card.get("description", "")).strip(),
            str(card.get("personality", "")).strip(),
            str(card.get("scenario", "")).strip(),
        ]
        if part
    ).strip()
    if base_content:
        memories.append(
            {
                "id": "card-base",
                "title": str(card.get("name", "")).strip() or "角色基础设定",
                "content": base_content,
                "tags": tags,
                "notes": str(card.get("creator_notes", "")).strip(),
            }
        )

    plot_stages = card.get("plotStages", {})
    if isinstance(plot_stages, dict):
        for key, value in plot_stages.items():
            if not isinstance(value, dict):
                continue
            content = "\n".join(
                part
                for part in [
                    str(value.get("description", "")).strip(),
                    str(value.get("rules", "")).strip(),
                ]
                if part
            ).strip()
            if content:
                memories.append(
                    {
                        "id": f"plot-stage-{key}",
                        "title": f"剧情阶段 {key}",
                        "content": content,
                        "tags": ["plotStage", key],
                        "notes": "",
                    }
                )

    personas = card.get("personas", {})
    if isinstance(personas, dict):
        for key, value in personas.items():
            if not isinstance(value, dict):
                continue
            content = "\n".join(
                part
                for part in [
                    str(value.get("description", "")).strip(),
                    str(value.get("personality", "")).strip(),
                    str(value.get("scenario", "")).strip(),
                ]
                if part
            ).strip()
            if content:
                memories.append(
                    {
                        "id": f"persona-{key}",
                        "title": str(value.get("name", "")).strip() or f"角色 {key}",
                        "content": content,
                        "tags": ["persona", key],
                        "notes": str(value.get("creator_notes", "")).strip(),
                    }
                )

    return sanitize_memories(memories)


def apply_role_card(card: dict[str, Any], *, source_name: str = "", slot_id: str | None = None) -> dict[str, Any]:
    normalized_card = normalize_role_card(card)
    persona = build_persona_from_role_card(normalized_card)
    target_slot = sanitize_slot_id(slot_id, get_active_slot_id())

    persist_json(
        persona_path(target_slot),
        persona,
        detail="写入角色设定失败，请检查 persona.json 权限。",
    )
    persist_json(
        memories_path(target_slot),
        [],
        detail="清空记忆库失败，请检查文件权限。",
    )
    persist_json(
        worldbook_path(target_slot),
        {},
        detail="清空世界书失败，请检查文件权限。",
    )

    current_card = {
        "source_name": source_name,
        "raw": normalized_card,
    }
    persist_json(
        current_card_path(target_slot),
        current_card,
        detail="写入当前角色卡失败，请检查文件权限。",
    )

    return {
        "persona": persona,
        "card": current_card,
    }


def sanitize_runtime_overrides(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    default_sprite_path = default_sprite_base_path_for_slot(get_active_slot_id())
    sprite_base_path = str(source.get("sprite_base_path", default_sprite_path)).strip() or default_sprite_path
    if sprite_base_path == DEFAULT_SPRITE_BASE_PATH:
        sprite_base_path = default_sprite_path
    return {
        "llm_base_url": str(source.get("llm_base_url", "")).strip(),
        "llm_api_key": str(source.get("llm_api_key", "")).strip(),
        "llm_model": str(source.get("llm_model", "")).strip(),
        "temperature": clamp_float(source.get("temperature"), 0.0, 2.0, 0.85),
        "history_limit": clamp_int(source.get("history_limit"), 1, 100, 20),
        "request_timeout": clamp_int(source.get("request_timeout"), 10, 600, 120),
        "demo_mode": parse_bool(source.get("demo_mode"), False),
        "embedding_base_url": str(source.get("embedding_base_url", "")).strip(),
        "embedding_api_key": str(source.get("embedding_api_key", "")).strip(),
        "embedding_model": str(source.get("embedding_model", "")).strip(),
        "embedding_fields": sanitize_embedding_fields(source.get("embedding_fields")),
        "retrieval_top_k": clamp_int(source.get("retrieval_top_k"), 1, 12, 4),
        "rerank_enabled": parse_bool(source.get("rerank_enabled"), False),
        "rerank_base_url": str(source.get("rerank_base_url", "")).strip(),
        "rerank_api_key": str(source.get("rerank_api_key", "")).strip(),
        "rerank_model": str(source.get("rerank_model", "")).strip(),
        "rerank_top_n": clamp_int(source.get("rerank_top_n"), 1, 12, 3),
        "sprite_enabled": parse_bool(source.get("sprite_enabled"), True),
        "sprite_base_path": sprite_base_path,
    }


def resolve_runtime_value(override_value: Any, stored_value: Any, env_key: str | None = None) -> Any:
    if isinstance(override_value, str):
        if override_value.strip():
            return override_value.strip()
    elif override_value is not None:
        return override_value

    if isinstance(stored_value, str):
        if stored_value.strip():
            return stored_value.strip()
    elif stored_value is not None:
        return stored_value

    if env_key:
        return os.getenv(env_key, "").strip()
    return stored_value


def get_runtime_chat_config(runtime_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    overrides = sanitize_runtime_overrides(runtime_overrides)
    return {
        "base_url": resolve_runtime_value(overrides.get("llm_base_url"), settings.get("llm_base_url", ""), "LLM_BASE_URL"),
        "api_key": resolve_runtime_value(overrides.get("llm_api_key"), settings.get("llm_api_key", ""), "LLM_API_KEY"),
        "model": resolve_runtime_value(overrides.get("llm_model"), settings.get("llm_model", ""), "LLM_MODEL"),
        "temperature": overrides.get("temperature") if runtime_overrides else settings.get("temperature", 0.85),
        "history_limit": overrides.get("history_limit") if runtime_overrides else settings.get("history_limit", 20),
        "request_timeout": overrides.get("request_timeout") if runtime_overrides else settings.get("request_timeout", 120),
        "demo_mode": overrides.get("demo_mode") if runtime_overrides else settings.get("demo_mode", False),
        "sprite_enabled": overrides.get("sprite_enabled") if runtime_overrides else settings.get("sprite_enabled", True),
        "sprite_base_path": overrides.get("sprite_base_path") if runtime_overrides else settings.get("sprite_base_path", DEFAULT_SPRITE_BASE_PATH),
    }


def get_runtime_embedding_config(runtime_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    overrides = sanitize_runtime_overrides(runtime_overrides)
    return {
        "base_url": resolve_runtime_value(overrides.get("embedding_base_url"), settings.get("embedding_base_url", ""), "EMBEDDING_BASE_URL"),
        "api_key": resolve_runtime_value(overrides.get("embedding_api_key"), settings.get("embedding_api_key", ""), "EMBEDDING_API_KEY"),
        "model": resolve_runtime_value(overrides.get("embedding_model"), settings.get("embedding_model", ""), "EMBEDDING_MODEL"),
        "request_timeout": overrides.get("request_timeout") if runtime_overrides else settings.get("request_timeout", 120),
        "fields": overrides.get("embedding_fields") if runtime_overrides else settings.get("embedding_fields", DEFAULT_SETTINGS["embedding_fields"]),
        "top_k": overrides.get("retrieval_top_k") if runtime_overrides else settings.get("retrieval_top_k", 4),
    }


def get_runtime_rerank_config(runtime_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    overrides = sanitize_runtime_overrides(runtime_overrides)
    return {
        "enabled": overrides.get("rerank_enabled") if runtime_overrides else settings.get("rerank_enabled", False),
        "base_url": resolve_runtime_value(overrides.get("rerank_base_url"), settings.get("rerank_base_url", ""), "RERANK_BASE_URL"),
        "api_key": resolve_runtime_value(overrides.get("rerank_api_key"), settings.get("rerank_api_key", ""), "RERANK_API_KEY"),
        "model": resolve_runtime_value(overrides.get("rerank_model"), settings.get("rerank_model", ""), "RERANK_MODEL"),
        "request_timeout": overrides.get("request_timeout") if runtime_overrides else settings.get("request_timeout", 120),
        "top_n": overrides.get("rerank_top_n") if runtime_overrides else settings.get("rerank_top_n", 3),
    }


def append_messages(entries: list[tuple[str, str]]) -> None:
    history = get_conversation()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for role, content in entries:
        history.append(
            {
                "role": role,
                "content": content,
                "created_at": timestamp,
            }
        )

    persist_json(
        conversation_path(),
        history,
        detail="聊天记录保存失败，请检查磁盘空间或文件权限。",
    )


def build_memory_text(memory: dict[str, Any], fields: list[str]) -> str:
    parts: list[str] = []
    if "title" in fields and memory.get("title"):
        parts.append(f"标题：{memory['title']}")
    if "content" in fields and memory.get("content"):
        parts.append(f"正文：{memory['content']}")
    if "tags" in fields and memory.get("tags"):
        parts.append(f"标签：{'、'.join(memory['tags'])}")
    if "notes" in fields and memory.get("notes"):
        parts.append(f"备注：{memory['notes']}")
    return "\n".join(parts).strip()


def normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def build_api_url(base_url: str, endpoint: str) -> str:
    clean_base = normalize_base_url(base_url)
    clean_endpoint = endpoint.strip("/")
    if not clean_base:
        return ""
    if clean_base.endswith("/" + clean_endpoint) or clean_base.endswith(clean_endpoint):
        return clean_base
    return f"{clean_base}/{clean_endpoint}"


def build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def should_retry_status_code(status_code: int) -> bool:
    if status_code in {408, 409, 425, 429}:
        return True
    return status_code >= 500


async def request_json(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    request_timeout: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    last_error_detail = ""

    for attempt in range(1, REQUEST_RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=float(request_timeout)) as client:
                response = await client.post(url, headers=build_headers(api_key), json=payload)
                response.raise_for_status()

            try:
                return response.json()
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "Upstream JSON parse failed on attempt %s/%s for %s",
                    attempt,
                    REQUEST_RETRY_ATTEMPTS,
                    url,
                )
        except httpx.HTTPStatusError as exc:
            last_error = exc
            response_text = exc.response.text.strip() if exc.response is not None else ""
            last_error_detail = response_text[:500]
            logger.warning(
                "Upstream request failed on attempt %s/%s for %s: %s | body=%s",
                attempt,
                REQUEST_RETRY_ATTEMPTS,
                url,
                exc,
                last_error_detail or "<empty>",
            )
            status_code = exc.response.status_code if exc.response is not None else 0
            if 400 <= status_code < 500 and not should_retry_status_code(status_code):
                break
        except httpx.HTTPError as exc:
            last_error = exc
            last_error_detail = ""
            logger.warning(
                "Upstream request failed on attempt %s/%s for %s: %s",
                attempt,
                REQUEST_RETRY_ATTEMPTS,
                url,
                exc,
            )

        if attempt < REQUEST_RETRY_ATTEMPTS:
            await asyncio.sleep(REQUEST_RETRY_BASE_DELAY_SECONDS * attempt)

    if isinstance(last_error, ValueError):
        raise HTTPException(status_code=502, detail="模型返回的不是合法 JSON") from last_error

    detail = f"模型请求失败: {last_error}"
    if last_error_detail:
        detail = f"{detail} | upstream={last_error_detail}"
    raise HTTPException(status_code=502, detail=detail) from last_error


async def fetch_available_models(
    *,
    base_url: str,
    api_key: str,
    request_timeout: int,
) -> list[str]:
    url = build_api_url(base_url, "models")
    if not url:
        raise HTTPException(status_code=400, detail="请先填写聊天模型的 API URL。")

    try:
        async with httpx.AsyncClient(timeout=float(request_timeout)) as client:
            response = await client.get(url, headers=build_headers(api_key))
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text.strip() if exc.response is not None else ""
        detail = response_text[:500] if response_text else str(exc)
        raise HTTPException(status_code=502, detail=f"拉取模型列表失败：{detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"拉取模型列表失败：{exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="模型列表接口返回的不是合法 JSON。") from exc

    rows = data.get("data", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="模型列表接口返回格式不正确。")

    models: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if model_id and model_id not in models:
            models.append(model_id)

    return models


async def request_minimal_model_reply() -> dict[str, Any]:
    llm_config = get_runtime_chat_config()
    url = build_api_url(llm_config["base_url"], "chat/completions")
    payload = {
        "model": llm_config["model"],
        "messages": [
            {
                "role": "user",
                "content": "Please reply with one short sentence: connection test successful.",
            }
        ],
    }
    data = await request_json(
        url=url,
        api_key=llm_config["api_key"],
        payload=payload,
        request_timeout=int(llm_config["request_timeout"]),
    )

    try:
        raw_reply = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="模型返回格式不正确") from exc

    sprite_tag, cleaned_reply = extract_sprite_tag(raw_reply)
    return {
        "reply": cleaned_reply or raw_reply,
        "sprite_tag": sprite_tag,
        "worldbook_enforced": False,
    }


async def fetch_embeddings(texts: list[str], runtime_overrides: dict[str, Any] | None = None) -> list[list[float]]:
    embedding = get_runtime_embedding_config(runtime_overrides)
    if not (embedding["base_url"] and embedding["model"]):
        return []

    url = build_api_url(embedding["base_url"], "embeddings")
    payload = {"model": embedding["model"], "input": texts}
    data = await request_json(
        url=url,
        api_key=embedding["api_key"],
        payload=payload,
        request_timeout=int(embedding["request_timeout"]),
    )

    rows = data.get("data", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="嵌入模型返回格式不正确")

    vectors: list[list[float]] = []
    for row in rows:
        vector = row.get("embedding", []) if isinstance(row, dict) else []
        if not isinstance(vector, list):
            raise HTTPException(status_code=502, detail="嵌入模型返回格式不正确")
        vectors.append([float(value) for value in vector])
    return vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(l * r for l, r in zip(left, right))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


async def rerank_documents(
    query: str,
    documents: list[dict[str, Any]],
    runtime_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rerank = get_runtime_rerank_config(runtime_overrides)
    if not rerank["enabled"] or not documents:
        return documents
    if not (rerank["base_url"] and rerank["model"]):
        return documents

    url = build_api_url(rerank["base_url"], "rerank")
    payload = {
        "model": rerank["model"],
        "query": query,
        "documents": [item["text"] for item in documents],
        "top_n": min(int(rerank["top_n"]), len(documents)),
    }
    data = await request_json(
        url=url,
        api_key=rerank["api_key"],
        payload=payload,
        request_timeout=int(rerank["request_timeout"]),
    )

    results = data.get("results") or data.get("data") or []
    if not isinstance(results, list):
        logger.warning("重排序模型返回了非列表结果，回退原始召回结果。")
        return documents

    reranked: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if not isinstance(index, int) or not (0 <= index < len(documents)):
            continue
        updated = documents[index].copy()
        updated["score"] = round(float(item.get("relevance_score", item.get("score", 0.0))), 4)
        reranked.append(updated)

    return reranked or documents


def _deprecated_match_worldbook_entries(query: str) -> list[dict[str, str]]:
    text = str(query or "").strip()
    if not text:
        return []

    normalized_query = normalize_match_text(text)
    hits: list[dict[str, str]] = []
    for trigger, content in get_worldbook().items():
        aliases = [part.strip() for part in re.split(r"[|,，、\n]+", trigger) if part.strip()]
        matched_aliases = [alias for alias in aliases if normalize_match_text(alias) in normalized_query]
        if matched_aliases:
            hits.append(
                {
                    "trigger": trigger,
                    "content": content,
                    "matched": " / ".join(matched_aliases),
                }
            )
    return hits


def split_trigger_aliases(trigger: Any) -> list[str]:
    text = unicodedata.normalize("NFKC", str(trigger or ""))
    aliases = [part.strip() for part in re.split(r"[|,，、/\n]+", text) if part.strip()]
    return aliases or ([text.strip()] if text.strip() else [])


def keyword_matches_query(query_text: str, keyword: str, *, case_sensitive: bool, whole_word: bool) -> bool:
    query = unicodedata.normalize("NFKC", str(query_text or ""))
    target = unicodedata.normalize("NFKC", str(keyword or "")).strip()
    if not query or not target:
        return False

    if not case_sensitive:
        query = query.lower()
        target = target.lower()

    if not whole_word:
        return target in query

    if re.search(r"[\u4e00-\u9fff]", target):
        return target in query

    return bool(re.search(rf"(?<![0-9A-Za-z_]){re.escape(target)}(?![0-9A-Za-z_])", query))


def match_worldbook_entries(query: str) -> list[dict[str, Any]]:
    text = str(query or "").strip()
    if not text:
        return []

    settings = get_worldbook_settings()
    if not settings.get("enabled", True):
        return []

    hits: list[dict[str, Any]] = []
    for item in get_worldbook_entries():
        if not item.get("enabled", True):
            continue

        primary_aliases = split_trigger_aliases(item.get("trigger", ""))
        if not primary_aliases:
            continue

        case_sensitive = bool(item.get("case_sensitive", settings["default_case_sensitive"]))
        whole_word = bool(item.get("whole_word", settings["default_whole_word"]))
        primary_matches = [
            alias for alias in primary_aliases if keyword_matches_query(text, alias, case_sensitive=case_sensitive, whole_word=whole_word)
        ]

        primary_mode = str(item.get("match_mode", settings["default_match_mode"])).strip().lower()
        primary_ok = bool(primary_matches) if primary_mode != "all" else len(primary_matches) == len(primary_aliases)
        if not primary_ok:
            continue

        secondary_aliases = split_trigger_aliases(item.get("secondary_trigger", ""))
        secondary_matches: list[str] = []
        if secondary_aliases:
            secondary_matches = [
                alias for alias in secondary_aliases if keyword_matches_query(text, alias, case_sensitive=case_sensitive, whole_word=whole_word)
            ]
            secondary_mode = str(item.get("secondary_mode", settings["default_secondary_mode"])).strip().lower()
            secondary_ok = bool(secondary_matches) if secondary_mode != "all" else len(secondary_matches) == len(secondary_aliases)
            if not secondary_ok:
                continue

        hits.append(
            {
                "id": str(item.get("id", "")).strip(),
                "title": str(item.get("title", "")).strip(),
                "trigger": str(item.get("trigger", "")).strip(),
                "secondary_trigger": str(item.get("secondary_trigger", "")).strip(),
                "content": str(item.get("content", "")).strip(),
                "matched": " / ".join(primary_matches + secondary_matches),
                "comment": str(item.get("comment", "")).strip(),
                "priority": int(item.get("priority", 100) or 100),
            }
        )

    hits.sort(key=lambda item: (-int(item.get("priority", 100) or 100), item.get("title", "")))
    max_hits = max(1, int(settings.get("max_hits", DEFAULT_WORLDBOOK_SETTINGS["max_hits"])))
    hits = hits[:max_hits]

    if hits:
        logger.info("世界书命中：%s", ", ".join(item["matched"] for item in hits))
    return hits


def build_worldbook_prompt(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return ""

    blocks = [
        "以下是本轮消息命中的世界书设定补丁。",
        "这些内容属于当前对话的高优先级事实背景。",
        "如果用户正在询问这些词条本身，你必须优先直接依据这些设定回答，不要回避，不要装作不知道，也不要被其他闲聊语气盖过去。",
        "回答时不要提及你看到了世界书或设定补丁，只需要自然地把事实说出来。",
    ]
    for index, item in enumerate(matches, start=1):
        matched = item.get("matched", "")
        title = str(item.get("title", "")).strip()
        lines = [f"{index}. 词条：{title or item['trigger']}"]
        lines.append(f"触发词：{item['trigger']}")
        if matched:
            lines.append(f"本轮命中：{matched}")
        if item.get("secondary_trigger"):
            lines.append(f"辅助触发：{item['secondary_trigger']}")
        lines.append(f"设定：{item['content']}")
        if item.get("comment"):
            lines.append(f"备注：{item['comment']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_worldbook_answer_guard(user_message: str, matches: list[dict[str, str]]) -> str:
    if not matches:
        return ""

    text = str(user_message or "").strip()
    if not text:
        return ""

    direct_question_markers = ("是", "什么", "谁", "叫做", "介绍", "解释", "？", "?")
    if not any(marker in text for marker in direct_question_markers):
        return ""

    primary_match = matches[0]
    subject = primary_match.get("matched") or primary_match.get("trigger") or "该词条"
    fact = primary_match.get("content", "").strip()
    if not fact:
        return ""

    return (
        f"本轮用户正在直接询问“{subject}”的含义或身份。"
        f"你的回答第一句必须先直接说出核心事实，例如：{fact}。"
        "先直答，再继续保持角色语气补充，不要先吃醋、回避或装作不知道。"
    )


def enforce_worldbook_fact_in_reply(
    user_message: str,
    reply_text: str,
    matches: list[dict[str, str]],
) -> str:
    if not matches:
        return reply_text

    text = str(reply_text or "").strip()
    if not text:
        return text

    direct_question_markers = ("是", "什么", "谁", "叫做", "介绍", "解释", "？", "?")
    if not any(marker in str(user_message or "") for marker in direct_question_markers):
        return text

    primary_match = matches[0]
    subject = str(primary_match.get("matched") or primary_match.get("trigger") or "").strip()
    fact = str(primary_match.get("content") or "").strip()
    if not subject or not fact:
        return text

    normalized_reply = normalize_match_text(text)
    normalized_subject = normalize_match_text(subject)
    normalized_fact = normalize_match_text(fact[:48])
    if (normalized_subject and normalized_subject in normalized_reply) or (
        normalized_fact and normalized_fact in normalized_reply
    ):
        return text

    logger.info("世界书兜底生效：已在回复前补充事实。")
    return f"{fact}\n\n{text}"


def build_sprite_prompt(llm_config: dict[str, Any]) -> str:
    if not llm_config.get("sprite_enabled", True):
        return ""

    return (
        "你每次回复的第一段都必须以 [表情:标签] 开头。"
        "不允许省略，不允许放到中间。"
        "标签请尽量简短，例如 害羞、生气、平静、委屈、开心、惊讶。"
        "标签后再开始正文，不要解释这条规则。"
    )


def normalize_sprite_tag(tag: str) -> str:
    text = str(tag or "").strip()
    if not text:
        return ""

    replacements = {
        "骞抽潤": "平静",
        "賽抽潤": "平静",
        "賽抽润": "平静",
        "赛抽润": "平静",
    }
    return replacements.get(text, text)


def extract_sprite_tag(reply_text: str) -> tuple[str, str]:
    text = str(reply_text or "").strip()
    if not text:
        return "", ""

    match = re.match(r"^\s*\[(?:表情|emotion)\s*:\s*([^\]\n]{1,32})\]\s*", text, flags=re.IGNORECASE)
    if not match:
        return "", text

    tag = normalize_sprite_tag(match.group(1).strip())
    cleaned = text[match.end() :].lstrip()
    return tag, cleaned


def extract_reply_parts(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "")
    if not text:
        return {"sprite_tag": "", "visible": "", "think": "", "thinking": False}

    stripped = text.lstrip()
    if stripped.startswith("[") and "]" not in stripped[:48]:
        return {"sprite_tag": "", "visible": "", "think": "", "thinking": False}

    sprite_tag, cleaned = extract_sprite_tag(text)
    source = cleaned or text

    think_parts: list[str] = []
    visible_parts: list[str] = []
    cursor = 0
    thinking = False
    open_tag_pattern = re.compile(r"<think\b[^>]*>", flags=re.IGNORECASE)

    while True:
        match = open_tag_pattern.search(source, cursor)
        if not match:
            if cursor < len(source):
                visible_parts.append(source[cursor:])
            break

        start = match.start()
        open_end = match.end()
        if start > cursor:
            visible_parts.append(source[cursor:start])

        close_match = re.search(r"</think>", source[open_end:], flags=re.IGNORECASE)
        if not close_match:
            trailing = source[open_end:].strip()
            if trailing:
                think_parts.append(trailing)
            thinking = True
            cursor = len(source)
            break

        close_index = open_end + close_match.start()
        inner = source[open_end:close_index].strip()
        if inner:
            think_parts.append(inner)
        cursor = close_index + len(close_match.group(0))

    visible = "".join(visible_parts)
    visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
    think = "\n\n".join(part for part in think_parts if part).strip()
    return {
        "sprite_tag": sprite_tag,
        "visible": visible,
        "think": think,
        "thinking": thinking,
    }


def compose_full_reply(think_text: str, visible_text: str) -> str:
    think = str(think_text or "").strip()
    visible = str(visible_text or "").strip()
    if think and visible:
        return f"<think>\n{think}\n</think>\n\n{visible}"
    if think:
        return f"<think>\n{think}\n</think>"
    return visible


def extract_stream_visible_reply(raw_text: str) -> tuple[str, str]:
    reply_parts = extract_reply_parts(raw_text)
    return str(reply_parts["sprite_tag"]), str(reply_parts["visible"])


async def retrieve_memories(query: str, runtime_overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    embedding = get_runtime_embedding_config(runtime_overrides)
    memories = get_memories()
    if not memories:
        return []
    if not (embedding["base_url"] and embedding["model"]):
        return []

    documents: list[dict[str, Any]] = []
    for item in memories:
        text = build_memory_text(item, list(embedding["fields"]))
        if text:
            documents.append({**item, "text": text})

    if not documents:
        return []

    vectors = await fetch_embeddings([query] + [item["text"] for item in documents], runtime_overrides)
    expected_count = len(documents) + 1
    if len(vectors) != expected_count:
        logger.warning(
            "嵌入模型返回数量异常，预期 %s，实际 %s，本轮跳过记忆召回。",
            expected_count,
            len(vectors),
        )
        return []

    query_vector = vectors[0]
    scored: list[dict[str, Any]] = []
    for doc, doc_vector in zip(documents, vectors[1:]):
        scored.append({**doc, "score": round(cosine_similarity(query_vector, doc_vector), 4)})

    scored.sort(key=lambda item: item["score"], reverse=True)
    top_k = min(int(embedding["top_k"]), len(scored))
    selected = scored[:top_k]
    reranked = await rerank_documents(query, selected, runtime_overrides)

    return [
        {
            "id": item["id"],
            "title": item["title"],
            "content": item["content"],
            "tags": item["tags"],
            "notes": item["notes"],
            "text": item["text"],
            "score": item["score"],
        }
        for item in reranked
    ]


def build_retrieval_prompt(retrieved_items: list[dict[str, Any]]) -> str:
    if not retrieved_items:
        return ""

    blocks = [
        "以下是与当前消息最相关的长期记忆或资料片段。",
        "你可以自然参考它们，但不要机械复述，也不要编造没有出现在片段里的细节。",
    ]
    for index, item in enumerate(retrieved_items, start=1):
        title = item.get("title") or f"记忆片段 {index}"
        blocks.append(f"{index}. {title}\n{item.get('text', '')}")
    return "\n\n".join(blocks)


def build_memory_recap_prompt(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""

    blocks = [
        "以下是必须长期记住的前情提要与固定记忆。",
        "回答时请始终把它们当作持续有效的背景信息，除非用户明确要求推翻或修改其中内容。",
    ]
    for index, item in enumerate(memories, start=1):
        title = str(item.get("title", "")).strip() or f"记忆 {index}"
        content = str(item.get("content", "")).strip()
        tags = ", ".join(sanitize_tags(item.get("tags", [])))
        notes = str(item.get("notes", "")).strip()
        lines = [f"{index}. {title}"]
        if content:
            lines.append(f"正文：{content}")
        if tags:
            lines.append(f"标签：{tags}")
        if notes:
            lines.append(f"备注：{notes}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_messages(
    user_message: str,
    retrieved_items: list[dict[str, Any]] | None = None,
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    persona = get_persona()
    history = get_conversation()
    memories = get_memories()
    llm_config = get_runtime_chat_config(runtime_overrides)
    messages: list[dict[str, str]] = []
    system_sections: list[str] = []

    system_prompt = persona.get("system_prompt", "").strip()
    if system_prompt:
        system_sections.append(system_prompt)

    memory_recap_prompt = build_memory_recap_prompt(memories)
    if memory_recap_prompt:
        system_sections.append(memory_recap_prompt)

    worldbook_prompt = build_worldbook_prompt(worldbook_matches or [])
    if worldbook_prompt:
        system_sections.append(worldbook_prompt)
    worldbook_answer_guard = build_worldbook_answer_guard(user_message, worldbook_matches or [])
    if worldbook_answer_guard:
        system_sections.append(worldbook_answer_guard)

    retrieval_prompt = build_retrieval_prompt(retrieved_items or [])
    if retrieval_prompt:
        system_sections.append(retrieval_prompt)

    sprite_prompt = build_sprite_prompt(llm_config)
    if sprite_prompt:
        system_sections.append(sprite_prompt)

    if system_sections:
        messages.append({"role": "system", "content": "\n\n".join(section for section in system_sections if section)})

    history_limit = max(1, int(llm_config["history_limit"]))
    for item in history[-history_limit:]:
        role = item.get("role", "assistant")
        content = str(item.get("content", ""))
        if content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages


async def request_model_reply(
    user_message: str,
    retrieved_items: list[dict[str, Any]],
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    llm_config = get_runtime_chat_config(runtime_overrides)
    url = build_api_url(llm_config["base_url"], "chat/completions")
    payload = {
        "model": llm_config["model"],
        "messages": build_messages(
            user_message,
            retrieved_items,
            runtime_overrides=runtime_overrides,
            worldbook_matches=worldbook_matches,
        ),
        "temperature": llm_config["temperature"],
    }
    data = await request_json(
        url=url,
        api_key=llm_config["api_key"],
        payload=payload,
        request_timeout=int(llm_config["request_timeout"]),
    )

    try:
        raw_reply = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="模型返回格式不正确") from exc

    reply_parts = extract_reply_parts(raw_reply)
    sprite_tag = str(reply_parts["sprite_tag"])
    reply_source = str(reply_parts["visible"] or raw_reply)
    final_reply = enforce_worldbook_fact_in_reply(
        user_message,
        reply_source,
        worldbook_matches or [],
    )
    worldbook_enforced = final_reply != reply_source
    if not sprite_tag and llm_config.get("sprite_enabled", True):
        sprite_tag = "平静"
    return {
        "reply": final_reply,
        "full_reply": compose_full_reply(str(reply_parts["think"]), final_reply),
        "think": str(reply_parts["think"]),
        "sprite_tag": sprite_tag,
        "worldbook_enforced": worldbook_enforced,
    }


def build_worldbook_debug_payload(
    user_message: str,
    worldbook_matches: list[dict[str, str]],
    *,
    reply_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "hit_count": len(worldbook_matches),
        "prompt": build_worldbook_prompt(worldbook_matches),
        "guard": build_worldbook_answer_guard(user_message, worldbook_matches),
        "enforced": bool((reply_result or {}).get("worldbook_enforced")),
        "matched": worldbook_matches,
    }


async def stream_model_reply(
    user_message: str,
    retrieved_items: list[dict[str, Any]],
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, str]] | None = None,
):
    llm_config = get_runtime_chat_config(runtime_overrides)
    url = build_api_url(llm_config["base_url"], "chat/completions")
    payload = {
        "model": llm_config["model"],
        "messages": build_messages(
            user_message,
            retrieved_items,
            runtime_overrides=runtime_overrides,
            worldbook_matches=worldbook_matches,
        ),
        "temperature": llm_config["temperature"],
        "stream": True,
    }

    accumulated_raw = ""
    accumulated_visible = ""
    accumulated_think = ""
    sprite_tag = ""
    was_thinking = False
    stream_started = False
    last_error: Exception | None = None
    last_error_detail = ""

    for attempt in range(1, REQUEST_RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=float(llm_config["request_timeout"])) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=build_headers(llm_config["api_key"]),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_line = line[5:].strip()
                        if not data_line or data_line == "[DONE]":
                            break
                        try:
                            data = json.loads(data_line)
                        except ValueError:
                            continue

                        choices = data.get("choices") or []
                        if not isinstance(choices, list) or not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        chunk = delta.get("content")
                        if not isinstance(chunk, str) or not chunk:
                            continue

                        stream_started = True
                        accumulated_raw += chunk
                        reply_parts = extract_reply_parts(accumulated_raw)
                        parsed_tag = str(reply_parts["sprite_tag"])
                        visible_text = str(reply_parts["visible"])
                        think_text = str(reply_parts["think"])
                        is_thinking = bool(reply_parts["thinking"])
                        if parsed_tag and not sprite_tag:
                            sprite_tag = parsed_tag
                        if is_thinking and not was_thinking:
                            yield {"type": "think_start"}
                        if len(think_text) > len(accumulated_think):
                            think_delta = think_text[len(accumulated_think) :]
                            accumulated_think = think_text
                            if think_delta:
                                yield {"type": "think_chunk", "delta": think_delta}
                        if was_thinking and not is_thinking:
                            yield {"type": "think_end"}
                        was_thinking = is_thinking
                        if len(visible_text) > len(accumulated_visible):
                            delta_text = visible_text[len(accumulated_visible) :]
                            accumulated_visible = visible_text
                            if delta_text:
                                yield {"type": "chunk", "delta": delta_text}
            break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            response_text = exc.response.text.strip() if exc.response is not None else ""
            last_error_detail = response_text[:500]
            status_code = exc.response.status_code if exc.response is not None else 0
            logger.warning(
                "Upstream stream request failed on attempt %s/%s for %s: %s | body=%s",
                attempt,
                REQUEST_RETRY_ATTEMPTS,
                url,
                exc,
                last_error_detail or "<empty>",
            )
            if stream_started or (400 <= status_code < 500 and not should_retry_status_code(status_code)):
                break
        except httpx.HTTPError as exc:
            last_error = exc
            last_error_detail = ""
            logger.warning(
                "Upstream stream request failed on attempt %s/%s for %s: %s",
                attempt,
                REQUEST_RETRY_ATTEMPTS,
                url,
                exc,
            )
            if stream_started:
                break

        if attempt < REQUEST_RETRY_ATTEMPTS and not stream_started:
            await asyncio.sleep(REQUEST_RETRY_BASE_DELAY_SECONDS * attempt)

    if last_error and not accumulated_raw and not accumulated_visible and not accumulated_think:
        detail = f"模型流式请求失败: {last_error}"
        if last_error_detail:
            detail = f"{detail} | upstream={last_error_detail}"
        raise HTTPException(status_code=502, detail=detail) from last_error

    reply_result: dict[str, Any] = {
        "reply": enforce_worldbook_fact_in_reply(
            user_message,
            accumulated_visible or accumulated_raw,
            worldbook_matches or [],
        ),
        "sprite_tag": sprite_tag or ("平静" if llm_config.get("sprite_enabled", True) else ""),
    }
    reply_result["full_reply"] = compose_full_reply(accumulated_think, str(reply_result["reply"]))
    reply_result["think"] = accumulated_think
    reply_result["worldbook_enforced"] = reply_result["reply"] != (accumulated_visible or accumulated_raw)
    yield {"type": "done", **reply_result}


async def generate_reply(
    user_message: str,
    runtime_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    llm_config = get_runtime_chat_config(runtime_overrides)
    retrieved = await retrieve_memories(user_message, runtime_overrides)
    worldbook_matches = match_worldbook_entries(user_message)

    if not (llm_config["base_url"] and llm_config["model"]):
        if not llm_config["demo_mode"]:
            raise HTTPException(
                status_code=400,
                detail="Please configure the chat model API URL and model name first, or enable demo mode.",
            )
        return {"reply": "", "sprite_tag": ""}, retrieved, worldbook_matches

    reply = await request_model_reply(
        user_message,
        retrieved,
        runtime_overrides=runtime_overrides,
        worldbook_matches=worldbook_matches,
    )
    return reply, retrieved, worldbook_matches


def build_conversation_transcript(history: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in history:
        role = item.get("role", "")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        speaker = "User" if role == "user" else "AI"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def fallback_memory_from_conversation(history: list[dict[str, Any]]) -> dict[str, Any]:
    transcript = build_conversation_transcript(history)
    last_user = next(
        (str(item.get("content", "")).strip() for item in reversed(history) if item.get("role") == "user"),
        "",
    )
    title_source = last_user or transcript or "Conversation Memory"
    title = title_source[:18] + ("..." if len(title_source) > 18 else "")
    compact = transcript[:120] + ("..." if len(transcript) > 120 else "")
    return {
        "title": title or "Conversation Memory",
        "content": compact or "A short long-term memory summary was created for this conversation.",
        "tags": ["auto-memory", "summary"],
        "notes": "",
    }


async def request_conversation_summary_with_model(history: list[dict[str, Any]]) -> dict[str, Any]:
    llm_config = get_runtime_chat_config()
    if not (llm_config["base_url"] and llm_config["model"]):
        raise ValueError("chat model is not configured")

    url = build_api_url(llm_config["base_url"], "chat/completions")
    transcript = build_conversation_transcript(history)
    schema_hint = (
        '{\n'
        '  "title": "不超过20字的短标题",\n'
        '  "content": "一条精炼完整的长期记忆短句",\n'
        '  "tags": ["tag1", "tag2"],\n'
        '  "notes": "可为空字符串"\n'
        '}'
    )
    payload = {
        "model": llm_config["model"],
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a dialogue memory formatter. "
                    "Return one strict JSON object only. "
                    "Do not output markdown fences, explanation, roleplay, XML, or any extra text. "
                    "The JSON object must contain exactly these keys: title, content, tags, notes. "
                    "title must be a short title within 20 Chinese characters or 40 ASCII chars. "
                    "content must be one polished complete sentence for long-term memory. "
                    "tags must be an array of short strings. "
                    "notes may be an empty string. "
                    "Output must start with { and end with }."
                ),
            },
            {
                "role": "user",
                "content": (
                    "请把这段完整对话整理成长期记忆。\n"
                    "只返回 JSON 对象，不要返回任何解释。\n"
                    f"格式示例：\n{schema_hint}\n\n"
                    f"对话内容：\n{transcript}"
                ),
            },
        ],
    }
    data = await request_json(
        url=url,
        api_key=llm_config["api_key"],
        payload=payload,
        request_timeout=int(llm_config["request_timeout"]),
    )

    try:
        text = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("invalid summary payload") from exc

    def parse_summary_json(candidate: str) -> dict[str, Any]:
        cleaned = str(candidate or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
        except ValueError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("summary is not json") from None
            parsed = json.loads(cleaned[start : end + 1])

        if not isinstance(parsed, dict):
            raise ValueError("summary json must be an object")

        required_keys = {"title", "content", "tags", "notes"}
        if not required_keys.issubset(parsed.keys()):
            raise ValueError("summary json missing required keys")
        return parsed

    try:
        summary = parse_summary_json(text)
        logger.info("Automatic memory summary parsed as strict JSON on first pass.")
        return summary
    except ValueError:
        logger.warning("Automatic memory summary was not strict JSON, trying one repair pass.")
        repair_payload = {
            "model": llm_config["model"],
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Convert the provided text into one strict JSON object only. "
                        "Do not output markdown, explanation, or extra text. "
                        "The object must contain exactly these keys: title, content, tags, notes."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "把下面这段内容修正成严格 JSON。\n"
                        f"格式示例：\n{schema_hint}\n\n"
                        f"原始内容：\n{text}"
                    ),
                },
            ],
        }
        repair_data = await request_json(
            url=url,
            api_key=llm_config["api_key"],
            payload=repair_payload,
            request_timeout=int(llm_config["request_timeout"]),
        )
        try:
            repaired_text = str(repair_data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("invalid summary repair payload") from exc
        summary = parse_summary_json(repaired_text)
        logger.info("Automatic memory summary repaired into strict JSON successfully.")
        return summary


def sanitize_memory_summary(payload: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip() or fallback["title"]
    content = str(payload.get("content", "")).strip() or fallback["content"]
    tags = sanitize_tags(payload.get("tags", fallback["tags"])) or ["auto-memory", "summary"]
    notes = str(payload.get("notes", "")).strip()

    return {
        "id": f"memory-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "title": title[:40],
        "content": content[:180],
        "tags": tags[:8],
        "notes": notes[:240],
    }


async def summarize_conversation_to_memory(history: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = fallback_memory_from_conversation(history)
    try:
        summary_payload = await request_conversation_summary_with_model(history)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Automatic memory summary failed, falling back to local summary: %s", exc)
        summary_payload = fallback

    return sanitize_memory_summary(summary_payload, fallback=fallback)


async def archive_current_conversation() -> dict[str, Any]:
    history = [item for item in get_conversation() if item.get("role") in {"user", "assistant"}]
    if not history:
        raise HTTPException(status_code=400, detail="当前没有可结束的对话。")

    memory = await summarize_conversation_to_memory(history)
    memories = get_memories()
    if memories:
        last = memories[-1]
        if last.get("title") == memory["title"] and last.get("content") == memory["content"]:
            persist_json(
                conversation_path(),
                [],
                detail="结束对话失败：无法清空当前聊天记录。",
            )
            return last

    memories.append(memory)
    save_memories(memories)
    persist_json(
        conversation_path(),
        [],
        detail="结束对话失败：无法清空当前聊天记录。",
    )
    return memory

load_env_file()
ensure_data_files()

bootstrap_runtime_layout()

app = FastAPI(title="Xuqi LLM Chat")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ChatRequest(BaseModel):
    message: str
    runtime_config: dict[str, Any] | None = None


class PersonaPayload(BaseModel):
    name: str
    system_prompt: str
    greeting: str


class SettingsPayload(BaseModel):
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    theme: str = "light"
    temperature: float = 0.85
    history_limit: int = 20
    request_timeout: int = 120
    demo_mode: bool = False
    ui_opacity: float = 0.84
    background_image_url: str = ""
    background_overlay: float = 0.42
    sprite_enabled: bool = True
    sprite_base_path: str = DEFAULT_SPRITE_BASE_PATH
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_fields: list[str] = Field(default_factory=lambda: list(DEFAULT_SETTINGS["embedding_fields"]))
    retrieval_top_k: int = 4
    rerank_enabled: bool = False
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""
    rerank_top_n: int = 3


class MemoryItemPayload(BaseModel):
    id: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class MemoryListPayload(BaseModel):
    items: list[MemoryItemPayload] = Field(default_factory=list)


class WorldbookEntryPayload(BaseModel):
    id: str = ""
    title: str = ""
    trigger: str = ""
    secondary_trigger: str = ""
    content: str = ""
    enabled: bool = True
    priority: int = 100
    case_sensitive: bool = False
    whole_word: bool = False
    match_mode: str = "any"
    secondary_mode: str = "all"
    comment: str = ""


class WorldbookSettingsPayload(BaseModel):
    enabled: bool = True
    max_hits: int = 3
    default_case_sensitive: bool = False
    default_whole_word: bool = False
    default_match_mode: str = "any"
    default_secondary_mode: str = "all"


class WorldbookPayload(BaseModel):
    items: list[WorldbookEntryPayload] = Field(default_factory=list)
    settings: WorldbookSettingsPayload | None = None


class SaveSlotSelectPayload(BaseModel):
    slot_id: str


class SaveSlotRenamePayload(BaseModel):
    slot_id: str
    name: str = ""


class SaveSlotResetPayload(BaseModel):
    slot_id: str


class SpriteDeletePayload(BaseModel):
    filename: str


class RoleCardPayload(BaseModel):
    raw_json: str
    filename: str = ""
    apply_now: bool = True


class RoleCardLoadPayload(BaseModel):
    filename: str


def build_chat_template_context() -> dict[str, Any]:
    active_slot = get_active_slot_id()
    return {
        "persona": get_persona(active_slot),
        "history": get_conversation(active_slot),
        "settings": get_settings(active_slot),
        "active_slot": active_slot,
        "slot_registry": get_slot_registry(),
    }


@app.get("/", response_class=HTMLResponse)
async def welcome_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    return templates.TemplateResponse(
        request,
        "welcome.html",
        {
            "settings": get_settings(active_slot),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/chat", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        build_chat_template_context(),
    )


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "settings": get_settings(active_slot),
            "memory_count": len(get_memories(active_slot)),
            "current_card": get_current_card(active_slot),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/config/card", response_class=HTMLResponse)
async def card_config_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    current_card = get_current_card(active_slot)
    return templates.TemplateResponse(
        request,
        "card_config.html",
        {
            "settings": get_settings(active_slot),
            "cards": list_role_card_files(),
            "current_card": current_card,
            "card_template": normalize_role_card(current_card.get("raw", {})),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/config/memory", response_class=HTMLResponse)
async def memory_config_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    return templates.TemplateResponse(
        request,
        "memory_config.html",
        {
            "settings": get_settings(active_slot),
            "memories": get_memories(active_slot),
            "memory_count": len(get_memories(active_slot)),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/config/worldbook", response_class=HTMLResponse)
async def worldbook_config_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    return templates.TemplateResponse(
        request,
        "worldbook_config.html",
        {
            "settings": get_settings(active_slot),
            "worldbook_settings": get_worldbook_settings(active_slot),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/config/worldbook/entries", response_class=HTMLResponse)
async def worldbook_manager_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    return templates.TemplateResponse(
        request,
        "worldbook_manager.html",
        {
            "settings": get_settings(active_slot),
            "worldbook_settings": get_worldbook_settings(active_slot),
            "worldbook_entries": get_worldbook_entries(active_slot),
            "worldbook_count": len(get_worldbook_entries(active_slot)),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/config/sprite", response_class=HTMLResponse)
async def sprite_config_page(request: Request) -> HTMLResponse:
    active_slot = get_active_slot_id()
    return templates.TemplateResponse(
        request,
        "sprite_config.html",
        {
            "settings": get_settings(active_slot),
            "sprites": list_sprite_assets(active_slot),
            "sprite_count": len(list_sprite_assets(active_slot)),
            "sprite_base_path": default_sprite_base_path_for_slot(active_slot),
            "active_slot": active_slot,
            "slot_registry": get_slot_registry(),
        },
    )


@app.get("/api/persona")
async def api_get_persona() -> dict[str, Any]:
    return get_persona()


@app.post("/api/persona")
async def api_save_persona(payload: PersonaPayload) -> dict[str, Any]:
    persist_json(
        persona_path(),
        {
            "name": payload.name.strip(),
            "system_prompt": payload.system_prompt.strip(),
            "greeting": payload.greeting.strip(),
        },
        detail="角色设置保存失败，请检查磁盘空间或文件权限。",
    )
    return {"ok": True}


@app.get("/api/settings")
async def api_get_settings() -> dict[str, Any]:
    active_slot = get_active_slot_id()
    return {
        "active_slot": active_slot,
        "slot_name": get_slot_name(active_slot),
        "settings": get_settings(active_slot),
    }


@app.post("/api/settings")
async def api_save_settings(payload: SettingsPayload) -> dict[str, Any]:
    active_slot = get_active_slot_id()
    settings = sanitize_settings(payload.model_dump(), strict=True, slot_id=active_slot)
    persist_json(
        settings_path(),
        settings,
        detail="设置保存失败，请检查磁盘空间或文件权限。",
    )
    return {"ok": True, "settings": settings, "active_slot": active_slot}


@app.get("/api/slots")
async def api_get_slots() -> dict[str, Any]:
    registry = get_slot_registry()
    active_slot = registry["active_slot"]
    slots = [slot_summary(item["id"]) for item in registry["slots"]]
    return {"active_slot": active_slot, "slots": slots}


@app.post("/api/slots/select")
async def api_select_slot(payload: SaveSlotSelectPayload) -> dict[str, Any]:
    target = sanitize_slot_id(payload.slot_id, get_active_slot_id())
    registry = get_slot_registry()
    registry["active_slot"] = target
    save_slot_registry(registry)
    return {"ok": True, "active_slot": target, "slot": slot_summary(target)}


@app.post("/api/slots/rename")
async def api_rename_slot(payload: SaveSlotRenamePayload) -> dict[str, Any]:
    target = sanitize_slot_id(payload.slot_id, get_active_slot_id())
    registry = get_slot_registry()
    for index, item in enumerate(registry["slots"], start=1):
        if item["id"] == target:
            item["name"] = str(payload.name or "").strip()[:32] or f"存档 {index}"
            break
    save_slot_registry(registry)
    return {"ok": True, "active_slot": registry["active_slot"], "slots": registry["slots"]}


@app.post("/api/slots/reset")
async def api_reset_slot(payload: SaveSlotResetPayload) -> dict[str, Any]:
    target = sanitize_slot_id(payload.slot_id, get_active_slot_id())
    summary = reset_slot_data(target)
    return {"ok": True, "slot": summary, "active_slot": get_active_slot_id()}


@app.get("/api/memories")
async def api_get_memories() -> list[dict[str, Any]]:
    return get_memories()


@app.get("/api/worldbook")
async def api_get_worldbook() -> dict[str, Any]:
    store = get_worldbook_store()
    return {"items": store["entries"], "settings": store["settings"]}


@app.get("/api/sprites")
async def api_get_sprites() -> dict[str, Any]:
    active_slot = get_active_slot_id()
    return {
        "active_slot": active_slot,
        "base_path": default_sprite_base_path_for_slot(active_slot),
        "items": list_sprite_assets(active_slot),
    }


@app.get("/api/cards")
async def api_get_cards() -> dict[str, Any]:
    return {
        "items": list_role_card_files(),
        "current_card": get_current_card(),
    }


@app.post("/api/cards/import")
async def api_import_card(payload: RoleCardPayload) -> dict[str, Any]:
    card = parse_role_card_json(payload.raw_json)
    filename = Path(payload.filename.strip() or f"{card.get('name', 'role_card')}.json").name
    if not filename.lower().endswith(".json"):
        filename += ".json"

    persist_json(
        CARDS_DIR / filename,
        card,
        detail="角色卡保存失败：无法写入 cards 目录。",
    )

    result: dict[str, Any] = {"ok": True, "filename": filename, "card": card}
    if payload.apply_now:
        result.update(apply_role_card(card, source_name=filename))
    return result


@app.post("/api/cards/load")
async def api_load_card(payload: RoleCardLoadPayload) -> dict[str, Any]:
    filename = Path(payload.filename).name
    target = CARDS_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="未找到对应的角色卡文件。")
    if target.suffix.lower() not in ROLE_CARD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="角色卡文件格式不受支持，请使用 .json 或 .txt。")

    raw_text = read_role_card_text(target)
    card = parse_role_card_json(raw_text)
    result = apply_role_card(card, source_name=filename)
    result.update({"ok": True, "filename": filename, "card": card})
    return result


@app.get("/api/cards/export/current")
async def api_export_current_card() -> FileResponse:
    current_card = get_current_card()
    card = current_card.get("raw", {})
    if not isinstance(card, dict) or not any(
        str(value).strip() for value in card.values() if not isinstance(value, (dict, list))
    ):
        raise HTTPException(status_code=404, detail="当前角色卡不存在或尚未加载。")

    source_name = Path(str(current_card.get("source_name", "")).strip() or "role_card_export.json").name
    if not source_name.lower().endswith(".json"):
        source_name += ".json"
    export_path = EXPORT_DIR / source_name
    persist_json(
        export_path,
        normalize_role_card(card),
        detail="导出当前角色卡失败，请检查文件权限。",
    )
    return FileResponse(
        path=export_path,
        filename=source_name,
        media_type="application/json",
    )

@app.post("/api/memories")
async def api_save_memories(payload: MemoryListPayload) -> dict[str, Any]:
    memories = save_memories([item.model_dump() for item in payload.items])
    return {"ok": True, "items": memories}


@app.post("/api/worldbook")
async def api_save_worldbook(payload: WorldbookPayload) -> dict[str, Any]:
    existing_store = get_worldbook_store()
    existing_entries = existing_store["entries"]
    merged_items: list[dict[str, Any]] = []
    for index, item in enumerate(payload.items, start=1):
        row = item.model_dump()
        trigger = str(row.get("trigger", "")).strip()
        content = str(row.get("content", "")).strip()
        if not trigger or not content:
            continue
        previous = next((entry for entry in existing_entries if str(entry.get("trigger", "")).strip() == trigger), {})
        merged_items.append(
            {
                "id": row.get("id") or previous.get("id", f"worldbook-{index}"),
                "title": row.get("title") or previous.get("title", f"词条 {index}"),
                "trigger": trigger,
                "secondary_trigger": row.get("secondary_trigger") or previous.get("secondary_trigger", ""),
                "content": content,
                "enabled": row.get("enabled", previous.get("enabled", True)),
                "priority": row.get("priority", previous.get("priority", 100)),
                "case_sensitive": row.get("case_sensitive", previous.get("case_sensitive", existing_store["settings"]["default_case_sensitive"])),
                "whole_word": row.get("whole_word", previous.get("whole_word", existing_store["settings"]["default_whole_word"])),
                "match_mode": row.get("match_mode") or previous.get("match_mode", existing_store["settings"]["default_match_mode"]),
                "secondary_mode": row.get("secondary_mode") or previous.get("secondary_mode", existing_store["settings"]["default_secondary_mode"]),
                "comment": row.get("comment") or previous.get("comment", ""),
            }
        )

    store_to_save = {
        "settings": payload.settings.model_dump() if payload.settings is not None else existing_store["settings"],
        "entries": merged_items,
    }
    saved_store = save_worldbook_store(store_to_save)
    return {"ok": True, "items": saved_store["entries"], "settings": saved_store["settings"]}


@app.get("/api/worldbook/settings")
async def api_get_worldbook_settings() -> dict[str, Any]:
    return {"settings": get_worldbook_settings()}


@app.post("/api/worldbook/settings")
async def api_save_worldbook_settings(payload: WorldbookSettingsPayload) -> dict[str, Any]:
    settings = save_worldbook_settings(payload.model_dump())
    return {"ok": True, "settings": settings}


@app.get("/api/worldbook/entries")
async def api_get_worldbook_entries() -> dict[str, Any]:
    return {"items": get_worldbook_entries(), "settings": get_worldbook_settings()}


@app.post("/api/worldbook/entries")
async def api_save_worldbook_entries(payload: WorldbookPayload) -> dict[str, Any]:
    items = save_worldbook_entries([item.model_dump() for item in payload.items])
    return {"ok": True, "items": items, "settings": get_worldbook_settings()}


@app.post("/api/sprites")
async def api_upload_sprite(
    tag: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only png / jpg / jpeg / webp / gif sprites are supported.")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded sprite must be an image file.")

    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded sprite cannot be empty.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Sprite image cannot be larger than 10 MB.")

    active_slot = get_active_slot_id()
    directory = sprite_dir_path(active_slot)
    directory.mkdir(parents=True, exist_ok=True)

    normalized_tag = sanitize_sprite_filename_tag(tag) or sanitize_sprite_filename_tag(Path(file.filename or "").stem)
    if not normalized_tag:
        raise HTTPException(status_code=400, detail="Please provide a valid sprite tag.")

    for existing in directory.glob(f"{normalized_tag}.*"):
        if existing.is_file() and existing.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            existing.unlink(missing_ok=True)

    target = directory / f"{normalized_tag}{suffix}"
    try:
        target.write_bytes(content)
    except OSError as exc:
        logger.exception("Sprite write failed: %s", target)
        raise HTTPException(status_code=500, detail="Sprite save failed. Please check disk space or file permissions.") from exc

    return {
        "ok": True,
        "active_slot": active_slot,
        "base_path": default_sprite_base_path_for_slot(active_slot),
        "uploaded": {
            "filename": target.name,
            "tag": normalized_tag,
            "url": f"{default_sprite_base_path_for_slot(active_slot)}/{target.name}",
        },
        "items": list_sprite_assets(active_slot),
    }


@app.post("/api/sprites/delete")
async def api_delete_sprite(payload: SpriteDeletePayload) -> dict[str, Any]:
    active_slot = get_active_slot_id()
    filename = Path(str(payload.filename or "")).name
    if not filename:
        raise HTTPException(status_code=400, detail="Sprite filename is required.")

    target = sprite_dir_path(active_slot) / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Sprite file not found.")
    if target.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported sprite file type.")

    try:
        target.unlink()
    except OSError as exc:
        logger.exception("Sprite delete failed: %s", target)
        raise HTTPException(status_code=500, detail="Sprite delete failed. Please check file permissions.") from exc

    return {
        "ok": True,
        "active_slot": active_slot,
        "base_path": default_sprite_base_path_for_slot(active_slot),
        "items": list_sprite_assets(active_slot),
    }


@app.post("/api/background")
async def api_upload_background(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="只支持 png / jpg / jpeg / webp / gif 图片。")

    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="上传文件必须是图片。")

    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="背景图不能超过 10 MB。")

    filename = f"bg_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"
    target = UPLOAD_DIR / filename
    try:
        target.write_bytes(content)
    except OSError as exc:
        logger.exception("背景图写入失败: %s", target)
        raise HTTPException(status_code=500, detail="背景图保存失败，请检查磁盘空间或文件权限。") from exc

    return {"ok": True, "url": f"/static/uploads/{filename}"}


@app.post("/api/models")
async def api_get_models() -> dict[str, Any]:
    llm_config = get_runtime_chat_config()
    models = await fetch_available_models(
        base_url=str(llm_config["base_url"] or "").strip(),
        api_key=str(llm_config["api_key"] or "").strip(),
        request_timeout=int(llm_config["request_timeout"]),
    )
    current_model = str(llm_config.get("model", "")).strip()

    preferred = current_model if current_model in models else (models[0] if models else "")
    return {
        "ok": True,
        "items": models,
        "current_model": current_model,
        "preferred_model": preferred,
    }


@app.post("/api/test-connection")
async def api_test_connection() -> dict[str, Any]:
    llm_config = get_runtime_chat_config()
    if not (llm_config["base_url"] and llm_config["model"]):
        raise HTTPException(status_code=400, detail="请先填写聊天模型的 API URL 和模型名。")

    reply = await request_minimal_model_reply()
    return {"ok": True, "reply": reply.get("reply", ""), "sprite_tag": reply.get("sprite_tag", "")}


@app.post("/api/test-embedding")
async def api_test_embedding() -> dict[str, Any]:
    embedding = get_runtime_embedding_config()
    if not (embedding["base_url"] and embedding["model"]):
        raise HTTPException(status_code=400, detail="请先填写嵌入模型的 API URL 和模型名。")

    vectors = await fetch_embeddings(["连接测试", "向量检索"])
    if not vectors:
        raise HTTPException(status_code=502, detail="嵌入模型没有返回向量。")

    return {"ok": True, "dimension": len(vectors[0]), "count": len(vectors)}


@app.get("/api/history")
async def api_get_history() -> list[dict[str, Any]]:
    return get_conversation()


@app.post("/api/chat")
async def api_chat(payload: ChatRequest) -> dict[str, Any]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空。")

    runtime_overrides = payload.runtime_config or {}
    reply_result, retrieved_items, worldbook_matches = await generate_reply(message, runtime_overrides)
    reply = str(reply_result.get("reply", ""))
    entries = [("user", message)]
    if reply.strip():
        entries.append(("assistant", reply))
    append_messages(entries)

    worldbook_debug = build_worldbook_debug_payload(message, worldbook_matches, reply_result=reply_result)

    return {
        "reply": reply,
        "retrieved_items": retrieved_items,
        "worldbook_hits": worldbook_matches,
        "worldbook_debug": worldbook_debug,
        "sprite_tag": reply_result.get("sprite_tag", ""),
        "memory_item": None,
    }


@app.post("/api/chat/stream")
async def api_chat_stream(payload: ChatRequest) -> StreamingResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    runtime_overrides = payload.runtime_config or {}
    llm_config = get_runtime_chat_config(runtime_overrides)
    retrieved_items = await retrieve_memories(message, runtime_overrides)
    worldbook_matches = match_worldbook_entries(message)
    worldbook_debug = build_worldbook_debug_payload(message, worldbook_matches)

    if not (llm_config["base_url"] and llm_config["model"]):
        if not llm_config["demo_mode"]:
            raise HTTPException(
                status_code=400,
                detail="Please configure the chat model API URL and model name first, or enable demo mode.",
            )

        async def demo_event_stream():
            append_messages([("user", message)])
            meta = {
                "type": "meta",
                "retrieved_items": retrieved_items,
                "worldbook_hits": worldbook_matches,
                "worldbook_debug": worldbook_debug,
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            done = {"type": "done", "reply": "", "sprite_tag": "", "worldbook_enforced": False}
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"

        return StreamingResponse(demo_event_stream(), media_type="text/event-stream")

    async def event_stream():
        meta = {
            "type": "meta",
            "retrieved_items": retrieved_items,
            "worldbook_hits": worldbook_matches,
            "worldbook_debug": worldbook_debug,
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

        final_reply_result: dict[str, Any] | None = None
        try:
            async for item in stream_model_reply(
                message,
                retrieved_items,
                runtime_overrides=runtime_overrides,
                worldbook_matches=worldbook_matches,
            ):
                if item.get("type") == "done":
                    final_reply_result = item
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            error_event = {"type": "error", "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return
        except Exception as exc:
            logger.exception("Stream reply failed")
            error_event = {"type": "error", "detail": str(exc)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        reply_text = str((final_reply_result or {}).get("reply", "")).strip()
        stored_reply_text = str((final_reply_result or {}).get("full_reply", "")).strip() or reply_text
        entries = [("user", message)]
        if stored_reply_text:
            entries.append(("assistant", stored_reply_text))
        append_messages(entries)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/conversation/end")
async def api_end_conversation() -> dict[str, Any]:
    memory = await archive_current_conversation()
    return {"ok": True, "memory_item": memory}

@app.post("/api/reset")
async def api_reset() -> dict[str, Any]:
    persist_json(
        conversation_path(),
        [],
        detail="聊天记录清空失败，请检查磁盘空间或文件权限。",
    )
    return {"ok": True}


@app.get("/api/export/history")
async def api_export_history() -> FileResponse:
    slot_id = get_active_slot_id()
    history = get_conversation(slot_id)
    export_path = EXPORT_DIR / f"{slot_id}_chat_history_export.json"
    persist_json(
        export_path,
        history,
        detail="导出聊天记录失败，请检查磁盘空间或文件权限。",
    )
    return FileResponse(
        path=export_path,
        filename=f"{slot_id}_chat_history_export.json",
        media_type="application/json",
    )
