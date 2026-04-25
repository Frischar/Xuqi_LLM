from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field


def get_resource_dir() -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        return Path(bundle_dir)
    return Path(__file__).resolve().parent


RESOURCE_DIR = get_resource_dir()
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
RUNTIME_DIR = APP_DIR / "runtime"
VOICE_LIBRARY_DIR = RUNTIME_DIR / "voices"
VOICE_GPT_DIR = VOICE_LIBRARY_DIR / "gpt"
VOICE_SOVITS_DIR = VOICE_LIBRARY_DIR / "sovits"
VOICE_AUDIO_DIR = VOICE_LIBRARY_DIR / "audio"
SETTINGS_PATH = DATA_DIR / "settings.json"
HISTORY_PATH = DATA_DIR / "history.json"
STATIC_DIR = RESOURCE_DIR / "static"
TEMPLATES_DIR = RESOURCE_DIR / "templates"
LOGS_DIR = RUNTIME_DIR / "logs"
SETUP_LOG_PATH = LOGS_DIR / "setup.log"
SETUP_STATE_PATH = LOGS_DIR / "setup_state.json"
RUNTIME_LOG_PATH = LOGS_DIR / "runtime.log"
BOOTSTRAP_SCRIPT_PATH = APP_DIR / "runtime_bootstrap.py"

