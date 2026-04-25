import asyncio
import json
import logging
import os
import random
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .chat_api_routes import register_chat_api_routes
from .config_api_routes import register_config_api_routes
from .mod_api_routes import register_mod_api_routes
from .mods_runtime import mount_discovered_mods
from .page_routes import register_page_routes
from .preset_rules import (
    PRESET_MODULE_RULES,
    activate_preset_in_store,
    build_preset_prompt_from_preset,
    create_preset_in_store,
    default_preset_store as default_preset_store_data,
    delete_preset_from_store,
    duplicate_preset_in_store,
    get_active_preset_from_store,
    sanitize_preset_store as sanitize_preset_store_data,
)
from .slot_runtime import SlotRuntimeService
from .workshop_logic import (
    build_workshop_trigger_token,
    default_workshop_state,
    get_workshop_stage,
    get_workshop_stage_label,
    get_workshop_trigger_label,
    normalize_workshop_action_type,
    normalize_workshop_stage,
    normalize_workshop_trigger_mode,
    sanitize_creative_workshop,
    sanitize_workshop_state,
    select_workshop_match,
    workshop_effective_fields,
    workshop_rule_matches_trigger,
)
from .worldbook_logic import (
    DEFAULT_WORLDBOOK_SETTINGS,
    default_worldbook_store,
    keyword_matches_query,
    normalize_match_text,
    sanitize_worldbook,
    sanitize_worldbook_entry,
    sanitize_worldbook_settings,
    sanitize_worldbook_store,
    split_trigger_aliases,
)

from .prompt_builder import (
    build_conversation_transcript,
    build_memory_recap_prompt,
    build_messages,
    build_prompt_package,
    build_retrieval_prompt,
    build_sprite_prompt,
    build_user_profile_prompt,
    build_worldbook_answer_guard,
    build_worldbook_prompt,
    configure_prompt_builder,
)


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


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
    return PROJECT_ROOT


def get_resource_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return PROJECT_ROOT


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
MODS_DIR = BASE_DIR / "mods"
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
GLOBAL_PRESET_PATH = DATA_DIR / "preset.json"
GLOBAL_WORKSHOP_STATE_PATH = DATA_DIR / "creative_workshop_state.json"
GLOBAL_USER_PROFILE_PATH = DATA_DIR / "user_profile.json"
GLOBAL_WORLDBOOK_RUNTIME_STATE_PATH = DATA_DIR / "worldbook_runtime_state.json"
SLOT_MIGRATION_MARKER_PATH = DATA_DIR / ".slot_migration_done"
GLOBAL_RUNTIME_MIGRATION_MARKER_PATH = DATA_DIR / ".global_runtime_migration_done"
PRESET_FILENAME = "preset.json"

ALLOWED_EMBEDDING_FIELDS = ("title", "content", "tags", "notes")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".webm"}
ALLOWED_BACKGROUND_SCHEMES = {"http", "https"}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
MAX_BACKGROUND_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024
MAX_WORKSHOP_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024
REQUEST_RETRY_ATTEMPTS = 5
REQUEST_RETRY_BASE_DELAY_SECONDS = 1.0
DEFAULT_SPRITE_BASE_PATH = "/static/sprites"
GLOBAL_RUNTIME_ID = "global_workspace"
GLOBAL_RUNTIME_NAME = "当前记忆"
LEGACY_SLOT_IDS = ("slot_1", "slot_2", "slot_3")
DEFAULT_SLOT_IDS = (GLOBAL_RUNTIME_ID,)
WORKSHOP_STAGE_LIMITS = {"aMax": 2, "bMax": 5}

logger = logging.getLogger("xuqi_llm_chat")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

_LAST_WORLDBOOK_DEBUG_SNAPSHOT: dict[str, Any] = {"query": "", "all_matches": [], "selected_ids": [], "dropped_ids": []}


def _copy_worldbook_debug_snapshot(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else _LAST_WORLDBOOK_DEBUG_SNAPSHOT
    all_matches = source.get("all_matches", [])
    selected_ids = source.get("selected_ids", [])
    dropped_ids = source.get("dropped_ids", [])
    return {
        "query": str(source.get("query", "") or ""),
        "all_matches": [dict(item) for item in all_matches if isinstance(item, dict)],
        "selected_ids": [str(item) for item in selected_ids] if isinstance(selected_ids, list) else [],
        "dropped_ids": [str(item) for item in dropped_ids] if isinstance(dropped_ids, list) else [],
    }


def get_worldbook_debug_snapshot() -> dict[str, Any]:
    return _copy_worldbook_debug_snapshot()


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
    return {
        "active_slot": GLOBAL_RUNTIME_ID,
        "slots": [{"id": GLOBAL_RUNTIME_ID, "name": GLOBAL_RUNTIME_NAME}],
    }


def default_sprite_base_path_for_slot(slot_id: str | None = None) -> str:
    return DEFAULT_SPRITE_BASE_PATH


def sprite_dir_path(slot_id: str | None = None) -> Path:
    return SPRITES_DIR


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
        "creativeWorkshop": {
            "enabled": True,
            "items": [
                {
                    "id": "workshop_stage_a",
                    "name": "A阶段规则",
                    "enabled": True,
                    "triggerMode": "stage",
                    "triggerStage": "A",
                    "triggerTempMin": 0,
                    "triggerTempMax": 0,
                    "actionType": "music",
                    "popupTitle": "",
                    "musicPreset": "off",
                    "musicUrl": "",
                    "autoplay": True,
                    "loop": True,
                    "volume": 0.85,
                    "imageUrl": "",
                    "imageAlt": "",
                    "note": "",
                }
            ],
        },
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



def default_user_profile() -> dict[str, Any]:
    return {
        "display_name": "",
        "nickname": "",
        "profile_text": "",
        "notes": "",
        "avatar_url": "",
    }


def default_creative_workshop() -> dict[str, Any]:
    return json.loads(json.dumps(default_role_card()["creativeWorkshop"], ensure_ascii=False))


def get_workshop_state(slot_id: str | None = None) -> dict[str, Any]:
    return sanitize_workshop_state(read_json(workshop_state_path(slot_id), default_workshop_state()))


def save_workshop_state(payload: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    sanitized = sanitize_workshop_state(payload)
    persist_json(
        workshop_state_path(slot_id),
        sanitized,
        detail="Creative workshop state save failed. Please check disk space or file permissions.",
    )
    return sanitized


def reset_workshop_state(slot_id: str | None = None) -> dict[str, Any]:
    return save_workshop_state(default_workshop_state(), slot_id)


def workshop_signature(slot: dict[str, Any] | None, workshop: dict[str, Any], stage: str) -> str:
    payload = {
        "slot": str((slot or {}).get("source_name", "")),
        "enabled": bool(workshop.get("enabled", False)),
        "stage": stage,
        "items": [
            {
                **workshop_effective_fields(item),
            }
            for item in workshop.get("items", [])
            if isinstance(item, dict)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def resolve_workshop_music_url(item: dict[str, Any]) -> str:
    return str(item.get("musicUrl", "")).strip()


def resolve_workshop_image_url(item: dict[str, Any]) -> str:
    return str(item.get("imageUrl", "")).strip()


def evaluate_creative_workshop(*, slot_id: str | None = None, reason: str = "sync") -> dict[str, Any]:
    target_slot = sanitize_slot_id(slot_id, get_active_slot_id())
    current_card = get_current_card(target_slot)
    workshop = sanitize_creative_workshop(current_card.get("raw", {}).get("creativeWorkshop", {}))
    state = get_workshop_state(target_slot)
    current_temp = int(state.get("temp", 0) or 0)
    stage = get_workshop_stage(current_temp)

    result: dict[str, Any] = {
        "stage": stage,
        "stage_label": get_workshop_stage_label(stage),
        "temp": current_temp,
        "reason": reason,
        "triggered": False,
        "action": None,
        "workshop": workshop,
        "current_card_name": str(current_card.get("source_name", "")).strip(),
    }

    if reason != "chat_round_start":
        return result

    pending_temp = clamp_int(state.get("pending_temp"), -1, 9999, -1)
    if pending_temp != current_temp:
        return result

    match = select_workshop_match(workshop, temp=current_temp, stage=stage)
    signature = build_workshop_trigger_token(match, temp=current_temp, stage=stage) if match else ""
    previous = str(state.get("last_signature", "")).strip()
    state["pending_temp"] = -1
    state["last_signature"] = signature
    save_workshop_state(state, target_slot)

    if not workshop.get("enabled", False) or not match:
        return result

    trigger_history = state.get("trigger_history", []) if isinstance(state.get("trigger_history"), list) else []
    if signature and (signature == previous or signature in trigger_history):
        return result

    if signature:
        updated_state = get_workshop_state(target_slot)
        updated_history = updated_state.get("trigger_history", []) if isinstance(updated_state.get("trigger_history"), list) else []
        updated_history = [token for token in updated_history if token != signature]
        updated_state["trigger_history"] = (updated_history + [signature])[-128:]
        updated_state["last_signature"] = signature
        save_workshop_state(updated_state, target_slot)

    action_type = normalize_workshop_action_type(match.get("actionType"))
    action = {
        "id": match.get("id", ""),
        "name": match.get("name", ""),
        "stage": stage,
        "stage_label": result["stage_label"],
        "trigger_mode": normalize_workshop_trigger_mode(match.get("triggerMode")),
        "trigger_label": get_workshop_trigger_label(match, temp=current_temp, stage=stage),
        "reason": reason,
        "action_type": action_type,
        "note": str(match.get("note", "")).strip(),
    }

    if action_type == "image":
        action.update(
            {
                "popup_title": str(match.get("popupTitle", "")).strip() or str(match.get("name", "")).strip() or "鍒涙剰宸ュ潑寮圭獥",
                "image_url": resolve_workshop_image_url(match),
                "image_alt": str(match.get("imageAlt", "")).strip() or str(match.get("name", "")).strip() or "鍒涙剰宸ュ潑鍥剧墖",
            }
        )
    else:
        action.update(
            {
                "music_preset": str(match.get("musicPreset", "off")).strip() or "off",
                "music_url": resolve_workshop_music_url(match),
                "autoplay": bool(match.get("autoplay", True)),
                "loop": bool(match.get("loop", True)),
                "volume": clamp_float(match.get("volume"), 0.0, 1.0, 0.85),
            }
        )

    if action_type == "image" and not action["image_url"]:
        return result
    if action_type == "music" and not action["music_url"] and action["music_preset"] == "off":
        return result

    result["triggered"] = True
    result["action"] = action
    return result


def default_preset_store() -> dict[str, Any]:
    return default_preset_store_data()


def sanitize_preset_store(raw: Any) -> dict[str, Any]:
    return sanitize_preset_store_data(raw)


def preset_path(slot_id: str | None = None) -> Path:
    return GLOBAL_PRESET_PATH


def get_preset_store(slot_id: str | None = None) -> dict[str, Any]:
    return sanitize_preset_store(read_json(preset_path(slot_id), default_preset_store()))


def save_preset_store(payload: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    sanitized = sanitize_preset_store(payload)
    persist_json(
        preset_path(slot_id),
        sanitized,
        detail="Preset save failed. Please check disk space or file permissions.",
    )
    return sanitized


def get_active_preset(slot_id: str | None = None) -> dict[str, Any]:
    return get_active_preset_from_store(get_preset_store(slot_id))


def build_preset_prompt(slot_id: str | None = None) -> str:
    return build_preset_prompt_from_preset(get_active_preset(slot_id))


def get_active_preset_module_labels(slot_id: str | None = None) -> list[str]:
    preset = get_active_preset(slot_id)
    modules = preset.get("modules", {}) if isinstance(preset, dict) else {}
    labels: list[str] = []
    for key, meta in PRESET_MODULE_RULES.items():
        if modules.get(key):
            labels.append(str(meta.get("label", key)))
    return labels


def build_preset_debug_payload(slot_id: str | None = None) -> dict[str, Any]:
    store = get_preset_store(slot_id)
    preset = get_active_preset_from_store(store)
    prompt = build_preset_prompt_from_preset(preset)
    return {
        "active_preset_id": str(store.get("active_preset_id", "")).strip(),
        "active_preset_name": str(preset.get("name", "Unnamed preset")).strip() or "Unnamed preset",
        "enabled": bool(preset.get("enabled", True)),
        "active_modules": get_active_preset_module_labels(slot_id),
        "prompt": prompt,
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
        logger.warning("璇诲彇 JSON 澶辫触锛屼娇鐢ㄩ粯璁ゅ€? %s (%s)", path, exc)
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def persist_json(path: Path, payload: Any, *, detail: str, status_code: int = 500) -> None:
    try:
        write_json(path, payload)
    except OSError as exc:
        logger.exception("鍐欏叆 JSON 澶辫触: %s", path)
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
            detail="Background image URLs must be http/https or a /static/uploads/ local path.",
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
    if sprite_base_path == DEFAULT_SPRITE_BASE_PATH or sprite_base_path.startswith(f"{DEFAULT_SPRITE_BASE_PATH}/"):
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


def sanitize_slot_id(value: Any, default: str | None = None) -> str:
    return GLOBAL_RUNTIME_ID


def sanitize_legacy_slot_id(value: Any, default: str | None = None) -> str:
    slot_id = str(value or "").strip()
    if slot_id in LEGACY_SLOT_IDS:
        return slot_id
    return default or LEGACY_SLOT_IDS[0]


def sanitize_slot_registry(raw: Any) -> dict[str, Any]:
    return default_slot_registry()
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
            name = str(item.get("name", "")).strip() or f"瀛樻。 {index}"
            slots.append({"id": slot_id, "name": name[:32]})

    for index, slot_id in enumerate(DEFAULT_SLOT_IDS, start=1):
        if slot_id not in seen:
            slots.append({"id": slot_id, "name": f"瀛樻。 {index}"})

    active_slot = sanitize_slot_id(raw.get("active_slot"), DEFAULT_SLOT_IDS[0])
    return {"active_slot": active_slot, "slots": slots}


def get_slot_registry() -> dict[str, Any]:
    return sanitize_slot_registry(read_json(SLOT_META_PATH, default_slot_registry()))


def save_slot_registry(registry: dict[str, Any]) -> dict[str, Any]:
    return sanitize_slot_registry(registry)
    sanitized = sanitize_slot_registry(registry)
    persist_json(
        SLOT_META_PATH,
        sanitized,
        detail="Slot registry save failed. Please check disk space or file permissions.",
    )
    return sanitized


def get_active_slot_id() -> str:
    return GLOBAL_RUNTIME_ID
    return get_slot_registry()["active_slot"]


def get_slot_name(slot_id: str | None = None) -> str:
    return GLOBAL_RUNTIME_NAME
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    for item in get_slot_registry()["slots"]:
        if item["id"] == target:
            return item["name"]
    return target


def slot_summary(slot_id: str | None = None) -> dict[str, Any]:
    current_card = get_current_card()
    workshop_state = get_workshop_state()
    return {
        "id": GLOBAL_RUNTIME_ID,
        "name": GLOBAL_RUNTIME_NAME,
        "persona_name": get_persona().get("name", ""),
        "memory_count": len(get_memories()),
        "worldbook_count": len(get_worldbook()),
        "conversation_count": len(get_conversation()),
        "current_card_name": current_card.get("source_name", ""),
        "workshop_temp": workshop_state.get("temp", 0),
        "workshop_stage": get_workshop_stage(workshop_state.get("temp", 0)),
    }
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    current_card = get_current_card(target)
    workshop_state = get_workshop_state(target)
    return {
        "id": target,
        "name": get_slot_name(target),
        "persona_name": get_persona(target).get("name", ""),
        "memory_count": len(get_memories(target)),
        "worldbook_count": len(get_worldbook(target)),
        "conversation_count": len(get_conversation(target)),
        "current_card_name": current_card.get("source_name", ""),
        "workshop_temp": workshop_state.get("temp", 0),
        "workshop_stage": get_workshop_stage(workshop_state.get("temp", 0)),
    }


def get_slot_dir(slot_id: str | None = None) -> Path:
    return DATA_DIR
    return SLOTS_DIR / sanitize_slot_id(slot_id, get_active_slot_id())


def persona_path(slot_id: str | None = None) -> Path:
    return global_persona_path()
    return get_slot_dir(slot_id) / "persona.json"


def legacy_slot_dir(slot_id: str | None = None) -> Path:
    return SLOTS_DIR / sanitize_legacy_slot_id(slot_id, LEGACY_SLOT_IDS[0])


def legacy_persona_path(slot_id: str | None = None) -> Path:
    return legacy_slot_dir(slot_id) / "persona.json"


def global_persona_path() -> Path:
    return LEGACY_PERSONA_PATH


def conversation_path(slot_id: str | None = None) -> Path:
    return LEGACY_CONVERSATION_PATH
    return get_slot_dir(slot_id) / "conversations.json"


def settings_path(slot_id: str | None = None) -> Path:
    return LEGACY_SETTINGS_PATH
    return get_slot_dir(slot_id) / "settings.json"


def memories_path(slot_id: str | None = None) -> Path:
    return LEGACY_MEMORIES_PATH
    return get_slot_dir(slot_id) / "memories.json"


def worldbook_path(slot_id: str | None = None) -> Path:
    return LEGACY_WORLDBOOK_PATH
    return get_slot_dir(slot_id) / "worldbook.json"


def current_card_path(slot_id: str | None = None) -> Path:
    return global_current_card_path()
    return get_slot_dir(slot_id) / "current_role_card.json"


def legacy_current_card_path(slot_id: str | None = None) -> Path:
    return legacy_slot_dir(slot_id) / "current_role_card.json"


def global_current_card_path() -> Path:
    return LEGACY_CURRENT_CARD_PATH


def workshop_state_path(slot_id: str | None = None) -> Path:
    return GLOBAL_WORKSHOP_STATE_PATH
    return get_slot_dir(slot_id) / "creative_workshop_state.json"


def user_profile_path(slot_id: str | None = None) -> Path:
    return GLOBAL_USER_PROFILE_PATH
    return get_slot_dir(slot_id) / "user_profile.json"


def avatar_upload_url(filename: str) -> str:
    safe_name = Path(str(filename or "")).name
    return f"/static/uploads/{safe_name}" if safe_name else ""


def remove_upload_variants(prefix: str) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for path in UPLOAD_DIR.glob(f"{prefix}.*"):
        if path.is_file():
            path.unlink(missing_ok=True)


def save_image_upload_for_slot(
    *,
    file: UploadFile,
    prefix: str,
    empty_detail: str,
    too_large_detail: str,
    invalid_type_detail: str,
    save_failed_detail: str,
) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail=invalid_type_detail)
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=invalid_type_detail)
    content = file.file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail=empty_detail)
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=too_large_detail)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    remove_upload_variants(prefix)
    target = UPLOAD_DIR / f"{prefix}{suffix}"
    try:
        target.write_bytes(content)
    except OSError as exc:
        logger.exception("Avatar write failed: %s", target)
        raise HTTPException(status_code=500, detail=save_failed_detail) from exc
    return avatar_upload_url(target.name)


def workshop_asset_dir(kind: str) -> Path:
    normalized = "image" if str(kind or "").strip().lower() == "image" else "music"
    return UPLOAD_DIR / "workshop" / normalized


def workshop_asset_url(kind: str, filename: str) -> str:
    normalized = "image" if str(kind or "").strip().lower() == "image" else "music"
    safe_name = Path(str(filename or "")).name
    return f"/static/uploads/workshop/{normalized}/{safe_name}" if safe_name else ""


async def save_workshop_asset_upload(*, kind: str, file: UploadFile) -> dict[str, Any]:
    normalized_kind = "image" if str(kind or "").strip().lower() == "image" else "music"
    suffix = Path(file.filename or "").suffix.lower()
    allowed_suffixes = ALLOWED_IMAGE_SUFFIXES if normalized_kind == "image" else ALLOWED_AUDIO_SUFFIXES
    if suffix not in allowed_suffixes:
        if normalized_kind == "image":
            raise HTTPException(status_code=400, detail="Creative workshop images only support png / jpg / jpeg / webp / gif.")
        raise HTTPException(status_code=400, detail="Creative workshop audio only supports mp3 / wav / ogg / m4a / aac / flac / webm.")

    content_type = str(file.content_type or "").strip().lower()
    if normalized_kind == "image":
        if content_type and content_type != "application/octet-stream" and not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="The selected file is not an image.")
    else:
        if content_type and content_type != "application/octet-stream" and not (
            content_type.startswith("audio/") or content_type.startswith("video/")
        ):
            raise HTTPException(status_code=400, detail="The selected file is not audio.")

    content = await file.read(MAX_WORKSHOP_UPLOAD_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Upload file cannot be empty.")
    if len(content) > MAX_WORKSHOP_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Workshop assets cannot be larger than 25 MB.")

    normalized_stem = sanitize_sprite_filename_tag(Path(file.filename or "").stem) or f"workshop_{normalized_kind}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    directory = workshop_asset_dir(normalized_kind)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{timestamp}_{normalized_stem}{suffix}"
    try:
        target.write_bytes(content)
    except OSError as exc:
        logger.exception("Workshop asset write failed: %s", target)
        raise HTTPException(status_code=500, detail="Workshop asset save failed. Please check disk space or file permissions.") from exc

    return {
        "ok": True,
        "kind": normalized_kind,
        "filename": target.name,
        "url": workshop_asset_url(normalized_kind, target.name),
    }


def reset_slot_data(slot_id: str) -> dict[str, Any]:
    persist_json(conversation_path(), [], detail="Workspace reset failed: could not clear chat history.")
    persist_json(settings_path(), sanitize_settings(DEFAULT_SETTINGS), detail="Workspace reset failed: could not reset settings.")
    persist_json(memories_path(), [], detail="Workspace reset failed: could not clear memories.")
    persist_json(worldbook_path(), {}, detail="Workspace reset failed: could not clear worldbook.")
    persist_json(worldbook_runtime_state_path(), default_worldbook_runtime_state(), detail="Workspace reset failed: could not reset worldbook runtime state.")
    reset_workshop_state()
    persist_json(user_profile_path(), default_user_profile(), detail="Workspace reset failed: could not reset user profile.")
    persist_json(preset_path(), default_preset_store(), detail="Workspace reset failed: could not reset presets.")
    remove_upload_variants("user_avatar")
    remove_upload_variants("role_avatar")
    return slot_summary()


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
    card["creativeWorkshop"] = sanitize_creative_workshop(raw.get("creativeWorkshop", {}))

    # Preserve every imported plot stage instead of only the built-in A/B/C slots.
    raw_plot_stages = raw.get("plotStages", {})
    normalized_plot_stages: dict[str, dict[str, str]] = {}
    if isinstance(raw_plot_stages, dict):
        for source_key, value in raw_plot_stages.items():
            stage_key = str(source_key).strip()
            if not stage_key or not isinstance(value, dict):
                continue
            normalized_plot_stages[stage_key] = {
                "description": str(value.get("description", "")).strip(),
                "rules": str(value.get("rules", "")).strip(),
            }
    if normalized_plot_stages:
        card["plotStages"] = normalized_plot_stages

    # Preserve every imported persona instead of mapping into the default 1/2/3 slots.
    raw_personas = raw.get("personas", {})
    normalized_personas: dict[str, dict[str, str]] = {}
    if isinstance(raw_personas, dict):
        persona_items: list[tuple[str, Any]] = list(raw_personas.items())
    elif isinstance(raw_personas, list):
        persona_items = [(str(index), item) for index, item in enumerate(raw_personas, start=1)]
    else:
        persona_items = []

    for source_key, value in persona_items:
        persona_key = str(source_key).strip()
        if not persona_key or not isinstance(value, dict):
            continue

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
            elif source_name:
                display_name = source_name

        normalized_personas[persona_key] = {
            "name": display_name,
            "description": str(value.get("description", "")).strip(),
            "personality": str(value.get("personality", "")).strip(),
            "scenario": str(value.get("scenario", "")).strip(),
            "creator_notes": str(value.get("creator_notes", "")).strip(),
        }

    if normalized_personas:
        card["personas"] = normalized_personas

    return card

def extract_persona_name_from_fields(*texts: str) -> str:
    patterns = [
        r"姓名[:：]\s*([^\n,，。；;]{1,16})",
        r"名为([^\n,，。；;]{1,16})",
        r"^([^\n,，。；;]{1,16})[:：]",
        r"^([^\n,，。；;]{1,16})[：:]",
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
        "Config 椤甸潰濉啓鑱婂ぉ妯″瀷",
        "请先去配置页面",
        "本地演示模式",
        "Config 页面",
    ]
    return any(marker in text for marker in markers)


def is_garbled_placeholder_message(content: str) -> bool:
    text = str(content or "").strip()
    if len(text) < 3:
        return False
    return set(text) <= {"?"}


def normalize_legacy_message_content(role: str, content: str) -> str:
    text = str(content or "")
    if role != "assistant":
        return text

    stripped = text.lstrip()
    if stripped.startswith("??????"):
        remainder = stripped.lstrip("?").lstrip(":").lstrip()
        return f"Error: {remainder}" if remainder else "Error."
    return text


def sanitize_conversation(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    cleaned: list[dict[str, Any]] = []
    changed = False

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
        logger.info("Detected legacy demo messages and filtered them from chat history.")
    return cleaned


def legacy_active_slot_id() -> str:
    raw = read_json(SLOT_META_PATH, {})
    if isinstance(raw, dict):
        slot_id = str(raw.get("active_slot", "")).strip()
        if slot_id in LEGACY_SLOT_IDS:
            return slot_id
    return ""


def legacy_slot_last_updated(slot_id: str) -> float:
    source_dir = legacy_slot_dir(slot_id)
    timestamps: list[float] = []
    for path in source_dir.glob("*.json"):
        try:
            timestamps.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(timestamps) if timestamps else 0.0


def legacy_slot_seed_order() -> list[str]:
    preferred = legacy_active_slot_id()
    ordered = ([preferred] if preferred else []) + sorted(LEGACY_SLOT_IDS, key=legacy_slot_last_updated, reverse=True)
    seen: set[str] = set()
    result: list[str] = []
    for slot_id in ordered:
        target = sanitize_legacy_slot_id(slot_id, LEGACY_SLOT_IDS[0])
        if target in seen:
            continue
        seen.add(target)
        result.append(target)
    return result


def legacy_slot_has_runtime_data(slot_id: str) -> bool:
    target = sanitize_legacy_slot_id(slot_id, LEGACY_SLOT_IDS[0])
    slot_dir = legacy_slot_dir(target)
    if not slot_dir.exists():
        return False

    conversation_file = slot_dir / "conversations.json"
    settings_file = slot_dir / "settings.json"
    memories_file = slot_dir / "memories.json"
    worldbook_file = slot_dir / "worldbook.json"
    workshop_file = slot_dir / "creative_workshop_state.json"
    user_profile_file = slot_dir / "user_profile.json"
    preset_file = slot_dir / PRESET_FILENAME

    return any(
        (
            sanitize_conversation(read_json(conversation_file, [])),
            sanitize_settings(read_json(settings_file, {}), slot_id=GLOBAL_RUNTIME_ID) != sanitize_settings(DEFAULT_SETTINGS),
            sanitize_memories(read_json(memories_file, [])),
            sanitize_worldbook_store(read_json(worldbook_file, {}))["entries"],
            sanitize_workshop_state(read_json(workshop_file, default_workshop_state())) != default_workshop_state(),
            sanitize_user_profile(read_json(user_profile_file, {})) != default_user_profile(),
            sanitize_preset_store(read_json(preset_file, {})) != default_preset_store(),
        )
    )


def migrate_legacy_avatar_upload(prefix: str, legacy_slot_id: str) -> None:
    existing = [
        path
        for path in UPLOAD_DIR.glob(f"{prefix}.*")
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES
    ]
    if existing:
        return
    for path in sorted(UPLOAD_DIR.glob(f"{prefix}_{legacy_slot_id}.*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            continue
        shutil.copy2(path, UPLOAD_DIR / f"{prefix}{path.suffix.lower()}")
        return


def migrate_legacy_sprite_assets(legacy_slot_id: str) -> None:
    existing = [
        path
        for path in SPRITES_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES
    ] if SPRITES_DIR.exists() else []
    if existing:
        return

    source_dir = SPRITES_DIR / legacy_slot_id
    if not source_dir.exists():
        return

    for path in source_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            continue
        shutil.copy2(path, SPRITES_DIR / path.name)


def migrate_slot_runtime_to_global_files() -> None:
    if GLOBAL_RUNTIME_MIGRATION_MARKER_PATH.exists():
        return

    source_slot = next((slot_id for slot_id in legacy_slot_seed_order() if legacy_slot_has_runtime_data(slot_id)), "")
    if not source_slot:
        GLOBAL_RUNTIME_MIGRATION_MARKER_PATH.write_text("no-legacy-slot-data", encoding="utf-8")
        return

    source_dir = legacy_slot_dir(source_slot)
    persist_json(
        conversation_path(),
        sanitize_conversation(read_json(source_dir / "conversations.json", [])),
        detail="Workspace migration failed while importing chat history.",
    )
    persist_json(
        settings_path(),
        sanitize_settings(read_json(source_dir / "settings.json", {}), slot_id=GLOBAL_RUNTIME_ID),
        detail="Workspace migration failed while importing settings.",
    )
    persist_json(
        memories_path(),
        sanitize_memories(read_json(source_dir / "memories.json", [])),
        detail="Workspace migration failed while importing memories.",
    )
    persist_json(
        worldbook_path(),
        sanitize_worldbook_store(read_json(source_dir / "worldbook.json", {})),
        detail="Workspace migration failed while importing worldbook.",
    )
    persist_json(
        workshop_state_path(),
        sanitize_workshop_state(read_json(source_dir / "creative_workshop_state.json", default_workshop_state())),
        detail="Workspace migration failed while importing workshop state.",
    )
    persist_json(
        user_profile_path(),
        sanitize_user_profile(read_json(source_dir / "user_profile.json", {})),
        detail="Workspace migration failed while importing user profile.",
    )
    persist_json(
        preset_path(),
        sanitize_preset_store(read_json(source_dir / PRESET_FILENAME, {})),
        detail="Workspace migration failed while importing presets.",
    )
    migrate_legacy_avatar_upload("user_avatar", source_slot)
    migrate_legacy_avatar_upload("role_avatar", source_slot)
    migrate_legacy_sprite_assets(source_slot)
    GLOBAL_RUNTIME_MIGRATION_MARKER_PATH.write_text(source_slot, encoding="utf-8")
    logger.info("Migrated legacy slot runtime data from %s to the global workspace.", source_slot)


def slot_looks_uninitialized(slot_id: str) -> bool:
    return (
        get_conversation(slot_id) == []
        and get_settings(slot_id) == sanitize_settings(DEFAULT_SETTINGS, slot_id=slot_id)
        and get_memories(slot_id) == []
        and get_worldbook(slot_id) == {}
    )


def has_legacy_root_data() -> bool:
    return any(
        path.exists()
        for path in (
            LEGACY_CONVERSATION_PATH,
            LEGACY_SETTINGS_PATH,
            LEGACY_MEMORIES_PATH,
            LEGACY_WORLDBOOK_PATH,
        )
    )


def migrate_legacy_root_to_primary_slot() -> None:
    migrate_slot_runtime_to_global_files()
    return
    if SLOT_MIGRATION_MARKER_PATH.exists():
        return
    if not has_legacy_root_data():
        SLOT_MIGRATION_MARKER_PATH.write_text("no-legacy-data", encoding="utf-8")
        return
    if not slot_looks_uninitialized(DEFAULT_SLOT_IDS[0]):
        SLOT_MIGRATION_MARKER_PATH.write_text("slot-1-already-in-use", encoding="utf-8")
        return

    persist_json(
        conversation_path(DEFAULT_SLOT_IDS[0]),
        sanitize_conversation(read_json(LEGACY_CONVERSATION_PATH, [])),
        detail="Legacy conversation migration failed. Please check disk space or file permissions.",
    )
    persist_json(
        settings_path(DEFAULT_SLOT_IDS[0]),
        sanitize_settings(read_json(LEGACY_SETTINGS_PATH, {}), slot_id=DEFAULT_SLOT_IDS[0]),
        detail="Legacy settings migration failed. Please check disk space or file permissions.",
    )
    persist_json(
        memories_path(DEFAULT_SLOT_IDS[0]),
        sanitize_memories(read_json(LEGACY_MEMORIES_PATH, [])),
        detail="Legacy memories migration failed. Please check disk space or file permissions.",
    )
    persist_json(
        worldbook_path(DEFAULT_SLOT_IDS[0]),
        sanitize_worldbook(read_json(LEGACY_WORLDBOOK_PATH, {})),
        detail="Legacy worldbook migration failed. Please check disk space or file permissions.",
    )
    SLOT_MIGRATION_MARKER_PATH.write_text("migrated-slot-1", encoding="utf-8")
    logger.info("Migrated legacy data root contents to slot_1.")


def slot_role_state_seed_order() -> list[str]:
    return legacy_slot_seed_order()
    active_slot = get_active_slot_id()
    ordered = [active_slot, *DEFAULT_SLOT_IDS]
    seen: set[str] = set()
    result: list[str] = []
    for slot_id in ordered:
        target = sanitize_slot_id(slot_id, DEFAULT_SLOT_IDS[0])
        if target in seen:
            continue
        seen.add(target)
        result.append(target)
    return result


def seed_global_role_state() -> None:
    seeded_persona: dict[str, Any] | None = None
    for slot_id in slot_role_state_seed_order():
        raw_persona = read_json(legacy_persona_path(slot_id), {})
        if not isinstance(raw_persona, dict):
            continue
        candidate = {
            "name": str(raw_persona.get("name", "")).strip(),
            "system_prompt": str(raw_persona.get("system_prompt", "")).strip(),
            "greeting": str(raw_persona.get("greeting", "")).strip(),
        }
        if any(candidate.values()):
            seeded_persona = candidate
            break

    persona_target = global_persona_path()
    if not persona_target.exists():
        write_json(persona_target, seeded_persona or DEFAULT_PERSONA)
    else:
        normalized_persona = get_persona()
        if seeded_persona and normalized_persona == DEFAULT_PERSONA:
            write_json(persona_target, seeded_persona)
        elif normalized_persona != read_json(persona_target, {}):
            write_json(persona_target, normalized_persona)

    seeded_card: dict[str, Any] | None = None
    for slot_id in slot_role_state_seed_order():
        raw_card = read_json(legacy_current_card_path(slot_id), {})
        if not isinstance(raw_card, dict):
            continue
        source_name = str(raw_card.get("source_name", "")).strip()
        raw_payload = raw_card.get("raw", {})
        normalized_payload = normalize_role_card(raw_payload) if isinstance(raw_payload, dict) else default_role_card()
        if source_name or normalized_payload != default_role_card():
            seeded_card = {
                "source_name": source_name,
                "raw": normalized_payload,
            }
            break

    card_target = global_current_card_path()
    if not card_target.exists():
        write_json(card_target, seeded_card or {})
    else:
        normalized_card = get_current_card()
        is_blank_card = (
            not str(normalized_card.get("source_name", "")).strip()
            and normalize_role_card(normalized_card.get("raw", {})) == default_role_card()
        )
        if seeded_card and is_blank_card:
            write_json(card_target, seeded_card)
        elif normalized_card != read_json(card_target, {}):
            write_json(card_target, normalized_card)


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SPRITES_DIR.mkdir(parents=True, exist_ok=True)
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    if not conversation_path().exists():
        write_json(conversation_path(), [])
    if not settings_path().exists():
        write_json(settings_path(), sanitize_settings(DEFAULT_SETTINGS))
    else:
        normalized_settings = sanitize_settings(read_json(settings_path(), {}))
        if normalized_settings != read_json(settings_path(), {}):
            write_json(settings_path(), normalized_settings)
    if not memories_path().exists():
        write_json(memories_path(), [])
    if not worldbook_path().exists():
        write_json(worldbook_path(), sanitize_worldbook_store({}))
    if not workshop_state_path().exists():
        write_json(workshop_state_path(), default_workshop_state())
    if not user_profile_path().exists():
        write_json(user_profile_path(), default_user_profile())
    if not worldbook_runtime_state_path().exists():
        write_json(worldbook_runtime_state_path(), default_worldbook_runtime_state())
    if not preset_path().exists():
        write_json(preset_path(), default_preset_store())
    migrate_slot_runtime_to_global_files()
    seed_global_role_state()
    return
    if not SLOT_META_PATH.exists():
        write_json(SLOT_META_PATH, default_slot_registry())

    registry = get_slot_registry()
    if registry != read_json(SLOT_META_PATH, {}):
        write_json(SLOT_META_PATH, registry)

    for slot_id in DEFAULT_SLOT_IDS:
        slot_dir = get_slot_dir(slot_id)
        slot_dir.mkdir(parents=True, exist_ok=True)
        sprite_dir_path(slot_id).mkdir(parents=True, exist_ok=True)
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
        if not workshop_state_path(slot_id).exists():
            write_json(workshop_state_path(slot_id), default_workshop_state())
        if not user_profile_path(slot_id).exists():
            write_json(user_profile_path(slot_id), default_user_profile())
        if not preset_path(slot_id).exists():
            write_json(preset_path(slot_id), default_preset_store())
    migrate_legacy_root_to_primary_slot()
    seed_global_role_state()


def get_persona(slot_id: str | None = None) -> dict[str, Any]:
    persona = DEFAULT_PERSONA.copy()
    persona.update(read_json(global_persona_path(), {}))
    return persona


def get_conversation(slot_id: str | None = None) -> list[dict[str, Any]]:
    path = conversation_path(slot_id)
    history = sanitize_conversation(read_json(path, []))
    stored = read_json(path, [])
    if history != stored:
        persist_json(
            path,
            history,
            detail="Chat history cleanup failed. Please check disk space or file permissions.",
        )
    return history


def get_settings(slot_id: str | None = None) -> dict[str, Any]:
    target = sanitize_slot_id(slot_id, get_active_slot_id())
    return sanitize_settings(read_json(settings_path(target), {}), slot_id=target)


def sanitize_user_profile(payload: Any, *, slot_id: str | None = None) -> dict[str, Any]:
    base = default_user_profile()
    if isinstance(payload, dict):
        base["display_name"] = str(payload.get("display_name", base["display_name"])).strip()[:24] or "User"
        base["nickname"] = str(payload.get("nickname", "")).strip()[:40]
        base["profile_text"] = str(payload.get("profile_text", "")).strip()[:4000]
        base["notes"] = str(payload.get("notes", "")).strip()[:1000]
        avatar_url = str(payload.get("avatar_url", "")).strip()
        if avatar_url.startswith("/static/uploads/"):
            base["avatar_url"] = avatar_url
    avatar_prefix = "user_avatar"
    role_prefix = "role_avatar"
    for path in sorted(UPLOAD_DIR.glob(f"{avatar_prefix}.*")):
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            base["avatar_url"] = avatar_upload_url(path.name)
            break
    base["role_avatar_url"] = ""
    for path in sorted(UPLOAD_DIR.glob(f"{role_prefix}.*")):
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            base["role_avatar_url"] = avatar_upload_url(path.name)
            break
    return base


def get_user_profile(slot_id: str | None = None) -> dict[str, Any]:
    return sanitize_user_profile(read_json(user_profile_path(), {}))


def save_user_profile(payload: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    existing = get_user_profile()
    merged = {**existing, **payload}
    sanitized = sanitize_user_profile(merged)
    persist_json(user_profile_path(), sanitized, detail="User profile save failed. Please check disk space or file permissions.")
    return sanitized


def get_role_avatar_url(slot_id: str | None = None) -> str:
    return str(get_user_profile(slot_id).get("role_avatar_url", "")).strip()


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
        detail="Memory save failed. Please check disk space or file permissions.",
    )
    return sanitized


def save_worldbook(entries: dict[str, str], slot_id: str | None = None) -> dict[str, str]:
    sanitized = sanitize_worldbook(entries)
    persist_json(
        worldbook_path(slot_id),
        {"settings": get_worldbook_settings(slot_id), "entries": [{"trigger": key, "content": value} for key, value in sanitized.items()]},
        detail="Worldbook save failed. Please check disk space or file permissions.",
    )
    return sanitized


def save_worldbook_store(store: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    sanitized = sanitize_worldbook_store(store)
    persist_json(
        worldbook_path(slot_id),
        sanitized,
        detail="Worldbook save failed. Please check disk space or file permissions.",
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
    data = read_json(global_current_card_path(), {})
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
            raise HTTPException(status_code=500, detail="Role card file read failed.") from exc
    raise HTTPException(status_code=400, detail="Role card file encoding could not be detected. Please convert it to UTF-8 or UTF-8 with BOM.")


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
    for key in ["name", "description", "personality", "first_mes", "mes_example", "scenario", "creator_notes", "tags", "creativeWorkshop", "plotStages", "personas"]:
        if not merged.get(key) and data.get(key):
            merged[key] = data.get(key)

    return merged


def parse_role_card_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Role card JSON cannot be empty.")

    try:
        data = json.loads(raw)
    except ValueError:
        repaired = repair_deepseek_card_json(raw)
        try:
            data = json.loads(repaired)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Role card JSON parse failed: {exc}") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Role card JSON root must be an object.")
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
                "title": str(card.get("name", "")).strip() or "瑙掕壊鍩虹璁惧畾",
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
                        "title": f"鍓ф儏闃舵 {key}",
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
                        "title": str(value.get("name", "")).strip() or f"瑙掕壊 {key}",
                        "content": content,
                        "tags": ["persona", key],
                        "notes": str(value.get("creator_notes", "")).strip(),
                    }
                )

    return sanitize_memories(memories)


def apply_role_card(card: dict[str, Any], *, source_name: str = "", slot_id: str | None = None) -> dict[str, Any]:
    normalized_card = normalize_role_card(card)
    target_slot = sanitize_slot_id(slot_id, get_active_slot_id())
    next_source_name = Path(str(source_name or "").strip()).name
    persona = build_persona_from_role_card(normalized_card)
    current_settings = get_settings(target_slot)
    current_memories = get_memories(target_slot)
    current_worldbook_store = get_worldbook_store(target_slot)

    persist_json(
        global_persona_path(),
        persona,
        detail="Failed to write role settings. Please check persona.json permissions.",
    )
    current_card = {
        "source_name": next_source_name,
        "raw": normalized_card,
    }
    persist_json(
        global_current_card_path(),
        current_card,
        detail="Failed to save current card data. Please check file permissions.",
    )

    return {
        "persona": persona,
        "card": current_card,
        "current_memory_count": len(current_memories),
        "current_worldbook_count": len(current_worldbook_store["entries"]),
        "current_background_image_url": str(current_settings.get("background_image_url", "")).strip(),
        "current_background_overlay": clamp_float(
            current_settings.get("background_overlay"),
            0.0,
            0.85,
            DEFAULT_SETTINGS["background_overlay"],
        ),
    }


def save_workshop_card(workshop: dict[str, Any], *, slot_id: str | None = None) -> dict[str, Any]:
    target_slot = sanitize_slot_id(slot_id, get_active_slot_id())
    current_card = get_current_card(target_slot)
    current_raw = current_card.get("raw", {})
    if not isinstance(current_raw, dict):
        current_raw = {}

    updated_raw = json.loads(json.dumps(current_raw, ensure_ascii=False))
    updated_raw["creativeWorkshop"] = sanitize_creative_workshop(workshop)
    normalized_card = normalize_role_card(updated_raw)
    source_name = str(current_card.get("source_name", "")).strip()
    if not source_name:
        source_name = "role_card.json"
    source_path = CARDS_DIR / Path(source_name).name

    persist_json(
        source_path,
        normalized_card,
        detail="Creative workshop config save failed. Could not write the role card file.",
    )
    current_card_payload = {
        "source_name": source_path.name,
        "raw": normalized_card,
    }
    persist_json(
        global_current_card_path(),
        current_card_payload,
        detail="Creative workshop config save failed. Could not update the current card record.",
    )
    return {
        "current_card": current_card_payload,
        "card": normalized_card,
        "workshop": sanitize_creative_workshop(updated_raw["creativeWorkshop"]),
        "workshop_state": get_workshop_state(target_slot),
    }


def sanitize_runtime_overrides(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    default_sprite_path = default_sprite_base_path_for_slot()
    sprite_base_path = str(source.get("sprite_base_path", default_sprite_path)).strip() or default_sprite_path
    if sprite_base_path == DEFAULT_SPRITE_BASE_PATH or sprite_base_path.startswith(f"{DEFAULT_SPRITE_BASE_PATH}/"):
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
        detail="Chat history save failed. Please check disk space or file permissions.",
    )


def build_memory_text(memory: dict[str, Any], fields: list[str]) -> str:
    parts: list[str] = []
    if "title" in fields and memory.get("title"):
        parts.append(f"Title: {memory['title']}")
    if "content" in fields and memory.get("content"):
        parts.append(f"Content: {memory['content']}")
    if "tags" in fields and memory.get("tags"):
        parts.append(f"Tags: {'、'.join(memory['tags'])}")
    if "notes" in fields and memory.get("notes"):
        parts.append(f"Notes: {memory['notes']}")
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
        raise HTTPException(status_code=502, detail="妯″瀷杩斿洖鐨勪笉鏄悎娉?JSON") from last_error

    detail = f"妯″瀷璇锋眰澶辫触: {last_error}"
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
        raise HTTPException(status_code=400, detail="Please enter a chat model API URL first.")

    try:
        async with httpx.AsyncClient(timeout=float(request_timeout)) as client:
            response = await client.get(url, headers=build_headers(api_key))
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text.strip() if exc.response is not None else ""
        detail = response_text[:500] if response_text else str(exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch model list: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch model list: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Model list endpoint did not return valid JSON.") from exc

    rows = data.get("data", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="Model list endpoint returned an invalid format.")

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
        raise HTTPException(status_code=502, detail="Model response format is invalid.") from exc

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
        raise HTTPException(status_code=502, detail="Embedding model response format is invalid.")

    vectors: list[list[float]] = []
    for row in rows:
        vector = row.get("embedding", []) if isinstance(row, dict) else []
        if not isinstance(vector, list):
            raise HTTPException(status_code=502, detail="Embedding model response format is invalid.")
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
        logger.warning("Rerank model returned a non-list result; falling back to original documents.")
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



def default_worldbook_runtime_state() -> dict[str, Any]:
    return {"turn_index": 0, "entries": {}}


def worldbook_runtime_state_path(slot_id: str | None = None) -> Path:
    return GLOBAL_WORLDBOOK_RUNTIME_STATE_PATH


def sanitize_worldbook_runtime_state(raw: Any) -> dict[str, Any]:
    state = default_worldbook_runtime_state()
    if not isinstance(raw, dict):
        return state

    state["turn_index"] = clamp_int(raw.get("turn_index"), 0, 10_000_000, 0)
    raw_entries = raw.get("entries", {})
    if not isinstance(raw_entries, dict):
        return state

    cleaned_entries: dict[str, dict[str, Any]] = {}
    for raw_entry_id, value in raw_entries.items():
        if not isinstance(value, dict):
            continue
        entry_id = str(raw_entry_id or "").strip()
        if not entry_id:
            continue
        cleaned_entries[entry_id] = {
            "active_until_turn": clamp_int(value.get("active_until_turn"), 0, 10_000_000, 0),
            "cooldown_until_turn": clamp_int(value.get("cooldown_until_turn"), 0, 10_000_000, 0),
            "last_trigger_turn": clamp_int(value.get("last_trigger_turn"), 0, 10_000_000, 0),
            "last_roll": clamp_int(value.get("last_roll"), 0, 100, 0),
            "last_result": str(value.get("last_result", "")).strip()[:32],
            "last_reason": str(value.get("last_reason", "")).strip()[:64],
            "matched_text": str(value.get("matched_text", "")).strip()[:240],
        }
    state["entries"] = cleaned_entries
    return state


def get_worldbook_runtime_state(slot_id: str | None = None) -> dict[str, Any]:
    return sanitize_worldbook_runtime_state(read_json(worldbook_runtime_state_path(slot_id), default_worldbook_runtime_state()))


def save_worldbook_runtime_state(payload: dict[str, Any], slot_id: str | None = None) -> dict[str, Any]:
    sanitized = sanitize_worldbook_runtime_state(payload)
    persist_json(
        worldbook_runtime_state_path(slot_id),
        sanitized,
        detail="Worldbook runtime state save failed. Please check disk space or file permissions.",
    )
    return sanitized


def _worldbook_direct_question(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False

    markers = (
        "what", "who", "why", "how", "tell me", "explain", "?", "？",
        "什么", "是谁", "为啥", "为什么", "怎么", "如何", "解释", "告诉我", "说说", "介绍",
    )
    return any(marker in text for marker in markers)




def _normalize_worldbook_insertion_position(value: Any, default: str = "after_char_defs") -> str:
    text = str(value or "").strip().lower()
    return text if text in {"before_char_defs", "after_char_defs", "in_chat"} else default


def _normalize_worldbook_injection_role(value: Any, default: str = "system") -> str:
    text = str(value or "").strip().lower()
    if text in {"system", "user", "assistant"}:
        return text
    return default


def _normalize_worldbook_injection_depth(value: Any, default: int = 0) -> int:
    return clamp_int(value, 0, 3, default)


def _normalize_worldbook_injection_order(value: Any, default: int = 100) -> int:
    return clamp_int(value, 0, 999999, default)


def _worldbook_position_priority(item: dict[str, Any]) -> int:
    position = _normalize_worldbook_insertion_position(item.get("insertion_position", "after_char_defs"), "after_char_defs")
    if position == "in_chat":
        return 0
    if position == "after_char_defs":
        return 1
    return 2


def _worldbook_global_selection_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    order = clamp_int(item.get("order", item.get("priority", 100)), 0, 999999, 100)
    source_rank_map = {"constant": 0, "sticky": 1, "keyword": 2}
    source_rank = source_rank_map.get(str(item.get("source", "keyword")), 2)
    title = str(item.get("title", "")).strip() or str(item.get("trigger", "")).strip()
    return (order, source_rank, title)


def _worldbook_bucket_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    injection_order = _normalize_worldbook_injection_order(
        item.get("injection_order", item.get("order", item.get("priority", 100))),
        100,
    )
    order = clamp_int(item.get("order", item.get("priority", 100)), 0, 999999, 100)
    title = str(item.get("title", "")).strip() or str(item.get("trigger", "")).strip()
    return (injection_order, order, title)


def bucket_worldbook_matches(matches: list[dict[str, Any]] | None) -> dict[str, Any]:
    buckets: dict[str, Any] = {
        "before_char_defs": [],
        "after_char_defs": [],
        "in_chat": {},
    }
    for item in matches or []:
        position = _normalize_worldbook_insertion_position(item.get("insertion_position", "after_char_defs"), "after_char_defs")
        if position == "in_chat":
            depth = _normalize_worldbook_injection_depth(item.get("injection_depth", 0), 0)
            buckets["in_chat"].setdefault(depth, []).append(item)
        elif position == "before_char_defs":
            buckets["before_char_defs"].append(item)
        else:
            buckets["after_char_defs"].append(item)

    buckets["before_char_defs"].sort(key=_worldbook_bucket_sort_key)
    buckets["after_char_defs"].sort(key=_worldbook_bucket_sort_key)
    for depth, items in list(buckets["in_chat"].items()):
        items.sort(key=_worldbook_bucket_sort_key)
        buckets["in_chat"][depth] = items
    return buckets
def _worldbook_entry_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    position_rank = _worldbook_position_priority(item)
    order = clamp_int(item.get("order", item.get("priority", 100)), 0, 999999, 100)
    source_rank_map = {"constant": 0, "sticky": 1, "keyword": 2}
    source_rank = source_rank_map.get(str(item.get("source", "keyword")), 2)
    title = str(item.get("title", "")).strip() or str(item.get("trigger", "")).strip()
    return (position_rank, order, source_rank, title)
def _build_worldbook_runtime_debug_entries(
    current_turn: int,
    entries: list[dict[str, Any]],
    runtime_entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in sorted(entries, key=_worldbook_entry_sort_key):
        entry_id = str(item.get("id", "")).strip()
        runtime = runtime_entries.get(entry_id, {})
        active_until_turn = clamp_int(runtime.get("active_until_turn"), 0, 10_000_000, 0)
        cooldown_until_turn = clamp_int(runtime.get("cooldown_until_turn"), 0, 10_000_000, 0)
        sticky_remaining = max(0, active_until_turn - current_turn)
        cooldown_remaining = max(0, cooldown_until_turn - max(current_turn, active_until_turn))
        rows.append(
            {
                "id": entry_id,
                "title": str(item.get("title", "")).strip(),
                "entry_type": str(item.get("entry_type", "keyword")).strip() or "keyword",
                "group": str(item.get("group", "")).strip(),
                "order": clamp_int(item.get("order", item.get("priority", 100)), 0, 999999, 100),
                "insertion_position": _normalize_worldbook_insertion_position(item.get("insertion_position", "after_char_defs"), "after_char_defs"),
                "injection_depth": _normalize_worldbook_injection_depth(item.get("injection_depth", 0), 0),
                "injection_role": _normalize_worldbook_injection_role(item.get("injection_role", "system"), "system"),
                "injection_order": _normalize_worldbook_injection_order(
                    item.get("injection_order", item.get("order", item.get("priority", 100))),
                    100,
                ),
                "recursive_enabled": bool(item.get("recursive_enabled", True)),
                "prevent_further_recursion": bool(item.get("prevent_further_recursion", False)),
                "chance": clamp_int(item.get("chance", 100), 0, 100, 100),
                "sticky_turns": clamp_int(item.get("sticky_turns", 0), 0, 999, 0),
                "cooldown_turns": clamp_int(item.get("cooldown_turns", 0), 0, 999, 0),
                "active_until_turn": active_until_turn,
                "cooldown_until_turn": cooldown_until_turn,
                "sticky_remaining": sticky_remaining,
                "cooldown_remaining": cooldown_remaining,
                "last_result": str(runtime.get("last_result", "")).strip(),
                "last_reason": str(runtime.get("last_reason", "")).strip(),
                "last_roll": clamp_int(runtime.get("last_roll"), 0, 100, 0),
                "matched_text": str(runtime.get("matched_text", "")).strip(),
            }
        )
    return rows


def _worldbook_alias_match_result(
    text: str,
    aliases: list[str],
    *,
    mode: str,
    case_sensitive: bool,
    whole_word: bool,
) -> tuple[bool, list[str]]:
    if not aliases:
        return False, []

    matches = [
        alias for alias in aliases if keyword_matches_query(text, alias, case_sensitive=case_sensitive, whole_word=whole_word)
    ]
    normalized_mode = str(mode or "any").strip().lower()
    ok = len(matches) == len(aliases) if normalized_mode == "all" else bool(matches)
    return ok, matches


def _evaluate_worldbook_keyword_entry(
    text: str,
    item: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[bool, list[str], list[str], str]:
    case_sensitive = bool(item.get("case_sensitive", settings["default_case_sensitive"]))
    whole_word = bool(item.get("whole_word", settings["default_whole_word"]))

    primary_aliases = split_trigger_aliases(item.get("trigger", ""))
    secondary_aliases = split_trigger_aliases(item.get("secondary_trigger", ""))

    primary_mode = str(item.get("match_mode", settings.get("default_match_mode", "any"))).strip().lower()
    secondary_mode = str(item.get("secondary_mode", settings.get("default_secondary_mode", "all"))).strip().lower()
    group_operator = str(item.get("group_operator", settings.get("default_group_operator", "and"))).strip().lower()
    if group_operator not in {"and", "or"}:
        group_operator = "and"

    primary_ok = False
    primary_matches: list[str] = []
    if primary_aliases:
        primary_ok, primary_matches = _worldbook_alias_match_result(
            text,
            primary_aliases,
            mode=primary_mode,
            case_sensitive=case_sensitive,
            whole_word=whole_word,
        )

    secondary_ok = False
    secondary_matches: list[str] = []
    if secondary_aliases:
        secondary_ok, secondary_matches = _worldbook_alias_match_result(
            text,
            secondary_aliases,
            mode=secondary_mode,
            case_sensitive=case_sensitive,
            whole_word=whole_word,
        )

    if not secondary_aliases:
        final_ok = primary_ok
    elif group_operator == "or":
        final_ok = primary_ok or secondary_ok
    else:
        final_ok = primary_ok and secondary_ok

    matched_text = " / ".join(primary_matches + secondary_matches)
    return final_ok, primary_matches, secondary_matches, matched_text


def _worldbook_match_payload(
    *,
    item: dict[str, Any],
    source: str,
    matched_text: str = "",
    matched_depth: int = 0,
    matched_from: str = "",
) -> dict[str, Any]:
    order = clamp_int(item.get("order", item.get("priority", 100)), 0, 999999, 100)
    insertion_position = _normalize_worldbook_insertion_position(item.get("insertion_position", "after_char_defs"), "after_char_defs")
    injection_depth = _normalize_worldbook_injection_depth(item.get("injection_depth", 0), 0)
    injection_role = _normalize_worldbook_injection_role(item.get("injection_role", "system"), "system")
    injection_order = _normalize_worldbook_injection_order(
        item.get("injection_order", order),
        order,
    )
    return {
        "id": str(item.get("id", "")).strip(),
        "title": str(item.get("title", "")).strip(),
        "trigger": str(item.get("trigger", "")).strip(),
        "secondary_trigger": str(item.get("secondary_trigger", "")).strip(),
        "content": str(item.get("content", "")).strip(),
        "matched": matched_text,
        "comment": str(item.get("comment", "")).strip(),
        "priority": order,
        "order": order,
        "source": source,
        "group": str(item.get("group", "")).strip(),
        "entry_type": str(item.get("entry_type", "keyword")).strip() or "keyword",
        "chance": clamp_int(item.get("chance", 100), 0, 100, 100),
        "sticky_turns": clamp_int(item.get("sticky_turns", 0), 0, 999, 0),
        "cooldown_turns": clamp_int(item.get("cooldown_turns", 0), 0, 999, 0),
        "insertion_position": insertion_position,
        "injection_depth": injection_depth,
        "injection_role": injection_role,
        "injection_order": injection_order,
        "recursive_enabled": bool(item.get("recursive_enabled", True)),
        "prevent_further_recursion": bool(item.get("prevent_further_recursion", False)),
        "matched_depth": clamp_int(matched_depth, 0, 5, 0),
        "matched_from": str(matched_from or "").strip(),
        "selected_for_prompt": False,
        "dropped_reason": "",
    }

def _worldbook_recursive_seed_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in [
        item.get("title", ""),
        item.get("trigger", ""),
        item.get("secondary_trigger", ""),
    ]:
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts).strip()


def _worldbook_runtime_state_row(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "active_until_turn": clamp_int(runtime.get("active_until_turn"), 0, 10_000_000, 0),
        "cooldown_until_turn": clamp_int(runtime.get("cooldown_until_turn"), 0, 10_000_000, 0),
        "last_trigger_turn": clamp_int(runtime.get("last_trigger_turn"), 0, 10_000_000, 0),
        "last_roll": clamp_int(runtime.get("last_roll"), 0, 100, 0),
        "last_result": str(runtime.get("last_result", "")).strip()[:32],
        "last_reason": str(runtime.get("last_reason", "")).strip()[:64],
        "matched_text": str(runtime.get("matched_text", "")).strip()[:240],
    }


def _worldbook_debug_display_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
    return (
        clamp_int(item.get("matched_depth", 0), 0, 99, 0),
        _worldbook_position_priority(item),
        _normalize_worldbook_injection_depth(item.get("injection_depth", 0), 0),
        _normalize_worldbook_injection_order(item.get("injection_order", item.get("order", 100)), 100),
        str(item.get("title", "")).strip() or str(item.get("trigger", "")).strip(),
    )


def match_worldbook_entries(query: str) -> list[dict[str, Any]]:
    global _LAST_WORLDBOOK_DEBUG_SNAPSHOT

    text = str(query or "").strip()
    if not text:
        _LAST_WORLDBOOK_DEBUG_SNAPSHOT = {"query": "", "all_matches": [], "selected_ids": [], "dropped_ids": []}
        return []

    settings = get_worldbook_settings()
    if not settings.get("enabled", True):
        _LAST_WORLDBOOK_DEBUG_SNAPSHOT = {"query": text, "all_matches": [], "selected_ids": [], "dropped_ids": []}
        return []

    runtime_state = get_worldbook_runtime_state()
    current_turn = clamp_int(runtime_state.get("turn_index"), 0, 10_000_000, 0) + 1
    runtime_state["turn_index"] = current_turn

    runtime_entries = runtime_state.get("entries", {}) if isinstance(runtime_state.get("entries"), dict) else {}
    clean_runtime_entries: dict[str, dict[str, Any]] = {}
    hits: list[dict[str, Any]] = []
    hits_by_id: dict[str, dict[str, Any]] = {}
    keyword_candidates: list[dict[str, Any]] = []
    seed_queue: list[dict[str, Any]] = [{"text": text, "depth": 0, "from": ""}]
    recursion_enabled = bool(settings.get("recursive_scan_enabled", False))
    recursion_max_depth = clamp_int(settings.get("recursion_max_depth", 2), 0, 5, 2)

    for item in get_worldbook_entries():
        if not item.get("enabled", True):
            continue

        entry_id = str(item.get("id", "")).strip()
        if not entry_id:
            continue

        entry_type = str(item.get("entry_type", settings.get("default_entry_type", "keyword"))).strip().lower()
        if entry_type not in {"keyword", "constant"}:
            entry_type = "keyword"

        runtime = runtime_entries.get(entry_id, {}) if isinstance(runtime_entries.get(entry_id), dict) else {}
        state_row = _worldbook_runtime_state_row(runtime)
        sticky_turns = clamp_int(item.get("sticky_turns", settings.get("default_sticky_turns", 0)), 0, 999, 0)
        cooldown_turns = clamp_int(item.get("cooldown_turns", settings.get("default_cooldown_turns", 0)), 0, 999, 0)

        candidate = {
            "item": item,
            "entry_id": entry_id,
            "entry_type": entry_type,
            "state_row": state_row,
            "sticky_turns": sticky_turns,
            "cooldown_turns": cooldown_turns,
        }

        if entry_type == "constant":
            state_row["last_result"] = "constant"
            state_row["last_reason"] = "always_on"
            clean_runtime_entries[entry_id] = state_row
            hit = _worldbook_match_payload(item=item, source="constant", matched_text="常驻", matched_depth=0, matched_from="")
            hits.append(hit)
            hits_by_id[entry_id] = hit
            continue

        if state_row["active_until_turn"] >= current_turn and state_row["last_trigger_turn"] < current_turn:
            matched_text = state_row["matched_text"] or str(item.get("trigger", "")).strip()
            state_row["last_result"] = "sticky"
            state_row["last_reason"] = "active"
            clean_runtime_entries[entry_id] = state_row
            hit = _worldbook_match_payload(item=item, source="sticky", matched_text=matched_text, matched_depth=0, matched_from="")
            hits.append(hit)
            hits_by_id[entry_id] = hit
            continue

        if state_row["cooldown_until_turn"] >= current_turn:
            state_row["last_result"] = "cooldown"
            state_row["last_reason"] = "cooldown"
            clean_runtime_entries[entry_id] = state_row
            continue

        keyword_candidates.append(candidate)

    depth = 0
    while seed_queue:
        next_queue: list[dict[str, Any]] = []
        newly_matched_this_depth: list[dict[str, Any]] = []

        for seed in seed_queue:
            seed_text = str(seed.get("text", "")).strip()
            if not seed_text:
                continue
            seed_depth = clamp_int(seed.get("depth", depth), 0, 5, depth)
            seed_from = str(seed.get("from", "")).strip()

            for candidate in keyword_candidates:
                entry_id = candidate["entry_id"]
                if entry_id in hits_by_id:
                    continue

                item = candidate["item"]
                if seed_depth > 0 and not bool(item.get("recursive_enabled", True)):
                    continue

                state_row = candidate["state_row"]
                matched, _primary_matches, _secondary_matches, matched_text = _evaluate_worldbook_keyword_entry(seed_text, item, settings)
                if not matched:
                    continue

                chance = clamp_int(item.get("chance", settings.get("default_chance", 100)), 0, 100, 100)
                roll = random.randint(1, 100)
                state_row["last_roll"] = roll
                state_row["matched_text"] = matched_text[:240]
                if chance < 100 and roll > chance:
                    state_row["last_result"] = "chance_failed"
                    state_row["last_reason"] = "chance"
                    clean_runtime_entries[entry_id] = state_row
                    hits_by_id[entry_id] = {"id": entry_id, "_chance_failed": True}
                    continue

                active_until_turn = current_turn + candidate["sticky_turns"]
                cooldown_until_turn = active_until_turn + candidate["cooldown_turns"]
                state_row["active_until_turn"] = active_until_turn
                state_row["cooldown_until_turn"] = cooldown_until_turn
                state_row["last_trigger_turn"] = current_turn
                state_row["last_result"] = "triggered"
                state_row["last_reason"] = "recursive" if seed_depth > 0 else "keyword"
                clean_runtime_entries[entry_id] = state_row

                hit = _worldbook_match_payload(
                    item=item,
                    source="keyword",
                    matched_text=matched_text,
                    matched_depth=seed_depth,
                    matched_from=seed_from,
                )
                hits.append(hit)
                hits_by_id[entry_id] = hit
                newly_matched_this_depth.append(hit)

        if not recursion_enabled or depth >= recursion_max_depth:
            break

        if not newly_matched_this_depth:
            break

        for hit in newly_matched_this_depth:
            if not bool(hit.get("recursive_enabled", True)):
                continue
            if bool(hit.get("prevent_further_recursion", False)):
                continue
            seed_text = _worldbook_recursive_seed_text(hit)
            if not seed_text:
                continue
            next_queue.append(
                {
                    "text": seed_text,
                    "depth": clamp_int(hit.get("matched_depth", depth), 0, 5, depth) + 1,
                    "from": str(hit.get("title", "")).strip() or str(hit.get("trigger", "")).strip(),
                }
            )

        depth += 1
        seed_queue = next_queue

    for candidate in keyword_candidates:
        entry_id = candidate["entry_id"]
        if entry_id in clean_runtime_entries:
            continue
        state_row = candidate["state_row"]
        if state_row.get("last_result") == "chance_failed":
            clean_runtime_entries[entry_id] = state_row
            continue
        if entry_id in hits_by_id:
            continue
        state_row["last_result"] = "not_matched"
        state_row["last_reason"] = "keyword"
        clean_runtime_entries[entry_id] = state_row

    runtime_state["entries"] = clean_runtime_entries
    save_worldbook_runtime_state(runtime_state)

    full_hits = [item for item in hits if not item.get("_chance_failed")]
    full_hits.sort(key=_worldbook_global_selection_sort_key)
    max_hits = max(1, int(settings.get("max_hits", DEFAULT_WORLDBOOK_SETTINGS["max_hits"])))
    selected_hits = full_hits[:max_hits]
    selected_ids = {str(item.get("id", "")).strip() for item in selected_hits if str(item.get("id", "")).strip()}

    all_matches_sorted: list[dict[str, Any]] = []
    dropped_ids: list[str] = []
    for item in sorted(full_hits, key=_worldbook_debug_display_sort_key):
        row = dict(item)
        entry_id = str(row.get("id", "")).strip()
        selected_for_prompt = entry_id in selected_ids
        row["selected_for_prompt"] = selected_for_prompt
        row["dropped_reason"] = "" if selected_for_prompt else "max_hits"
        all_matches_sorted.append(row)
        if not selected_for_prompt and entry_id:
            dropped_ids.append(entry_id)

    _LAST_WORLDBOOK_DEBUG_SNAPSHOT = {
        "query": text,
        "all_matches": all_matches_sorted,
        "selected_ids": list(selected_ids),
        "dropped_ids": dropped_ids,
    }

    if selected_hits:
        logger.info("Worldbook hits: %s", ", ".join(item.get("title") or item.get("matched") or item.get("trigger", "") for item in selected_hits))
    return selected_hits


def enforce_worldbook_fact_in_reply(
    user_message: str,
    reply_text: str,
    matches: list[dict[str, Any]],
) -> str:
    if not matches:
        return reply_text

    text = str(reply_text or "").strip()
    if not text or not _worldbook_direct_question(user_message):
        return text

    primary_match = matches[0]
    subject = str(primary_match.get("matched") or primary_match.get("title") or primary_match.get("trigger") or "").strip()
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

    logger.info("Worldbook direct-answer guard applied before reply.")
    return f"{fact}\\n\\n{text}"


def normalize_sprite_tag(tag: str) -> str:
    text = str(tag or "").strip().lower()
    if not text:
        return ""

    replacements = {
        "neutral": "calm",
        "quiet": "calm",
        "relaxed": "calm",
        "angry": "angry",
        "mad": "angry",
        "happy": "happy",
        "sad": "sad",
        "surprised": "surprised",
    }
    return replacements.get(text, text)


def extract_sprite_tag(reply_text: str) -> tuple[str, str]:
    text = str(reply_text or "").strip()
    if not text:
        return "", ""

    match = re.match(r"^\s*\[(?:琛ㄦ儏|emotion)\s*:\s*([^\]\n]{1,32})\]\s*", text, flags=re.IGNORECASE)
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
            "Embedding model returned an unexpected number of vectors: expected %s, got %s; skipping memory recall for this turn.",
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


async def request_model_reply(
    user_message: str,
    retrieved_items: list[dict[str, Any]],
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, str]] | None = None,
    prompt_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm_config = get_runtime_chat_config(runtime_overrides)
    package = prompt_package or build_prompt_package(
        user_message,
        retrieved_items,
        runtime_overrides=runtime_overrides,
        worldbook_matches=worldbook_matches,
    )
    url = build_api_url(llm_config["base_url"], "chat/completions")
    payload = {
        "model": llm_config["model"],
        "messages": package["messages"],
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
        raise HTTPException(status_code=502, detail="Model response format is invalid.") from exc

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
        sprite_tag = "calm"
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
    debug_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not get_worldbook_settings().get("debug_enabled", False):
        return {}

    runtime_state = get_worldbook_runtime_state()
    all_entries = get_worldbook_entries()
    runtime_entries = runtime_state.get("entries", {}) if isinstance(runtime_state.get("entries"), dict) else {}

    snapshot = _copy_worldbook_debug_snapshot(debug_snapshot)
    snapshot_matches = snapshot.get("all_matches", [])
    selected_snapshot = [item for item in snapshot_matches if item.get("selected_for_prompt")]
    dropped_snapshot = [item for item in snapshot_matches if not item.get("selected_for_prompt")]

    buckets = bucket_worldbook_matches(selected_snapshot or worldbook_matches)

    prompt_blocks: list[str] = []
    before_prompt = build_worldbook_prompt(
        buckets["before_char_defs"],
        heading="[before_char_defs] The following worldbook notes must be considered before the character definition.",
    )
    after_prompt = build_worldbook_prompt(
        buckets["after_char_defs"],
        heading="[after_char_defs] The following worldbook notes refine or extend the character definition for this turn.",
    )
    if before_prompt:
        prompt_blocks.append(before_prompt)
    if after_prompt:
        prompt_blocks.append(after_prompt)
    for depth in sorted(buckets.get("in_chat", {})):
        bucket_prompt = build_worldbook_prompt(
            buckets["in_chat"][depth],
            heading=f"[in_chat depth={depth}] The following are in-chat worldbook notes at depth {depth}.",
        )
        if bucket_prompt:
            prompt_blocks.append(bucket_prompt)

    return {
        "turn_index": clamp_int(runtime_state.get("turn_index"), 0, 10_000_000, 0),
        "hit_count": len(selected_snapshot or worldbook_matches),
        "matched_count": len(snapshot_matches) if snapshot_matches else len(worldbook_matches),
        "selected_count": len(selected_snapshot or worldbook_matches),
        "dropped_count": len(dropped_snapshot),
        "prompt": "\n\n".join(prompt_blocks).strip(),
        "guard": build_worldbook_answer_guard(user_message, worldbook_matches),
        "enforced": bool((reply_result or {}).get("worldbook_enforced")),
        "matched": selected_snapshot or worldbook_matches,
        "matched_all": snapshot_matches or worldbook_matches,
        "selected": selected_snapshot or worldbook_matches,
        "dropped": dropped_snapshot,
        "buckets": buckets,
        "entry_states": _build_worldbook_runtime_debug_entries(
            clamp_int(runtime_state.get("turn_index"), 0, 10_000_000, 0),
            all_entries,
            runtime_entries,
        ),
    }
async def stream_model_reply(
    user_message: str,
    retrieved_items: list[dict[str, Any]],
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, str]] | None = None,
    prompt_package: dict[str, Any] | None = None,
):
    llm_config = get_runtime_chat_config(runtime_overrides)
    package = prompt_package or build_prompt_package(
        user_message,
        retrieved_items,
        runtime_overrides=runtime_overrides,
        worldbook_matches=worldbook_matches,
    )
    url = build_api_url(llm_config["base_url"], "chat/completions")
    payload = {
        "model": llm_config["model"],
        "messages": package["messages"],
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
        detail = f"妯″瀷娴佸紡璇锋眰澶辫触: {last_error}"
        if last_error_detail:
            detail = f"{detail} | upstream={last_error_detail}"
        raise HTTPException(status_code=502, detail=detail) from last_error

    reply_result: dict[str, Any] = {
        "reply": enforce_worldbook_fact_in_reply(
            user_message,
            accumulated_visible or accumulated_raw,
            worldbook_matches or [],
        ),
        "sprite_tag": sprite_tag or ("骞抽潤" if llm_config.get("sprite_enabled", True) else ""),
    }
    reply_result["full_reply"] = compose_full_reply(accumulated_think, str(reply_result["reply"]))
    reply_result["think"] = accumulated_think
    reply_result["worldbook_enforced"] = reply_result["reply"] != (accumulated_visible or accumulated_raw)
    yield {"type": "done", **reply_result}


async def generate_reply(
    user_message: str,
    runtime_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    llm_config = get_runtime_chat_config(runtime_overrides)
    retrieved = await retrieve_memories(user_message, runtime_overrides)
    worldbook_matches = match_worldbook_entries(user_message)
    worldbook_debug_snapshot = get_worldbook_debug_snapshot()
    prompt_package = build_prompt_package(
        user_message,
        retrieved,
        runtime_overrides=runtime_overrides,
        worldbook_matches=worldbook_matches,
    )

    if not (llm_config["base_url"] and llm_config["model"]):
        if not llm_config["demo_mode"]:
            raise HTTPException(
                status_code=400,
                detail="Please configure the chat model API URL and model name first, or enable demo mode.",
            )
        return {"reply": "", "sprite_tag": ""}, retrieved, worldbook_matches, prompt_package, worldbook_debug_snapshot

    reply = await request_model_reply(
        user_message,
        retrieved,
        runtime_overrides=runtime_overrides,
        worldbook_matches=worldbook_matches,
        prompt_package=prompt_package,
    )
    return reply, retrieved, worldbook_matches, prompt_package, worldbook_debug_snapshot


def fallback_memory_from_conversation(history: list[dict[str, Any]]) -> dict[str, Any]:
    def compact_text(value: Any, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return text[: max(limit - 3, 0)].rstrip() + "..."

    transcript = build_conversation_transcript(history)
    last_user = next(
        (str(item.get("content", "")).strip() for item in reversed(history) if item.get("role") == "user"),
        "",
    )
    title_source = last_user or transcript or "对话记忆"
    title = compact_text(title_source, 32) or "对话记忆"

    highlighted_turns: list[str] = []
    for item in history[-8:]:
        role = str(item.get("role", "")).strip()
        content = compact_text(item.get("content", ""), 110)
        if role not in {"user", "assistant"} or not content:
            continue
        speaker = "用户" if role == "user" else "AI"
        highlighted_turns.append(f"{speaker}：{content}")

    recent_exchange = " | ".join(highlighted_turns)
    compact = recent_exchange or compact_text(transcript, 420)
    notes_parts = []
    if last_user:
        notes_parts.append(f"用户最后一次请求：{compact_text(last_user, 140)}")
    if highlighted_turns:
        notes_parts.append(f"最近关键轮次：{recent_exchange}")
    return {
        "title": title,
        "content": compact or "系统已为本轮对话生成一条长期记忆摘要。",
        "tags": ["自动记忆", "对话总结"],
        "notes": "\n".join(notes_parts).strip(),
    }


async def request_conversation_summary_with_model(history: list[dict[str, Any]]) -> dict[str, Any]:
    llm_config = get_runtime_chat_config()
    if not (llm_config["base_url"] and llm_config["model"]):
        raise ValueError("chat model is not configured")

    url = build_api_url(llm_config["base_url"], "chat/completions")
    transcript = build_conversation_transcript(history)
    schema_hint = (
        "{\n"
        "  \"title\": \"简短中文标题\",\n"
        "  \"content\": \"一段较详细的中文长期记忆总结，覆盖重要事件、决定、结果、情绪变化和未解决事项\",\n"
        "  \"tags\": [\"标签1\", \"标签2\", \"标签3\"],\n"
        "  \"notes\": \"可选补充细节，例如人名、地名、约定、数字、时间点和待办事项\"\n"
        "}"
    )

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

    def is_mostly_english_summary(payload: dict[str, Any]) -> bool:
        tags = payload.get("tags", [])
        if isinstance(tags, list):
            tags_text = " ".join(str(item) for item in tags)
        else:
            tags_text = str(tags or "")

        combined = " ".join(
            [
                str(payload.get("title", "") or ""),
                str(payload.get("content", "") or ""),
                str(payload.get("notes", "") or ""),
                tags_text,
            ]
        ).strip()

        if not combined:
            return False

        english_count = len(re.findall(r"[A-Za-z]", combined))
        chinese_count = len(re.findall(r"[\u4e00-\u9fff]", combined))
        return english_count >= max(40, chinese_count * 2) and chinese_count < 40

    payload = {
        "model": llm_config["model"],
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是用于长期记忆归档的对话总结器。"
                    "你必须只返回一个严格 JSON 对象。"
                    "不要输出 markdown 代码块、解释、旁白、角色扮演内容、XML 或任何额外文本。"
                    "JSON 对象必须且只能包含这四个键：title、content、tags、notes。"
                    "总结时要记录具体事件，不要只写空泛主题。"
                    "如果发生了多个重要事件，要一并写入。"
                    "优先保留具体信息：请求、决定、承诺、结果、情绪转折、状态变化、后续待处理事项。"
                    "title 必须是简短中文标题，长度不超过 32 个汉字或 64 个 ASCII 字符。"
                    "content 必须是较详细但紧凑的中文总结，通常 2 到 5 句。"
                    "在信息足够时，content 通常不少于 120 个汉字或 220 个 ASCII 字符。"
                    "tags 必须是 2 到 6 个短标签，优先使用简体中文；专有名词可保留原文。"
                    "notes 可以为空，但在有帮助时应补充人名、地点、时间、数字、约定和未解决事项。"
                    "除专有名词、产品名、缩写外，title、content、notes 必须使用简体中文。"
                    "如果原对话以中文为主，禁止输出整段英文总结。"
                    "输出必须以 { 开始，并以 } 结束。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请把下面完整对话总结为一条长期记忆。\n"
                    "不要为了简短而省略重要事件。\n"
                    "重点总结：实际发生了什么、有什么变化、做了什么决定、承诺了什么、后续还有什么重要事项。\n"
                    "只返回 JSON。\n"
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

    try:
        summary = parse_summary_json(text)
        logger.info("Automatic memory summary parsed as strict JSON on first pass.")
    except ValueError:
        logger.warning("Automatic memory summary was not strict JSON, trying one repair pass.")
        repair_payload = {
            "model": llm_config["model"],
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "请把提供的内容修复为一个严格 JSON 对象。"
                        "不要输出 markdown、解释或额外文本。"
                        "对象必须且只能包含这四个键：title、content、tags、notes。"
                        "除专有名词外，title、content、notes 必须使用简体中文。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请将下面内容修复为严格 JSON。\n"
                        "如果原文已经是 JSON，请只修正格式，不要扩写。\n"
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

    if is_mostly_english_summary(summary):
        logger.warning("Automatic memory summary is mostly English, trying one Chinese rewrite pass.")
        rewrite_payload = {
            "model": llm_config["model"],
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 JSON 语言修正器。"
                        "请在不改变原意的前提下，把输入中的长期记忆内容改写为简体中文。"
                        "只返回一个严格 JSON 对象。"
                        "不要输出 markdown、解释或额外文本。"
                        "对象必须且只能包含这四个键：title、content、tags、notes。"
                        "除专有名词、产品名、缩写外，title、content、notes 必须使用简体中文。"
                        "tags 优先使用简体中文，专有名词可保留原文。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请把下面 JSON 中的长期记忆内容改写为简体中文，并保持原意。\n"
                        "不要丢失事件、决定、承诺、结果、情绪变化和未解决事项。\n"
                        "只返回 JSON。\n\n"
                        f"原始 JSON：\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
                    ),
                },
            ],
        }

        try:
            rewrite_data = await request_json(
                url=url,
                api_key=llm_config["api_key"],
                payload=rewrite_payload,
                request_timeout=int(llm_config["request_timeout"]),
            )
            rewrite_text = str(rewrite_data["choices"][0]["message"]["content"]).strip()
            rewritten_summary = parse_summary_json(rewrite_text)
            if not is_mostly_english_summary(rewritten_summary):
                summary = rewritten_summary
                logger.info("Automatic memory summary rewritten into Chinese successfully.")
            else:
                logger.warning("Chinese rewrite pass still looks mostly English, keeping previous summary.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chinese rewrite pass failed, keeping previous summary: %s", exc)

    return summary

def sanitize_memory_summary(payload: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip() or fallback["title"]
    content = str(payload.get("content", "")).strip() or fallback["content"]
    tags = sanitize_tags(payload.get("tags", fallback["tags"])) or ["自动记忆", "对话总结"]
    notes = str(payload.get("notes", "")).strip() or str(fallback.get("notes", "")).strip()

    normalized_content = re.sub(r"\s+", " ", content).strip()
    fallback_content = str(fallback.get("content", "")).strip()
    if len(normalized_content) < 80 and len(fallback_content) > len(normalized_content):
        content = fallback_content

    return {
        "id": f"memory-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "title": title[:60],
        "content": content[:520],
        "tags": tags[:8],
        "notes": notes[:800],
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
        raise HTTPException(status_code=400, detail="There is no conversation to archive yet.")

    memory = await summarize_conversation_to_memory(history)
    memories = get_memories()
    if memories:
        last = memories[-1]
        if last.get("title") == memory["title"] and last.get("content") == memory["content"]:
            persist_json(
                conversation_path(),
                [],
                detail="Conversation archive failed: could not clear the current chat history.",
            )
            return last

    memories.append(memory)
    save_memories(memories)
    persist_json(
        conversation_path(),
        [],
        detail="Conversation archive failed: could not clear the current chat history.",
    )
    return memory


configure_prompt_builder(
    sanitize_tags=sanitize_tags,
    get_persona=get_persona,
    get_conversation=get_conversation,
    get_memories=get_memories,
    get_user_profile=get_user_profile,
    get_runtime_chat_config=get_runtime_chat_config,
    bucket_worldbook_matches=bucket_worldbook_matches,
    normalize_worldbook_injection_role=_normalize_worldbook_injection_role,
    build_preset_prompt=build_preset_prompt,
)

load_env_file()
ensure_data_files()

bootstrap_runtime_layout()

app = FastAPI(title="Xuqi LLM Chat")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
registered_mods = mount_discovered_mods(app, MODS_DIR)
templates.env.globals["registered_mods"] = [mod.to_dict() for mod in registered_mods]



route_ctx = SimpleNamespace(
    ALLOWED_IMAGE_SUFFIXES=ALLOWED_IMAGE_SUFFIXES,
    CARDS_DIR=CARDS_DIR,
    EXPORT_DIR=EXPORT_DIR,
    MAX_BACKGROUND_UPLOAD_SIZE_BYTES=MAX_BACKGROUND_UPLOAD_SIZE_BYTES,
    ROLE_CARD_EXTENSIONS=ROLE_CARD_EXTENSIONS,
    UPLOAD_DIR=UPLOAD_DIR,
    activate_preset_in_store=activate_preset_in_store,
    append_messages=append_messages,
    apply_role_card=apply_role_card,
    archive_current_conversation=archive_current_conversation,
    build_prompt_package=build_prompt_package,
    build_preset_debug_payload=build_preset_debug_payload,
    build_worldbook_debug_payload=build_worldbook_debug_payload,
    conversation_path=conversation_path,
    create_preset_in_store=create_preset_in_store,
    default_sprite_base_path_for_slot=default_sprite_base_path_for_slot,
    delete_preset_from_store=delete_preset_from_store,
    duplicate_preset_in_store=duplicate_preset_in_store,
    evaluate_creative_workshop=evaluate_creative_workshop,
    fetch_available_models=fetch_available_models,
    fetch_embeddings=fetch_embeddings,
    generate_reply=generate_reply,
    get_active_preset=get_active_preset,
    get_active_preset_from_store=get_active_preset_from_store,
    get_active_slot_id=get_active_slot_id,
    get_conversation=get_conversation,
    get_current_card=get_current_card,
    get_memories=get_memories,
    get_mod=lambda slug: next(
        (mod.to_dict() for mod in registered_mods if mod.slug == slug), None
    ),
    get_persona=get_persona,
    get_preset_store=get_preset_store,
    get_role_avatar_url=get_role_avatar_url,
    get_runtime_chat_config=get_runtime_chat_config,
    get_runtime_embedding_config=get_runtime_embedding_config,
    get_settings=get_settings,
    get_slot_dir=get_slot_dir,
    get_slot_name=get_slot_name,
    get_slot_registry=get_slot_registry,
    get_user_profile=get_user_profile,
    global_persona_path=global_persona_path,
    get_workshop_stage=get_workshop_stage,
    get_workshop_stage_label=get_workshop_stage_label,
    get_workshop_state=get_workshop_state,
    get_worldbook_entries=get_worldbook_entries,
    get_worldbook_debug_snapshot=get_worldbook_debug_snapshot,
    get_worldbook_settings=get_worldbook_settings,
    get_worldbook_store=get_worldbook_store,
    list_mods=lambda: [mod.to_dict() for mod in registered_mods],
    list_role_card_files=list_role_card_files,
    list_sprite_assets=list_sprite_assets,
    logger=logger,
    match_worldbook_entries=match_worldbook_entries,
    normalize_role_card=normalize_role_card,
    parse_role_card_json=parse_role_card_json,
    persona_path=persona_path,
    persist_json=persist_json,
    preset_path=preset_path,
    preset_module_rules=PRESET_MODULE_RULES,
    read_json=read_json,
    read_role_card_text=read_role_card_text,
    request_minimal_model_reply=request_minimal_model_reply,
    reset_slot_data=reset_slot_data,
    reset_workshop_state=reset_workshop_state,
    retrieve_memories=retrieve_memories,
    memories_path=memories_path,
    sanitize_creative_workshop=sanitize_creative_workshop,
    sanitize_worldbook_store=sanitize_worldbook_store,
    sanitize_preset_store=sanitize_preset_store,
    sanitize_settings=sanitize_settings,
    sanitize_slot_id=sanitize_slot_id,
    sanitize_sprite_filename_tag=sanitize_sprite_filename_tag,
    save_image_upload_for_slot=save_image_upload_for_slot,
    save_memories=save_memories,
    save_preset_store=save_preset_store,
    save_slot_registry=save_slot_registry,
    save_user_profile=save_user_profile,
    save_workshop_asset_upload=save_workshop_asset_upload,
    save_workshop_card=save_workshop_card,
    save_workshop_state=save_workshop_state,
    save_worldbook_entries=save_worldbook_entries,
    save_worldbook_settings=save_worldbook_settings,
    save_worldbook_store=save_worldbook_store,
    settings_path=settings_path,
    slot_summary=slot_summary,
    sprite_dir_path=sprite_dir_path,
    stream_model_reply=stream_model_reply,
    user_profile_path=user_profile_path,
    workshop_state_path=workshop_state_path,
    worldbook_path=worldbook_path,
    workshop_signature=workshop_signature,
)
route_ctx.slot_runtime_service = SlotRuntimeService(route_ctx)

register_page_routes(app, templates=templates, ctx=route_ctx)
register_config_api_routes(app, ctx=route_ctx)
register_chat_api_routes(app, ctx=route_ctx)
register_mod_api_routes(app, ctx=route_ctx)