SUPPORTED_FORMATS = {"wav", "ogg", "aac", "raw"}
WEIGHT_SUFFIXES = {".ckpt", ".pth", ".pt"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
RUNTIME_DEVICE_OPTIONS = {"auto", "cu126", "cu128", "cpu"}
DEFAULT_API_URL = "http://127.0.0.1:9880"
MAX_MODEL_UPLOAD_SIZE_BYTES = 3 * 1024 * 1024 * 1024
MAX_AUDIO_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024

DEFAULT_VOICE_PROFILE: dict[str, Any] = {
    "id": "default",
    "name": "默认声线",
    "gpt_weights_path": "",
    "sovits_weights_path": "",
    "ref_audio_path": "",
    "prompt_text": "",
    "prompt_lang": "zh",
    "text_lang": "zh",
    "aux_ref_audio_paths": "",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "gpt_sovits",
    "api_url": DEFAULT_API_URL,
    "runtime_root": str((RUNTIME_DIR / "GPT-SoVITS").resolve()),
    "python_path": "",
    "runtime_device": "auto",
    "tts_config_path": "",
    "launch_host": "127.0.0.1",
    "launch_port": 9880,
    "active_voice_id": "default",
    "voice_profiles": [DEFAULT_VOICE_PROFILE],
    "audio_format": "wav",
    "request_timeout": 180,
    "max_text_chars": 6000,
    "top_k": 5,
    "top_p": 1.0,
    "temperature": 1.0,
    "text_split_method": "cut5",
    "batch_size": 1,
    "batch_threshold": 0.75,
    "speed_factor": 1.0,
    "sample_steps": 32,
    "streaming_mode": False,
    "parallel_infer": True,
    "repetition_penalty": 1.35,
    "appearance": {
        "background_image": "",
        "background_overlay": 0.46,
        "panel_opacity": 0.88,
        "blur_strength": 18,
        "accent_color": "#5ec2a8",
    },
}

HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_runtime_process: subprocess.Popen | None = None
_runtime_process_endpoint: tuple[str, int] | None = None
_setup_process: subprocess.Popen | None = None


class AppearanceSettingsPayload(BaseModel):
    background_image: str = ""
    background_overlay: float = Field(default=0.46)
    panel_opacity: float = Field(default=0.88)
    blur_strength: int = Field(default=18)
    accent_color: str = "#5ec2a8"


class VoiceProfilePayload(BaseModel):
    id: str = ""
    name: str = ""
    gpt_weights_path: str = ""
    sovits_weights_path: str = ""
    ref_audio_path: str = ""
    prompt_text: str = ""
    prompt_lang: str = "zh"
    text_lang: str = "zh"
    aux_ref_audio_paths: str = ""


class SettingsPayload(BaseModel):
    api_url: str = DEFAULT_API_URL
    runtime_root: str = ""
    python_path: str = ""
    runtime_device: str = "auto"
    tts_config_path: str = ""
    launch_host: str = "127.0.0.1"
    launch_port: int = 9880
    active_voice_id: str = "default"
    voice_profiles: list[VoiceProfilePayload] = Field(default_factory=list)
    audio_format: str = "wav"
    request_timeout: int = 180
    max_text_chars: int = 6000
    top_k: int = 5
    top_p: float = 1.0
    temperature: float = 1.0
    text_split_method: str = "cut5"
    batch_size: int = 1
    batch_threshold: float = 0.75
    speed_factor: float = 1.0
    sample_steps: int = 32
    streaming_mode: bool = False
    parallel_infer: bool = True
    repetition_penalty: float = 1.35
    appearance: AppearanceSettingsPayload = Field(default_factory=AppearanceSettingsPayload)


class SynthesizePayload(BaseModel):
    text: str = ""
    voice_id: str = ""


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_GPT_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_SOVITS_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    repair_extensionless_voice_audio_files()
    if not SETTINGS_PATH.exists():
        write_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    if not HISTORY_PATH.exists():
        write_json(HISTORY_PATH, [])


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def sanitize_color(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text if HEX_COLOR_RE.match(text) else default


def default_settings_copy() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def default_runtime_root() -> Path:
    return (RUNTIME_DIR / "GPT-SoVITS").resolve()


def runtime_cache_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "Fantareal" / "tts-studio"
    return Path.home() / ".fantareal" / "tts-studio"


def is_ascii_path(path: Path | str) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def windows_short_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    try:
        import ctypes

        text = str(path)
        size = ctypes.windll.kernel32.GetShortPathNameW(text, None, 0)
        if size <= 0:
            return path
        buffer = ctypes.create_unicode_buffer(size)
        result = ctypes.windll.kernel32.GetShortPathNameW(text, buffer, size)
        if result <= 0:
            return path
        return Path(buffer.value)
    except Exception:
        return path


def can_write_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write-test-{uuid4().hex}"
        probe.write_text("ok", encoding="ascii")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def ascii_runtime_asset_cache_root() -> Path:
    candidates: list[Path] = []
    if os.name == "nt":
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Fantareal" / "tts-studio" / "asset-cache")
        if os.environ.get("PROGRAMDATA"):
            candidates.append(Path(os.environ["PROGRAMDATA"]) / "Fantareal" / "tts-studio" / "asset-cache")
        system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\/")
        candidates.append(Path(f"{system_drive}\\FantarealTTSCache"))
    candidates.extend(
        [
            Path(tempfile.gettempdir()) / "FantarealTTSCache",
            runtime_cache_root() / "asset-cache",
            DATA_DIR / "runtime-asset-cache",
        ]
    )

    fallback = candidates[-1]
    for candidate in candidates:
        short_candidate = windows_short_path(candidate)
        if not can_write_directory(short_candidate):
            continue
        if is_ascii_path(short_candidate):
            return short_candidate
        if can_write_directory(candidate) and is_ascii_path(candidate):
            return candidate
        fallback = short_candidate
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def prepare_runtime_audio_path(source: str) -> str:
    source_path = Path(str(source or "").strip())
    if not source_path.is_file():
        return str(source_path)
    stat = source_path.stat()
    digest_source = f"{source_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    digest = hashlib.sha256(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:20]
    suffix = source_path.suffix.lower() if source_path.suffix.lower() in AUDIO_SUFFIXES else ".wav"
    cache_dir = ascii_runtime_asset_cache_root() / "audio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{digest}{suffix}"
    if not target.exists() or target.stat().st_size != stat.st_size:
        shutil.copy2(source_path, target)
    short_target = windows_short_path(target)
    return str(short_target if is_ascii_path(short_target) else target)


def is_runtime_root(path: Path) -> bool:
    return (path / "api_v2.py").exists()


def resolve_runtime_root(settings: dict[str, Any]) -> Path:
    configured = str(settings.get("runtime_root", "") or "").strip()
    if configured:
        configured_path = Path(configured)
        if is_runtime_root(configured_path):
            return configured_path
    fallback = default_runtime_root()
    if is_runtime_root(fallback):
        return fallback
    return Path(configured) if configured else fallback


def compact_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]



TTSVOICE_ALLOWED_EMOTIONS = {"", "happy", "sad", "surprise", "angry", "scare", "hate", "😠"}
TTSVOICE_TAG_RE = re.compile(r"[\[【]TTSVoice[:：](.*?)[\]】]", re.DOTALL)


def normalize_ttsvoice_part(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_ttsvoice_items(raw_text: Any) -> list[dict[str, str]]:
    text = str(raw_text or "")
    items: list[dict[str, str]] = []
    for match in TTSVOICE_TAG_RE.finditer(text):
        inner = match.group(1)
        parts = re.split(r"[:：]", inner, maxsplit=2)
        if len(parts) != 3:
            continue
        speaker = normalize_ttsvoice_part(parts[0])
        emotion = normalize_ttsvoice_part(parts[1]).lower()
        voice_text = normalize_ttsvoice_part(parts[2])
        if emotion == "😠":
            emotion = "angry"
        if not speaker or not voice_text:
            continue
        if emotion not in TTSVOICE_ALLOWED_EMOTIONS:
            continue
        items.append({"speaker": speaker, "emotion": emotion, "text": voice_text})
    return items


def has_ttsvoice_marker(raw_text: Any) -> bool:
    return bool(re.search(r"[\[【]TTSVoice[:：]", str(raw_text or "")))


def resolve_synthesize_text(raw_text: Any) -> str:
    text = str(raw_text or "").strip()
    if not has_ttsvoice_marker(text):
        return text
    voice_texts = [item["text"] for item in extract_ttsvoice_items(text)]
    return "\n".join(voice_texts).strip()


def sanitize_audio_format(value: Any) -> str:
    audio_format = str(value or "").strip().lower()
    return audio_format if audio_format in SUPPORTED_FORMATS else DEFAULT_SETTINGS["audio_format"]


def sanitize_slug(value: Any, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    return text or fallback


def sanitize_filename(value: str, fallback: str = "upload") -> str:
    raw = Path(str(value or "")).name
    suffix = Path(raw).suffix.lower()
    stem_raw = Path(raw).stem if suffix else raw
    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "-", stem_raw).strip(".-") or fallback
    if suffix:
        return f"{stem}{suffix}"
    return stem


def repair_extensionless_voice_audio_files() -> None:
    if not VOICE_AUDIO_DIR.exists():
        return
    extension_names = {suffix.lstrip(".") for suffix in AUDIO_SUFFIXES}
    for path in VOICE_AUDIO_DIR.iterdir():
        if not path.is_file() or path.suffix:
            continue
        extension = path.name.lower()
        if extension not in extension_names:
            continue
        digest = hashlib.sha256(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:8]
        target = path.with_name(f"audio-{digest}.{extension}")
        if target.exists():
            target = path.with_name(f"audio-{digest}-{uuid4().hex[:6]}.{extension}")
        path.rename(target)


def sanitize_existing_file_path(value: Any, suffixes: set[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_file():
        return ""
    if path.suffix.lower() not in suffixes:
        return ""
    return str(path)


def single_supported_file(root: Path, suffixes: set[str]) -> str:
    if not root.exists() or not root.is_dir():
        return ""
    found: list[str] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [item for item in dirs if item not in {".git", ".venv", "__pycache__", "runtime"}]
        for filename in files:
            path = Path(current_root) / filename
            if path.suffix.lower() in suffixes:
                found.append(str(path))
            if len(found) > 1:
                return ""
    return found[0] if len(found) == 1 else ""


def infer_prompt_text_from_ref_audio(value: Any) -> str:
    text = Path(str(value or "")).stem.strip()
    if not text:
        return ""

    text = re.sub(r"^[【\[\(（][^】\]\)）]{1,32}[】\]\)）]\s*", "", text).strip()
    text = text.strip(" \t\r\n-_—:：")
    text = re.sub(r"\s+", " ", text)
    compact = re.sub(r"[\s_\-—:：]+", "", text.lower())
    if not text or compact in {"ref", "reference", "sample", "audio", "voice", "wav", "参考", "参考音频", "音频"}:
        return ""
    if len(text) <= 16 and any(marker in compact for marker in ("ref", "reference", "sample", "audio", "参考", "音频")):
        return ""
    return text[:1200]


def sanitize_runtime_device(value: Any) -> str:
    device = str(value or "").strip().lower()
    return device if device in RUNTIME_DEVICE_OPTIONS else "auto"


def sanitize_appearance_settings(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    defaults = DEFAULT_SETTINGS["appearance"]
    return {
        "background_image": str(data.get("background_image", "") or "").strip(),
        "background_overlay": clamp_float(data.get("background_overlay"), 0.0, 0.92, defaults["background_overlay"]),
        "panel_opacity": clamp_float(data.get("panel_opacity"), 0.5, 0.98, defaults["panel_opacity"]),
        "blur_strength": clamp_int(data.get("blur_strength"), 0, 40, defaults["blur_strength"]),
        "accent_color": sanitize_color(data.get("accent_color"), defaults["accent_color"]),
    }


def sanitize_voice_profile(raw: Any, index: int) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    fallback_id = "default" if index == 0 else f"voice-{index + 1}"
    profile_id = sanitize_slug(data.get("id") or data.get("name"), fallback_id)
    name = str(data.get("name", "") or "").strip() or ("默认声线" if profile_id == "default" else profile_id)
    ref_audio_path = sanitize_existing_file_path(data.get("ref_audio_path", ""), AUDIO_SUFFIXES)
    prompt_text = str(data.get("prompt_text", "") or "").strip()[:1200]
    if not prompt_text and ref_audio_path:
        prompt_text = infer_prompt_text_from_ref_audio(ref_audio_path)
    return {
        "id": profile_id,
        "name": name[:80],
        "gpt_weights_path": sanitize_existing_file_path(data.get("gpt_weights_path", ""), {".ckpt"}),
        "sovits_weights_path": sanitize_existing_file_path(data.get("sovits_weights_path", ""), {".pth", ".pt"}),
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": str(data.get("prompt_lang", "zh") or "zh").strip().lower(),
        "text_lang": str(data.get("text_lang", "zh") or "zh").strip().lower(),
        "aux_ref_audio_paths": str(data.get("aux_ref_audio_paths", "") or "").strip(),
    }


def sanitize_voice_profiles(raw: Any) -> list[dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items[:80]):
        profile = sanitize_voice_profile(item, index)
        base_id = profile["id"]
        unique_id = base_id
        suffix = 2
        while unique_id in seen:
            unique_id = f"{base_id}-{suffix}"
            suffix += 1
        profile["id"] = unique_id
        seen.add(unique_id)
        profiles.append(profile)
    if not profiles:
        profiles = [dict(DEFAULT_VOICE_PROFILE)]
    if len(profiles) == 1:
        if not profiles[0].get("gpt_weights_path"):
            gpt_path = single_supported_file(VOICE_GPT_DIR, {".ckpt"})
            if gpt_path:
                profiles[0]["gpt_weights_path"] = gpt_path
        if not profiles[0].get("sovits_weights_path"):
            sovits_path = single_supported_file(VOICE_SOVITS_DIR, {".pth", ".pt"})
            if sovits_path:
                profiles[0]["sovits_weights_path"] = sovits_path
        if not profiles[0].get("ref_audio_path"):
            audio_path = single_supported_file(VOICE_AUDIO_DIR, AUDIO_SUFFIXES)
            if audio_path:
                profiles[0]["ref_audio_path"] = audio_path
        if not profiles[0].get("prompt_text") and profiles[0].get("ref_audio_path"):
            profiles[0]["prompt_text"] = infer_prompt_text_from_ref_audio(profiles[0]["ref_audio_path"])
    return profiles


def sanitize_settings(raw: Any, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    previous = existing if isinstance(existing, dict) else {}
    settings = default_settings_copy()
    settings.update({key: previous[key] for key in settings if key in previous})

    settings["provider"] = "gpt_sovits"
    settings["api_url"] = str(source.get("api_url", settings["api_url"]) or "").strip().rstrip("/") or DEFAULT_API_URL
    settings["runtime_root"] = str(source.get("runtime_root", settings["runtime_root"]) or "").strip()
    if not is_runtime_root(Path(settings["runtime_root"])):
        settings["runtime_root"] = str(default_runtime_root())
    settings["python_path"] = str(source.get("python_path", settings["python_path"]) or "").strip()
    settings["runtime_device"] = sanitize_runtime_device(source.get("runtime_device", settings["runtime_device"]))
    settings["tts_config_path"] = str(source.get("tts_config_path", settings["tts_config_path"]) or "").strip()
    settings["launch_host"] = str(source.get("launch_host", settings["launch_host"]) or "").strip() or "127.0.0.1"
    settings["launch_port"] = clamp_int(source.get("launch_port", settings["launch_port"]), 1, 65535, settings["launch_port"])
    settings["audio_format"] = sanitize_audio_format(source.get("audio_format", settings["audio_format"]))
    settings["request_timeout"] = clamp_int(source.get("request_timeout", settings["request_timeout"]), 10, 900, settings["request_timeout"])
    settings["max_text_chars"] = clamp_int(source.get("max_text_chars", settings["max_text_chars"]), 500, 30000, settings["max_text_chars"])
    settings["top_k"] = clamp_int(source.get("top_k", settings["top_k"]), 1, 100, settings["top_k"])
    settings["top_p"] = clamp_float(source.get("top_p", settings["top_p"]), 0.05, 1.0, settings["top_p"])
    settings["temperature"] = clamp_float(source.get("temperature", settings["temperature"]), 0.05, 2.0, settings["temperature"])
    settings["text_split_method"] = str(source.get("text_split_method", settings["text_split_method"]) or "cut5").strip()
    settings["batch_size"] = clamp_int(source.get("batch_size", settings["batch_size"]), 1, 64, settings["batch_size"])
    settings["batch_threshold"] = clamp_float(source.get("batch_threshold", settings["batch_threshold"]), 0.0, 1.0, settings["batch_threshold"])
    settings["speed_factor"] = clamp_float(source.get("speed_factor", settings["speed_factor"]), 0.25, 4.0, settings["speed_factor"])
    settings["sample_steps"] = clamp_int(source.get("sample_steps", settings["sample_steps"]), 4, 128, settings["sample_steps"])
    settings["streaming_mode"] = bool(source.get("streaming_mode", settings["streaming_mode"]))
    settings["parallel_infer"] = bool(source.get("parallel_infer", settings["parallel_infer"]))
    settings["repetition_penalty"] = clamp_float(
        source.get("repetition_penalty", settings["repetition_penalty"]),
        0.1,
        3.0,
        settings["repetition_penalty"],
    )
    settings["voice_profiles"] = sanitize_voice_profiles(source.get("voice_profiles", settings["voice_profiles"]))
    active_voice_id = sanitize_slug(source.get("active_voice_id", settings["active_voice_id"]), settings["voice_profiles"][0]["id"])
    profile_ids = {profile["id"] for profile in settings["voice_profiles"]}
    settings["active_voice_id"] = active_voice_id if active_voice_id in profile_ids else settings["voice_profiles"][0]["id"]
    appearance_raw = source.get("appearance", settings.get("appearance", {}))
    settings["appearance"] = sanitize_appearance_settings(appearance_raw)
    return settings


def get_settings() -> dict[str, Any]:
    raw = read_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    settings = sanitize_settings(raw, existing=DEFAULT_SETTINGS)
    if raw != settings:
        write_json(SETTINGS_PATH, settings)
    return settings


def save_settings(raw: Any) -> dict[str, Any]:
    settings = sanitize_settings(raw, existing=get_settings())
    write_json(SETTINGS_PATH, settings)
    return settings


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return dict(settings)


def read_history() -> list[dict[str, Any]]:
    items = read_json(HISTORY_PATH, [])
    return items if isinstance(items, list) else []


def write_history(items: list[dict[str, Any]]) -> None:
    write_json(HISTORY_PATH, items[:80])


def add_history_item(item: dict[str, Any]) -> None:
    write_history([item, *read_history()])


def build_api_url(settings: dict[str, Any], path: str) -> str:
    base = str(settings.get("api_url", DEFAULT_API_URL) or DEFAULT_API_URL).rstrip("/")
    return f"{base}{path}"


def gpt_sovits_error_detail(response: httpx.Response | None, fallback: str) -> str:
    if response is None:
        return fallback
    try:
        data = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return text[:800] or fallback
    if isinstance(data, dict):
        parts = [
            str(data.get("message", "") or "").strip(),
            str(data.get("Exception", "") or "").strip(),
            str(data.get("detail", "") or "").strip(),
        ]
        detail = "：".join(part for part in parts if part)
        if detail:
            return detail[:800]
    return str(data)[:800] or fallback


def get_active_voice(settings: dict[str, Any], voice_id: str = "") -> dict[str, Any]:
    target = voice_id or settings.get("active_voice_id") or ""
    profiles = settings.get("voice_profiles") or []
    for profile in profiles:
        if profile.get("id") == target:
            return profile
    if profiles:
        return profiles[0]
    return dict(DEFAULT_VOICE_PROFILE)


def split_aux_paths(value: str) -> list[str]:
    paths: list[str] = []
    for line in str(value or "").replace(";", "\n").splitlines():
        clean = line.strip()
        if clean:
            paths.append(clean)
    return paths


def prepare_aux_ref_audio_paths(value: str) -> list[str]:
    prepared: list[str] = []
    for path in split_aux_paths(value):
        audio_path = Path(path)
        if not audio_path.is_file():
            raise HTTPException(status_code=400, detail=f"辅助参考音频文件不存在，请重新扫描或上传：{path}")
        prepared.append(prepare_runtime_audio_path(path))
    return prepared


async def probe_gpt_sovits(settings: dict[str, Any]) -> dict[str, Any]:
    base = str(settings.get("api_url", DEFAULT_API_URL) or DEFAULT_API_URL).rstrip("/")
    result: dict[str, Any] = {
        "ok": False,
        "api_url": base,
        "docs": False,
        "openapi": False,
        "error": "",
    }
    async with httpx.AsyncClient(timeout=1.5, trust_env=False) as client:
        try:
            docs = await client.get(f"{base}/docs")
            result["docs"] = docs.status_code < 500
        except httpx.HTTPError as exc:
            result["error"] = str(exc)
        try:
            openapi = await client.get(f"{base}/openapi.json")
            if openapi.status_code == 200:
                data = openapi.json()
                paths = data.get("paths", {}) if isinstance(data, dict) else {}
                result["openapi"] = True
                result["paths"] = sorted(paths.keys())
                result["ok"] = "/tts" in paths
        except (httpx.HTTPError, ValueError) as exc:
            result["error"] = result["error"] or str(exc)
    return result


async def apply_voice_weights(settings: dict[str, Any], voice: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=float(settings["request_timeout"]), trust_env=False) as client:
        gpt_path = str(voice.get("gpt_weights_path", "") or "").strip()
        if gpt_path:
            if not Path(gpt_path).is_file():
                raise HTTPException(status_code=400, detail=f"GPT 权重文件不存在，请重新扫描或上传：{gpt_path}")
            response = await client.get(build_api_url(settings, "/set_gpt_weights"), params={"weights_path": gpt_path})
            response.raise_for_status()
        sovits_path = str(voice.get("sovits_weights_path", "") or "").strip()
        if sovits_path:
            if not Path(sovits_path).is_file():
                raise HTTPException(status_code=400, detail=f"SoVITS 权重文件不存在，请重新扫描或上传：{sovits_path}")
            response = await client.get(build_api_url(settings, "/set_sovits_weights"), params={"weights_path": sovits_path})
            response.raise_for_status()


async def synthesize_gpt_sovits(text: str, settings: dict[str, Any], voice: dict[str, Any]) -> dict[str, Any]:
    original_ref_audio_path = str(voice.get("ref_audio_path", "") or "").strip()
    if not original_ref_audio_path:
        raise HTTPException(status_code=400, detail="当前声线缺少参考音频，请上传或选择参考音频。")
    if not Path(original_ref_audio_path).is_file():
        raise HTTPException(status_code=400, detail=f"参考音频文件不存在，请重新扫描或上传：{original_ref_audio_path}")
    prompt_text = str(voice.get("prompt_text", "") or "").strip() or infer_prompt_text_from_ref_audio(original_ref_audio_path)
    if not prompt_text:
        raise HTTPException(status_code=400, detail="当前声线缺少参考文本。请填写参考音频的原文，或把参考音频文件命名为原文后重新扫描。")
    ref_audio_path = prepare_runtime_audio_path(original_ref_audio_path)
    aux_ref_audio_paths = prepare_aux_ref_audio_paths(str(voice.get("aux_ref_audio_paths", "") or ""))

    await ensure_runtime_ready(settings)

    try:
        await apply_voice_weights(settings, voice)
    except httpx.HTTPStatusError as exc:
        detail = gpt_sovits_error_detail(exc.response, str(exc))
        raise HTTPException(status_code=502, detail=f"切换 GPT-SoVITS 权重失败：{detail}") from exc
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 GPT-SoVITS API：{exc}") from exc

    payload = {
        "text": text,
        "text_lang": voice.get("text_lang") or "zh",
        "ref_audio_path": ref_audio_path,
        "aux_ref_audio_paths": aux_ref_audio_paths,
        "prompt_text": prompt_text,
        "prompt_lang": voice.get("prompt_lang") or "zh",
        "top_k": settings["top_k"],
        "top_p": settings["top_p"],
        "temperature": settings["temperature"],
        "text_split_method": settings["text_split_method"],
        "batch_size": settings["batch_size"],
        "batch_threshold": settings["batch_threshold"],
        "split_bucket": True,
        "speed_factor": settings["speed_factor"],
        "streaming_mode": False,
        "seed": -1,
        "parallel_infer": settings["parallel_infer"],
        "repetition_penalty": settings["repetition_penalty"],
        "sample_steps": settings["sample_steps"],
        "media_type": settings["audio_format"],
    }
    async with httpx.AsyncClient(timeout=float(settings["request_timeout"]), trust_env=False) as client:
        try:
            response = await client.post(build_api_url(settings, "/tts"), json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = gpt_sovits_error_detail(exc.response, str(exc))
            raise HTTPException(status_code=502, detail=f"GPT-SoVITS 生成失败：{detail}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"GPT-SoVITS 生成失败：{exc}") from exc

    audio_bytes = response.content
    if not audio_bytes:
        raise HTTPException(status_code=502, detail="GPT-SoVITS 返回了空音频。")

    audio_hash = hashlib.sha256(audio_bytes).hexdigest()[:12]
    audio_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{audio_hash}-{uuid4().hex[:6]}"
    extension = settings["audio_format"]
    file_path = AUDIO_DIR / f"{audio_id}.{extension}"
    file_path.write_bytes(audio_bytes)

    item = {
        "id": audio_id,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "provider": "gpt_sovits",
        "voice": voice.get("name") or voice.get("id") or "voice",
        "voice_id": voice.get("id") or "",
        "format": extension,
        "text_preview": compact_text(text, 180),
        "size_bytes": len(audio_bytes),
        "url": f"/api/audio/{audio_id}",
    }
    add_history_item(item)
    return item


def runtime_python_path(settings: dict[str, Any]) -> Path:
    configured = str(settings.get("python_path", "") or "").strip()
    if configured:
        return Path(configured)
    venv_dir = runtime_venv_dir(settings)
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def runtime_api_path(settings: dict[str, Any]) -> Path:
    return resolve_runtime_root(settings) / "api_v2.py"


def runtime_venv_dir(settings: dict[str, Any]) -> Path:
    root = resolve_runtime_root(settings)
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    return runtime_cache_root() / digest / ".venv"


def patch_runtime_audio_loader(root: Path) -> None:
    tts_path = root / "GPT_SoVITS" / "TTS_infer_pack" / "TTS.py"
    if not tts_path.exists():
        return
    text = tts_path.read_text(encoding="utf-8")
    if "def load_ref_audio(ref_audio_path):" in text:
        return

    helper_anchor = "\n\nlanguage = os.environ.get(\"language\", \"Auto\")"
    helper = """

def load_ref_audio(ref_audio_path):
    try:
        return torchaudio.load(ref_audio_path)
    except Exception:
        # Windows torchcodec wheels are not always available; librosa keeps API inference usable.
        audio, sr = librosa.load(ref_audio_path, sr=None, mono=False)
        if audio.ndim == 1:
            audio = np.expand_dims(audio, axis=0)
        return torch.from_numpy(np.asarray(audio)), sr
"""
    if helper_anchor not in text:
        return
    text = text.replace(helper_anchor, helper + helper_anchor, 1)
    text = text.replace(
        "        raw_audio, raw_sr = torchaudio.load(ref_audio_path)",
        "        raw_audio, raw_sr = load_ref_audio(ref_audio_path)",
        1,
    )
    tts_path.write_text(text, encoding="utf-8")


def read_log_tail(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - (max_chars * 4)))
            raw = handle.read()
    except OSError:
        return ""
    text = raw.decode("utf-8", errors="ignore").replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text[-max_chars:].strip()


def python_command_display(command: list[str]) -> str:
    return " ".join(command)


def add_python_candidate(candidates: list[list[str]], seen: set[str], command: list[str]) -> None:
    if not command or not command[0]:
        return
    key = python_command_display(command).lower()
    if os.name == "nt" and len(command) == 1:
        try:
            key = str(Path(command[0]).resolve()).lower()
        except OSError:
            pass
    if key in seen:
        return
    seen.add(key)
    candidates.append(command)


def parse_py_launcher_candidates() -> list[list[str]]:
    if os.name != "nt":
        return []
    try:
        result = subprocess.run(
            ["py", "-0p"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    candidates: list[list[str]] = []
    seen: set[str] = set()
    for line in (result.stdout or "").splitlines():
        version_match = re.search(r"(?:-V:|-)?3\.(10|11|12)\b", line)
        path_match = re.search(r"([A-Za-z]:\\[^\r\n]*?python(?:w)?\.exe)", line, re.IGNORECASE)
        if not path_match:
            continue
        python_path = path_match.group(1).strip()
        if not version_match and not re.search(r"Python3(?:10|11|12)", python_path, re.IGNORECASE):
            continue
        add_python_candidate(candidates, seen, [python_path])
    return candidates


def where_python_candidates(name: str) -> list[list[str]]:
    paths: list[str] = []
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["where.exe", name],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                paths.extend(line.strip() for line in (result.stdout or "").splitlines())
        except (OSError, subprocess.SubprocessError):
            pass
    resolved = shutil.which(name)
    if resolved:
        paths.append(resolved)

    candidates: list[list[str]] = []
    seen: set[str] = set()
    for item in paths:
        if item and Path(item).exists():
            add_python_candidate(candidates, seen, [item])
    return candidates


def registry_python_candidates() -> list[list[str]]:
    if os.name != "nt":
        return []
    roots = (
        r"HKCU\Software\Python\PythonCore",
        r"HKLM\Software\Python\PythonCore",
        r"HKLM\Software\WOW6432Node\Python\PythonCore",
    )
    candidates: list[list[str]] = []
    seen: set[str] = set()
    for root in roots:
        try:
            result = subprocess.run(
                ["reg.exe", "query", root, "/s", "/v", "ExecutablePath"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        for line in (result.stdout or "").splitlines():
            if "ExecutablePath" not in line or "REG_" not in line:
                continue
            parts = re.split(r"\s+REG_\w+\s+", line.strip(), maxsplit=1)
            if len(parts) != 2:
                continue
            python_path = parts[1].strip().strip('"')
            if python_path and Path(python_path).exists():
                add_python_candidate(candidates, seen, [python_path])
    return candidates


def common_python_paths() -> list[list[str]]:
    candidates: list[list[str]] = []
    seen: set[str] = set()
    roots: list[Path] = []
    for env_name in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))

    if os.name == "nt":
        for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "USERPROFILE"):
            value = os.environ.get(env_name)
            if not value:
                continue
            base = Path(value)
            if env_name == "LOCALAPPDATA":
                roots.append(base / "Programs" / "Python")
            elif env_name == "USERPROFILE":
                roots.append(base / "AppData" / "Local" / "Programs" / "Python")
            else:
                roots.append(base)
        roots.append(Path(f"{os.environ.get('SystemDrive', 'C:')}\\"))

        names = ("Python312", "Python311", "Python310", "Python312-32", "Python311-32", "Python310-32")
        for root in roots:
            for name in names:
                for path in (root / name / "python.exe", root / name / "Scripts" / "python.exe"):
                    if path.exists():
                        add_python_candidate(candidates, seen, [str(path)])
        return candidates

    for path in (
        Path("/usr/local/bin/python3.12"),
        Path("/usr/local/bin/python3.11"),
        Path("/usr/local/bin/python3.10"),
        Path("/usr/bin/python3.12"),
        Path("/usr/bin/python3.11"),
        Path("/usr/bin/python3.10"),
    ):
        if path.exists():
            add_python_candidate(candidates, seen, [str(path)])
    return candidates


def build_python_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    seen: set[str] = set()

    if os.name == "nt":
        for command in (["py", "-3.10"], ["py", "-3.11"], ["py", "-3.12"]):
            add_python_candidate(candidates, seen, command)
    for command in (["python3.10"], ["python3.11"], ["python3.12"]):
        add_python_candidate(candidates, seen, command)

    add_python_candidate(candidates, seen, [sys.executable])

    for command in parse_py_launcher_candidates():
        add_python_candidate(candidates, seen, command)
    for command_name in ("python", "python3", "python3.10", "python3.11", "python3.12"):
        for command in where_python_candidates(command_name):
            add_python_candidate(candidates, seen, command)
    for command in registry_python_candidates():
        add_python_candidate(candidates, seen, command)
    for command in common_python_paths():
        add_python_candidate(candidates, seen, command)

    for command in (["python3"], ["python"]):
        add_python_candidate(candidates, seen, command)
    return candidates


def run_python_probe(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [*command, "-c", "import json, sys; print(json.dumps({'version': list(sys.version_info[:3]), 'executable': sys.executable}))"],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc), "command": python_command_display(command)}

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
        return {"ok": False, "error": error, "command": python_command_display(command)}

    try:
        data = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (IndexError, ValueError, TypeError) as exc:
        return {"ok": False, "error": f"无法解析 Python 信息：{exc}", "command": python_command_display(command)}

    version = data.get("version") or [0, 0, 0]
    major = int(version[0]) if len(version) > 0 else 0
    minor = int(version[1]) if len(version) > 1 else 0
    return {
        "ok": major == 3 and 10 <= minor <= 12,
        "version": version,
        "executable": str(data.get("executable", "") or ""),
        "command": python_command_display(command),
        "error": "" if (major == 3 and 10 <= minor <= 12) else "需要 Python 3.10-3.12",
    }


def detect_bootstrap_python() -> dict[str, Any]:
    candidates = build_python_candidates()
    attempts: list[dict[str, Any]] = []
    for command in candidates:
        probe = run_python_probe(command)
        attempts.append(probe)
        if probe.get("ok"):
            probe["command_list"] = command
            return probe

    found_versions: list[str] = []
    for item in attempts:
        version = item.get("version")
        executable = item.get("executable") or item.get("command") or ""
        if isinstance(version, list) and len(version) >= 2:
            found_versions.append(f"{version[0]}.{version[1]} ({executable})")
    if found_versions:
        detail = "；已检测到：" + "；".join(found_versions[:4])
    else:
        detail = "；已尝试：" + "；".join((item.get("command") or "") for item in attempts[:6])
    return {
        "ok": False,
        "attempts": attempts,
        "error": f"未找到可用的 Python 3.10-3.12{detail}。请安装 Python 3.10/3.11/3.12，或确认 py -3.10 / python3.10 可以启动。",
    }


def runtime_python_health(settings: dict[str, Any]) -> dict[str, Any]:
    python_path = runtime_python_path(settings)
    info: dict[str, Any] = {
        "path": str(python_path),
        "exists": python_path.exists(),
        "ok": False,
        "version": "",
        "error": "",
    }
    if not python_path.exists():
        info["error"] = "缺少 runtime Python。"
        return info
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.version)"],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        info["error"] = str(exc)
        return info
    if result.returncode != 0:
        info["error"] = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
        return info
    info["ok"] = True
    info["version"] = (result.stdout or "").strip()
    return info


def resolve_runtime_device(settings: dict[str, Any]) -> str:
    configured = sanitize_runtime_device(settings.get("runtime_device", "auto"))
    if configured != "auto":
        return configured
    return "cu126" if shutil.which("nvidia-smi") else "cpu"


def runtime_environment_status(settings: dict[str, Any]) -> dict[str, Any]:
    runtime_root = resolve_runtime_root(settings)
    api_path = runtime_api_path(settings)
    python_info = runtime_python_health(settings)
    bootstrap = detect_bootstrap_python()
    return {
        "runtime_root": str(runtime_root),
        "api_path": str(api_path),
        "api_exists": api_path.exists(),
        "venv_dir": str(runtime_venv_dir(settings)),
        "python": python_info,
        "bootstrap_python": bootstrap,
        "install_device": resolve_runtime_device(settings),
        "ready": bool(api_path.exists() and python_info.get("ok")),
    }


def read_setup_state() -> dict[str, Any]:
    state = read_json(SETUP_STATE_PATH, {})
    return state if isinstance(state, dict) else {}


def write_setup_state(state: dict[str, Any]) -> None:
    write_json(SETUP_STATE_PATH, state)


def process_exists(pid: Any) -> bool:
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return False
    if number <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {number}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return str(number) in (result.stdout or "")
    try:
        os.kill(number, 0)
    except OSError:
        return False
    return True


def runtime_setup_status() -> dict[str, Any]:
    global _setup_process
    status: dict[str, Any] = {
        "running": False,
        "pid": None,
        "returncode": None,
        "log_path": str(SETUP_LOG_PATH),
        "log_tail": read_log_tail(SETUP_LOG_PATH),
    }
    state = read_setup_state()
    if _setup_process is None:
        pid = state.get("pid")
        if pid and not state.get("finished_at") and process_exists(pid):
            status["running"] = True
            status["pid"] = pid
            status["state"] = state
            return status
        if state:
            if pid and not state.get("finished_at") and state.get("returncode") is None:
                state.update(
                    {
                        "returncode": -1,
                        "status": "interrupted",
                        "error": "安装进程已结束，但没有写入完成状态。请重新点击安装 / 修复环境。",
                        "finished_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    }
                )
                write_setup_state(state)
            status["pid"] = pid
            status["returncode"] = state.get("returncode")
            status["state"] = state
        return status
    if _setup_process.poll() is None:
        status["running"] = True
        status["pid"] = _setup_process.pid
        status["state"] = state
        return status
    status["pid"] = _setup_process.pid
    status["returncode"] = _setup_process.returncode
    state.update(
        {
            "pid": _setup_process.pid,
            "returncode": _setup_process.returncode,
            "finished_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        }
    )
    write_setup_state(state)
    _setup_process = None
    status["log_tail"] = read_log_tail(SETUP_LOG_PATH)
    status["state"] = state
    return status


def runtime_process_status() -> dict[str, Any]:
    global _runtime_process, _runtime_process_endpoint
    status: dict[str, Any] = {
        "running": False,
        "pid": None,
        "endpoint": list(_runtime_process_endpoint) if _runtime_process_endpoint else None,
        "log_path": str(RUNTIME_LOG_PATH),
        "log_tail": read_log_tail(RUNTIME_LOG_PATH),
    }
    if _runtime_process is None:
        return status
    if _runtime_process.poll() is None:
        status["running"] = True
        status["pid"] = _runtime_process.pid
        return status
    status["pid"] = _runtime_process.pid
    status["returncode"] = _runtime_process.returncode
    _runtime_process = None
    _runtime_process_endpoint = None
    return status


def stop_tracked_runtime_process() -> None:
    global _runtime_process, _runtime_process_endpoint
    if _runtime_process is not None and _runtime_process.poll() is None:
        _runtime_process.terminate()
        try:
            _runtime_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _runtime_process.kill()
            _runtime_process.wait(timeout=8)
    _runtime_process = None
    _runtime_process_endpoint = None


def runtime_creationflags() -> int:
    if os.name != "nt":
        return 0
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    return flags


def launch_runtime_setup(settings: dict[str, Any], *, force_recreate: bool = False) -> dict[str, Any]:
    global _setup_process
    status = runtime_setup_status()
    if status.get("running"):
        return status

    bootstrap = detect_bootstrap_python()
    if not bootstrap.get("ok"):
        raise HTTPException(status_code=400, detail=bootstrap.get("error") or "未找到可用的 Python 3.10+。")
    if not BOOTSTRAP_SCRIPT_PATH.exists():
        raise HTTPException(status_code=500, detail=f"缺少安装脚本：{BOOTSTRAP_SCRIPT_PATH}")

    runtime_root = resolve_runtime_root(settings)
    venv_dir = runtime_venv_dir(settings)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_LOG_PATH.write_text("", encoding="utf-8")
    command = [
        bootstrap["executable"],
        str(BOOTSTRAP_SCRIPT_PATH),
        "--runtime-root",
        str(runtime_root),
        "--venv-dir",
        str(venv_dir),
        "--state-path",
        str(SETUP_STATE_PATH),
        "--device",
        resolve_runtime_device(settings),
    ]
    if force_recreate:
        command.append("--force")
    with SETUP_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.utcnow().isoformat()}Z] Launch: {' '.join(command)}\n")
        handle.flush()
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        _setup_process = subprocess.Popen(
            command,
            cwd=str(APP_DIR),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=runtime_creationflags(),
        )
    write_setup_state(
        {
            "pid": _setup_process.pid,
            "started_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "command": command,
            "runtime_root": str(runtime_root),
            "venv_dir": str(venv_dir),
            "device": resolve_runtime_device(settings),
            "returncode": None,
        }
    )
    return runtime_setup_status()


def launch_runtime_process(settings: dict[str, Any]) -> dict[str, Any]:
    global _runtime_process, _runtime_process_endpoint
    endpoint = (str(settings["launch_host"]), int(settings["launch_port"]))
    process_status = runtime_process_status()
    if process_status.get("running"):
        if _runtime_process_endpoint == endpoint:
            return process_status
        stop_tracked_runtime_process()

    env_status = runtime_environment_status(settings)
    if not env_status.get("ready"):
        detail = env_status["python"].get("error") or "运行环境未安装。"
        raise HTTPException(status_code=400, detail=f"GPT-SoVITS 运行环境未就绪：{detail}")

    python_path = runtime_python_path(settings)
    api_path = runtime_api_path(settings)
    if not api_path.exists():
        raise HTTPException(status_code=400, detail=f"找不到 GPT-SoVITS api_v2.py：{api_path}")
    patch_runtime_audio_loader(api_path.parent)

    command = [
        str(python_path),
        str(api_path),
        "-a",
        str(settings["launch_host"]),
        "-p",
        str(settings["launch_port"]),
    ]
    if settings.get("tts_config_path"):
        command.extend(["-c", str(settings["tts_config_path"])])
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_LOG_PATH.write_text("", encoding="utf-8")
    log_handle = RUNTIME_LOG_PATH.open("a", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    _runtime_process = subprocess.Popen(
        command,
        cwd=str(api_path.parent),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=runtime_creationflags(),
    )
    _runtime_process_endpoint = endpoint
    return runtime_process_status()


async def ensure_runtime_ready(settings: dict[str, Any], *, attempts: int = 60, delay_seconds: float = 2.0) -> dict[str, Any]:
    probe = await probe_gpt_sovits(settings)
    if probe.get("ok"):
        return probe

    env_status = runtime_environment_status(settings)
    if not env_status.get("ready"):
        detail = env_status["python"].get("error") or "请先安装 / 修复 GPT-SoVITS 运行环境。"
        raise HTTPException(status_code=400, detail=f"GPT-SoVITS 运行环境未就绪：{detail}")

    launch_runtime_process(settings)
    last_probe = probe
    for _ in range(attempts):
        await asyncio.sleep(delay_seconds)
        last_probe = await probe_gpt_sovits(settings)
        if last_probe.get("ok"):
            return last_probe
    detail = last_probe.get("error") or "未发现 /tts"
    raise HTTPException(status_code=502, detail=f"GPT-SoVITS API 未就绪：{detail}")


def scan_files(root: Path, suffixes: set[str], limit: int = 300) -> list[str]:
    if not root.exists() or not root.is_dir():
        return []
    found: list[str] = []
    skip_names = {".git", ".venv", "__pycache__", "runtime"}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [item for item in dirs if item not in skip_names]
        for filename in files:
            path = Path(current_root) / filename
            if path.suffix.lower() in suffixes:
                found.append(str(path))
                if len(found) >= limit:
                    return found
    return found


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        items.append(key)
    return items


def discover_local_assets(settings: dict[str, Any]) -> dict[str, Any]:
    runtime_root = resolve_runtime_root(settings)
    scan_roots = [VOICE_GPT_DIR, VOICE_SOVITS_DIR, VOICE_AUDIO_DIR]
    weights = scan_files(VOICE_GPT_DIR, {".ckpt"}) + scan_files(VOICE_SOVITS_DIR, {".pth", ".pt"})
    audio = scan_files(VOICE_AUDIO_DIR, AUDIO_SUFFIXES)
    scanned: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        scanned.append(str(root))
    return {
        "runtime_root": str(runtime_root),
        "scan_roots": dedupe_paths(scanned),
        "weights": dedupe_paths(weights),
        "audio": dedupe_paths(audio),
        "drop_folders": {
            "gpt": str(VOICE_GPT_DIR),
            "sovits": str(VOICE_SOVITS_DIR),
            "audio": str(VOICE_AUDIO_DIR),
        },
    }


async def save_upload_file(file: UploadFile, *, kind: str) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if kind == "gpt":
        allowed = {".ckpt"}
        target_dir = VOICE_GPT_DIR
        max_size = MAX_MODEL_UPLOAD_SIZE_BYTES
    elif kind == "sovits":
        allowed = {".pth", ".pt"}
        target_dir = VOICE_SOVITS_DIR
        max_size = MAX_MODEL_UPLOAD_SIZE_BYTES
    elif kind == "audio":
        allowed = AUDIO_SUFFIXES
        target_dir = VOICE_AUDIO_DIR
        max_size = MAX_AUDIO_UPLOAD_SIZE_BYTES
    else:
        raise HTTPException(status_code=400, detail="Unknown upload kind.")

    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix or 'none'}")

    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(file.filename or f"{kind}{suffix}", kind)
    target_path = target_dir / safe_name
    if target_path.exists():
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        target_path = target_dir / f"{Path(safe_name).stem}-{stamp}{suffix}"

    total = 0
    with target_path.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size:
                handle.close()
                target_path.unlink(missing_ok=True)
                limit_mb = max_size // (1024 * 1024)
                raise HTTPException(status_code=413, detail=f"文件太大，限制 {limit_mb} MB。")
            handle.write(chunk)

    return {
        "kind": kind,
        "path": str(target_path),
        "filename": target_path.name,
        "size_bytes": total,
    }


app = FastAPI(title="TTS Studio")
ensure_data_files()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    root_path = (request.scope.get("root_path") or "").rstrip("/")
    stylesheet_url = f"{root_path}/static/styles.css" if root_path else "/static/styles.css"
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": public_settings(settings),
            "api_base_path": root_path,
            "static_stylesheet_url": stylesheet_url,
        },
    )


@app.get("/api/settings")
async def api_get_settings() -> dict[str, Any]:
    return {"ok": True, "settings": public_settings(get_settings())}


@app.post("/api/settings")
async def api_save_settings(payload: SettingsPayload) -> dict[str, Any]:
    settings = save_settings(payload.model_dump())
    return {"ok": True, "settings": public_settings(settings)}


@app.get("/api/runtime/status")
async def api_runtime_status() -> dict[str, Any]:
    settings = get_settings()
    probe = await probe_gpt_sovits(settings)
    return {
        "ok": True,
        "process": runtime_process_status(),
        "probe": probe,
        "environment": runtime_environment_status(settings),
        "setup": runtime_setup_status(),
    }


@app.get("/api/runtime/setup-status")
async def api_runtime_setup_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ok": True,
        "setup": runtime_setup_status(),
        "environment": runtime_environment_status(settings),
    }


@app.post("/api/runtime/setup")
async def api_runtime_setup() -> dict[str, Any]:
    settings = get_settings()
    setup = launch_runtime_setup(settings, force_recreate=True)
    return {
        "ok": True,
        "setup": setup,
        "environment": runtime_environment_status(settings),
    }


@app.post("/api/runtime/launch")
async def api_runtime_launch() -> dict[str, Any]:
    settings = get_settings()
    process = launch_runtime_process(settings)
    probe = await ensure_runtime_ready(settings, attempts=90)
    return {
        "ok": True,
        "process": process,
        "probe": probe,
        "environment": runtime_environment_status(settings),
        "setup": runtime_setup_status(),
    }


@app.post("/api/runtime/stop")
async def api_runtime_stop() -> dict[str, Any]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=4.0, trust_env=False) as client:
            await client.get(build_api_url(settings, "/control"), params={"command": "exit"})
    except httpx.HTTPError:
        pass
    stop_tracked_runtime_process()
    status = runtime_process_status()
    return {
        "ok": True,
        "process": status,
        "probe": await probe_gpt_sovits(settings),
        "environment": runtime_environment_status(settings),
        "setup": runtime_setup_status(),
    }


@app.get("/api/discover")
async def api_discover() -> dict[str, Any]:
    settings = get_settings()
    return {"ok": True, **discover_local_assets(settings)}


@app.post("/api/upload/{kind}")
async def api_upload(kind: str, file: UploadFile = File(...)) -> dict[str, Any]:
    saved = await save_upload_file(file, kind=kind)
    return {"ok": True, "item": saved}


@app.post("/api/synthesize")
async def api_synthesize(payload: SynthesizePayload) -> dict[str, Any]:
    settings = get_settings()
    raw_text = str(payload.text or "").strip()
    text = resolve_synthesize_text(raw_text)
    if not text:
        if has_ttsvoice_marker(raw_text):
            raise HTTPException(
                status_code=400,
                detail="未检测到有效的 TTSVoice 语音内容。请检查格式：[TTSVoice:说话人:情绪:语音内容]",
            )
        raise HTTPException(status_code=400, detail="Text is required.")
    max_chars = int(settings["max_text_chars"])
    if len(text) > max_chars:
        raise HTTPException(status_code=400, detail=f"Text is too long. Limit: {max_chars} characters.")

    voice = get_active_voice(settings, payload.voice_id)
    item = await synthesize_gpt_sovits(text, settings, voice)
    return {"ok": True, "item": item, "history": read_history(), "settings": public_settings(settings)}


@app.get("/api/history")
async def api_history() -> dict[str, Any]:
    return {"ok": True, "items": read_history()}


@app.get("/api/audio/{audio_id}")
async def api_audio(audio_id: str) -> FileResponse:
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", audio_id)
    for path in AUDIO_DIR.glob(f"{clean_id}.*"):
        if path.is_file():
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="Audio not found.")


@app.delete("/api/history/{audio_id}")
async def api_delete_audio(audio_id: str) -> dict[str, Any]:
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", audio_id)
    history = [item for item in read_history() if str(item.get("id", "")) != clean_id]
    for path in AUDIO_DIR.glob(f"{clean_id}.*"):
        if path.is_file():
            path.unlink()
    write_history(history)
    return {"ok": True, "items": history}
