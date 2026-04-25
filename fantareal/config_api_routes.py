import json
import re
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .memory_merge_logic import (
    get_memory_outline,
    get_merged_memories,
    merge_memories_to_outline,
    save_memory_outline,
    save_merged_memories,
)

from .app_models import (
    DynamicWorldbookPreviewPayload,
    JsonImportPayload,
    MemoryListPayload,
    MemoryMergePayload,
    MemoryOutlineListPayload,
    MergedMemoryListPayload,
    PersonaPayload,
    PresetActionPayload,
    PresetCreatePayload,
    PresetImportPayload,
    PresetStorePayload,
    RoleCardLoadPayload,
    RoleCardPayload,
    SettingsPayload,
    SpriteDeletePayload,
    UserProfilePayload,
    WorkshopEvaluatePayload,
    WorkshopSavePayload,
    WorldbookPayload,
    WorldbookSettingsPayload,
)


def strip_json_comments(raw_text: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    while index < len(raw_text):
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < len(raw_text) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            index += 1
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def parse_json_import_payload(raw_json: str, *, label: str) -> Any:
    raw_text = str(raw_json or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail=f"{label} import content cannot be empty.")
    try:
        return json.loads(raw_text)
    except ValueError as exc:
        try:
            return json.loads(strip_json_comments(raw_text))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{label} JSON parse failed: {exc}") from exc


def _worldbook_field_present(row: dict[str, Any], key: str) -> bool:
    if key not in row:
        return False
    value = row.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _apply_worldbook_import_options(
    entries: list[Any],
    *,
    missing_injection_policy: str,
    force_in_chat_depth: int,
    force_injection_order: int | None,
) -> list[Any]:
    policy = str(missing_injection_policy or "follow_defaults").strip().lower()
    if policy not in {"follow_defaults", "force_before_char_defs", "force_after_char_defs", "force_in_chat"}:
        policy = "follow_defaults"

    normalized_depth = max(0, min(int(force_in_chat_depth or 0), 3))
    processed: list[Any] = []
    for item in entries:
        if not isinstance(item, dict):
            processed.append(item)
            continue

        row = dict(item)
        if policy != "follow_defaults":
            if not _worldbook_field_present(row, "insertion_position"):
                if policy == "force_before_char_defs":
                    row["insertion_position"] = "before_char_defs"
                elif policy == "force_after_char_defs":
                    row["insertion_position"] = "after_char_defs"
                elif policy == "force_in_chat":
                    row["insertion_position"] = "in_chat"

            effective_position = str(row.get("insertion_position", "") or "").strip().lower()
            if effective_position == "in_chat" and not _worldbook_field_present(row, "injection_depth"):
                row["injection_depth"] = normalized_depth

            if not _worldbook_field_present(row, "injection_role"):
                row["injection_role"] = "system"

            if force_injection_order is not None and not _worldbook_field_present(row, "injection_order"):
                row["injection_order"] = force_injection_order

        processed.append(row)
    return processed


def register_config_api_routes(app: FastAPI, *, ctx: Any) -> None:
    def build_bundle_label() -> tuple[str, dict[str, Any], dict[str, Any]]:
        current_card = ctx.get_current_card()
        card = ctx.normalize_role_card(current_card.get("raw", {}))
        has_card_content = bool(str(current_card.get("source_name", "")).strip()) or any(
            str(value).strip() for value in card.values() if not isinstance(value, (dict, list))
        )
        if not has_card_content:
            raise HTTPException(status_code=404, detail="当前人设卡尚未加载，无法导出存档包。")

        display_name = (
            str(card.get("name", "")).strip()
            or str(ctx.get_persona().get("name", "")).strip()
            or Path(str(current_card.get("source_name", "")).strip() or "当前角色").stem
            or "当前角色"
        )
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", display_name).strip(" ._") or "当前角色"
        return safe_name[:64], current_card, card

    @app.get("/api/user-profile")
    async def api_get_user_profile() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {"active_slot": active_slot, "profile": ctx.get_user_profile(active_slot)}

    @app.post("/api/user-profile")
    async def api_save_user_profile(payload: UserProfilePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        profile = ctx.save_user_profile(payload.model_dump(), active_slot)
        return {"ok": True, "active_slot": active_slot, "profile": profile}

    @app.post("/api/user-avatar")
    async def api_upload_user_avatar(file: UploadFile = File(...)) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        url = ctx.save_image_upload_for_slot(
            file=file,
            prefix="user_avatar",
            empty_detail="User avatar upload cannot be empty.",
            too_large_detail="User avatar cannot be larger than 10 MB.",
            invalid_type_detail="User avatar only supports png / jpg / jpeg / webp / gif.",
            save_failed_detail="User avatar save failed. Please check disk space or file permissions.",
        )
        profile = ctx.save_user_profile({"avatar_url": url}, active_slot)
        return {"ok": True, "active_slot": active_slot, "profile": profile}

    @app.post("/api/role-avatar")
    async def api_upload_role_avatar(file: UploadFile = File(...)) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        url = ctx.save_image_upload_for_slot(
            file=file,
            prefix="role_avatar",
            empty_detail="Role avatar upload cannot be empty.",
            too_large_detail="Role avatar cannot be larger than 10 MB.",
            invalid_type_detail="Role avatar only supports png / jpg / jpeg / webp / gif.",
            save_failed_detail="Role avatar save failed. Please check disk space or file permissions.",
        )
        return {
            "ok": True,
            "active_slot": active_slot,
            "role_avatar_url": url,
            "profile": ctx.get_user_profile(active_slot),
        }

    @app.get("/api/preset")
    async def api_get_preset() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.get_preset_store(active_slot)
        return {
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.post("/api/preset")
    async def api_save_preset(payload: PresetStorePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.save_preset_store(payload.model_dump(), active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.post("/api/preset/create")
    async def api_create_preset(payload: PresetCreatePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.create_preset_in_store(ctx.get_preset_store(active_slot), payload.name)
        created_preset = store.get("presets", [])[-1] if store.get("presets") else {}
        store = ctx.save_preset_store(store, active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "created_preset_id": str(created_preset.get("id", "")).strip(),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.post("/api/preset/activate")
    async def api_activate_preset(payload: PresetActionPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.activate_preset_in_store(ctx.get_preset_store(active_slot), payload.preset_id)
        store = ctx.save_preset_store(store, active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.post("/api/preset/duplicate")
    async def api_duplicate_preset(payload: PresetActionPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.duplicate_preset_in_store(ctx.get_preset_store(active_slot), payload.preset_id)
        duplicated_preset = store.get("presets", [])[-1] if store.get("presets") else {}
        store = ctx.save_preset_store(store, active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "duplicated_preset_id": str(duplicated_preset.get("id", "")).strip(),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.post("/api/preset/delete")
    async def api_delete_preset(payload: PresetActionPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.delete_preset_from_store(ctx.get_preset_store(active_slot), payload.preset_id)
        store = ctx.save_preset_store(store, active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.get("/api/preset/export/current")
    async def api_export_current_preset() -> FileResponse:
        active_slot = ctx.get_active_slot_id()
        preset = ctx.get_active_preset(active_slot)
        if not isinstance(preset, dict):
            raise HTTPException(status_code=404, detail="No current preset exists.")
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", str(preset.get("name", "preset")).strip() or "preset")
        filename = f"{safe_name}.preset.json"
        target = ctx.EXPORT_DIR / filename
        ctx.persist_json(target, preset, detail="Preset export failed. Please check disk space or file permissions.")
        return FileResponse(target, media_type="application/json", filename=filename)

    @app.post("/api/preset/import")
    async def api_import_preset(payload: PresetImportPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        parsed = parse_json_import_payload(payload.raw_json, label="Preset")
        current_store = ctx.get_preset_store(active_slot)
        imported_store = ctx.sanitize_preset_store(parsed)
        if isinstance(parsed, dict) and "presets" in parsed:
            imported_presets = imported_store.get("presets", [])
        else:
            imported_presets = [ctx.get_active_preset_from_store(imported_store)]

        existing_ids = {item.get("id") for item in current_store.get("presets", []) if isinstance(item, dict)}
        added_ids: list[str] = []
        for item in imported_presets:
            if not isinstance(item, dict):
                continue
            cloned = json.loads(json.dumps(item, ensure_ascii=False))
            preset_id = str(cloned.get("id", "")).strip()
            if not preset_id or preset_id in existing_ids:
                from .preset_rules import generate_preset_id

                cloned["id"] = generate_preset_id()
            existing_ids.add(cloned["id"])
            current_store.setdefault("presets", []).append(cloned)
            added_ids.append(cloned["id"])
        if not added_ids:
            raise HTTPException(status_code=400, detail="No preset content could be imported.")
        if payload.activate_now:
            current_store["active_preset_id"] = added_ids[-1]
        store = ctx.save_preset_store(current_store, active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "preset_store": store,
            "active_preset": ctx.get_active_preset_from_store(store),
            "preset_debug": ctx.build_preset_debug_payload(active_slot),
        }

    @app.get("/api/persona")
    async def api_get_persona() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return ctx.get_persona(active_slot)

    @app.post("/api/persona")
    async def api_save_persona(payload: PersonaPayload) -> dict[str, Any]:
        ctx.persist_json(
            ctx.global_persona_path(),
            {
                "name": payload.name.strip(),
                "system_prompt": payload.system_prompt.strip(),
                "greeting": payload.greeting.strip(),
            },
            detail="Persona settings save failed. Please check disk space or file permissions.",
        )
        return {"ok": True}

    @app.get("/api/settings")
    async def api_get_settings() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {
            "active_slot": active_slot,
            "slot_name": ctx.get_slot_name(active_slot),
            "settings": ctx.get_settings(active_slot),
        }

    @app.post("/api/settings")
    async def api_save_settings(payload: SettingsPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        settings = ctx.sanitize_settings(payload.model_dump(), strict=True, slot_id=active_slot)
        ctx.persist_json(
            ctx.settings_path(active_slot),
            settings,
            detail="Settings save failed. Please check disk space or file permissions.",
        )
        return {"ok": True, "settings": settings, "active_slot": active_slot}

    @app.get("/api/memories")
    async def api_get_memories() -> list[dict[str, Any]]:
        active_slot = ctx.get_active_slot_id()
        return ctx.get_memories(active_slot)

    @app.get("/api/memories/export")
    async def api_export_memories() -> FileResponse:
        active_slot = ctx.get_active_slot_id()
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = "memories.json"
        target = ctx.EXPORT_DIR / filename
        ctx.persist_json(
            target,
            {"items": ctx.get_memories(active_slot)},
            detail="Memory export failed. Please check disk space or file permissions.",
        )
        return FileResponse(path=target, filename=filename, media_type="application/json")

    @app.post("/api/memories/import")
    async def api_import_memories(payload: JsonImportPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        parsed = parse_json_import_payload(payload.raw_json, label="Memory")
        raw_items = parsed
        if isinstance(parsed, dict):
            if isinstance(parsed.get("memories"), list):
                raw_items = parsed["memories"]
            elif isinstance(parsed.get("items"), list):
                raw_items = parsed["items"]
        if not isinstance(raw_items, list):
            raise HTTPException(status_code=400, detail="Memory import JSON must contain an items array.")
        memories = ctx.save_memories(raw_items, active_slot)
        return {"ok": True, "items": memories}

    @app.post("/api/memories")
    async def api_save_memories(payload: MemoryListPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        memories = ctx.save_memories([item.model_dump() for item in payload.items], active_slot)
        return {"ok": True, "items": memories}


    @app.get("/api/memories/merged")
    async def api_get_merged_memories() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {"ok": True, "items": get_merged_memories(ctx, active_slot), "active_slot": active_slot}

    @app.post("/api/memories/merged")
    async def api_save_merged_memories(payload: MergedMemoryListPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        items = save_merged_memories(ctx, [item.model_dump() for item in payload.items], active_slot)
        return {"ok": True, "items": items, "active_slot": active_slot}

    @app.get("/api/memories/merged/export")
    async def api_export_merged_memories() -> FileResponse:
        active_slot = ctx.get_active_slot_id()
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = "merged_memories.json"
        target = ctx.EXPORT_DIR / filename
        ctx.persist_json(
            target,
            {"items": get_merged_memories(ctx, active_slot)},
            detail="Merged memory export failed. Please check disk space or file permissions.",
        )
        return FileResponse(path=target, filename=filename, media_type="application/json")

    @app.get("/api/memories/outline")
    async def api_get_memory_outline() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {"ok": True, "items": get_memory_outline(ctx, active_slot), "active_slot": active_slot}

    @app.post("/api/memories/outline")
    async def api_save_memory_outline(payload: MemoryOutlineListPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        items = save_memory_outline(ctx, [item.model_dump() for item in payload.items], active_slot)
        return {"ok": True, "items": items, "active_slot": active_slot}

    @app.get("/api/memories/outline/export")
    async def api_export_memory_outline() -> FileResponse:
        active_slot = ctx.get_active_slot_id()
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = "memory_outline.json"
        target = ctx.EXPORT_DIR / filename
        ctx.persist_json(
            target,
            {"items": get_memory_outline(ctx, active_slot)},
            detail="Memory outline export failed. Please check disk space or file permissions.",
        )
        return FileResponse(path=target, filename=filename, media_type="application/json")


    @app.get("/api/memories/export-bundle")
    async def api_export_memory_bundle() -> FileResponse:
        active_slot = ctx.get_active_slot_id()
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"memory_bundle_{timestamp}.zip"
        target = ctx.EXPORT_DIR / filename

        memories_payload = {"items": ctx.get_memories(active_slot)}
        merged_payload = {"items": get_merged_memories(ctx, active_slot)}
        outline_payload = {"items": get_memory_outline(ctx, active_slot)}
        manifest_lines = [
            "记忆完整导出包",
            "",
            "1. memories.json：原记忆区条目",
            "2. merged_memories.json：合并后的记忆",
            "3. memory_outline.json：大纲表",
            "",
            f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"活动存档：{active_slot}",
        ]

        try:
            with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("memories.json", json.dumps(memories_payload, ensure_ascii=False, indent=2))
                archive.writestr("merged_memories.json", json.dumps(merged_payload, ensure_ascii=False, indent=2))
                archive.writestr("memory_outline.json", json.dumps(outline_payload, ensure_ascii=False, indent=2))
                archive.writestr("导出说明.txt", "\n".join(manifest_lines))
        except OSError as exc:
            ctx.logger.exception("Memory bundle export failed: %s", target)
            raise HTTPException(
                status_code=500,
                detail="Memory bundle export failed. Please check disk space or file permissions.",
            ) from exc

        return FileResponse(path=target, filename=filename, media_type="application/zip")

    @app.post("/api/memories/import-bundle")
    async def api_import_memory_bundle(file: UploadFile = File(...)) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        filename = Path(file.filename or "").name.lower()
        if not filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="完整记忆包必须是 .zip 文件。")

        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="完整记忆包不能为空。")

        def payload_items(payload: Any) -> list[Any]:
            if isinstance(payload, dict):
                if isinstance(payload.get("items"), list):
                    return payload["items"]
                if isinstance(payload.get("memories"), list):
                    return payload["memories"]
                if isinstance(payload.get("merged_memories"), list):
                    return payload["merged_memories"]
                if isinstance(payload.get("memory_outline"), list):
                    return payload["memory_outline"]
            if isinstance(payload, list):
                return payload
            return []

        def read_bundle_json(archive: ZipFile, entry_name: str) -> list[Any]:
            candidates = [name for name in archive.namelist() if Path(name).name == entry_name]
            if not candidates:
                return []
            try:
                with archive.open(candidates[0]) as handle:
                    payload = json.loads(handle.read().decode("utf-8-sig"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"完整记忆包中的 {entry_name} 读取失败。") from exc
            return payload_items(payload)

        def clone_rows(rows: list[Any]) -> list[dict[str, Any]]:
            cloned: list[dict[str, Any]] = []
            for row in rows:
                if isinstance(row, dict):
                    cloned.append(json.loads(json.dumps(row, ensure_ascii=False)))
            return cloned

        def ensure_unique_ids(
            rows: list[dict[str, Any]],
            existing_ids: set[str],
            *,
            prefix: str,
        ) -> tuple[list[dict[str, Any]], dict[str, str]]:
            id_map: dict[str, str] = {}
            normalized: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                old_id = str(item.get("id", "") or "").strip()
                new_id = old_id
                if not new_id or new_id in existing_ids:
                    new_id = f"{prefix}-{uuid4().hex[:10]}"
                item["id"] = new_id
                existing_ids.add(new_id)
                if old_id:
                    id_map[old_id] = new_id
                normalized.append(item)
            return normalized, id_map

        try:
            with ZipFile(BytesIO(raw_bytes), "r") as archive:
                imported_memories_raw = read_bundle_json(archive, "memories.json")
                imported_merged_raw = read_bundle_json(archive, "merged_memories.json")
                imported_outline_raw = read_bundle_json(archive, "memory_outline.json")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="完整记忆包 ZIP 读取失败，请确认文件格式正确。") from exc

        if not any([imported_memories_raw, imported_merged_raw, imported_outline_raw]):
            raise HTTPException(status_code=400, detail="完整记忆包中没有可导入的记忆数据。")

        current_memories = clone_rows(ctx.get_memories(active_slot))
        current_merged = clone_rows(get_merged_memories(ctx, active_slot))
        current_outline = clone_rows(get_memory_outline(ctx, active_slot))

        imported_memories, memory_id_map = ensure_unique_ids(
            clone_rows(imported_memories_raw),
            {str(item.get("id", "")) for item in current_memories if isinstance(item, dict)},
            prefix="memory-import",
        )
        imported_merged, _ = ensure_unique_ids(
            clone_rows(imported_merged_raw),
            {str(item.get("id", "")) for item in current_merged if isinstance(item, dict)},
            prefix="merged-import",
        )
        imported_outline, _ = ensure_unique_ids(
            clone_rows(imported_outline_raw),
            {str(item.get("id", "")) for item in current_outline if isinstance(item, dict)},
            prefix="outline-import",
        )

        def remap_source_ids(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                source_ids = row.get("source_memory_ids")
                if isinstance(source_ids, list):
                    row["source_memory_ids"] = [memory_id_map.get(str(item), str(item)) for item in source_ids]

        remap_source_ids(imported_merged)
        remap_source_ids(imported_outline)

        memories = ctx.save_memories(current_memories + imported_memories, active_slot)
        merged_items = save_merged_memories(ctx, current_merged + imported_merged, active_slot)
        outline_items = save_memory_outline(ctx, current_outline + imported_outline, active_slot)

        return {
            "ok": True,
            "active_slot": active_slot,
            "imported": {
                "memories": len(imported_memories),
                "merged_memories": len(imported_merged),
                "memory_outline": len(imported_outline),
            },
            "items": memories,
            "merged_items": merged_items,
            "outline_items": outline_items,
        }

    @app.post("/api/memories/merge")
    async def api_merge_memories(payload: MemoryMergePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return await merge_memories_to_outline(
            ctx,
            payload.memory_ids,
            merged_title=payload.merged_title,
            outline_title=payload.outline_title,
            delete_sources=payload.delete_sources,
            slot_id=active_slot,
            runtime_overrides=payload.runtime_config,
        )

    @app.get("/api/worldbook")
    async def api_get_worldbook() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        store = ctx.get_worldbook_store(active_slot)
        return {"items": store["entries"], "settings": store["settings"]}

    @app.get("/api/worldbook/export")
    async def api_export_worldbook() -> FileResponse:
        active_slot = ctx.get_active_slot_id()
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        filename = "worldbook.json"
        target = ctx.EXPORT_DIR / filename
        ctx.persist_json(
            target,
            ctx.get_worldbook_store(active_slot),
            detail="Worldbook export failed. Please check disk space or file permissions.",
        )
        return FileResponse(path=target, filename=filename, media_type="application/json")

    @app.post("/api/worldbook/import")
    async def api_import_worldbook(payload: JsonImportPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        parsed = parse_json_import_payload(payload.raw_json, label="Worldbook")
        raw_store = parsed
        if isinstance(parsed, dict) and "worldbook" in parsed:
            raw_store = parsed["worldbook"]
        if isinstance(raw_store, dict) and "items" in raw_store and "entries" not in raw_store:
            raw_store = {
                "settings": raw_store.get("settings", {}),
                "entries": raw_store.get("items", []),
            }

        current_store = ctx.get_worldbook_store(active_slot)
        current_settings = current_store.get("settings", {})

        if isinstance(raw_store, dict):
            import_settings = raw_store.get("settings", {})
            import_entries = raw_store.get("entries", [])
        elif isinstance(raw_store, list):
            import_settings = {}
            import_entries = raw_store
        else:
            import_settings = {}
            import_entries = []

        effective_entries = _apply_worldbook_import_options(
            import_entries if isinstance(import_entries, list) else [],
            missing_injection_policy=payload.missing_injection_policy,
            force_in_chat_depth=payload.force_in_chat_depth,
            force_injection_order=payload.force_injection_order,
        )

        store_to_save = {
            "settings": import_settings if payload.apply_settings else current_settings,
            "entries": effective_entries,
        }
        saved_store = ctx.save_worldbook_store(store_to_save, active_slot)
        return {"ok": True, "items": saved_store["entries"], "settings": saved_store["settings"]}

    @app.post("/api/worldbook")
    async def api_save_worldbook(payload: WorldbookPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        existing_store = ctx.get_worldbook_store(active_slot)
        existing_entries = existing_store["entries"]
        merged_items: list[dict[str, Any]] = []
        for index, item in enumerate(payload.items, start=1):
            row = item.model_dump(exclude_unset=True)
            trigger = str(row.get("trigger", "") or "").strip()
            content = str(row.get("content", "") or "").strip()
            previous = next((entry for entry in existing_entries if str(entry.get("trigger", "")).strip() == trigger), {})
            effective_trigger = trigger or str(previous.get("trigger", "")).strip()
            effective_content = content or str(previous.get("content", "")).strip()
            if not effective_trigger or not effective_content:
                continue

            merged = dict(previous)
            if row.get("id"):
                merged["id"] = row.get("id")
            else:
                merged.setdefault("id", f"worldbook-{index}")
            merged["title"] = str(row.get("title", "") or merged.get("title", f"词条 {index}")).strip() or f"词条 {index}"
            merged["trigger"] = effective_trigger
            merged["secondary_trigger"] = str(
                row.get("secondary_trigger", merged.get("secondary_trigger", ""))
            ).strip()
            merged["content"] = effective_content
            for key in [
                "enabled",
                "priority",
                "case_sensitive",
                "whole_word",
                "match_mode",
                "secondary_mode",
                "comment",
                "group",
                "entry_type",
                "group_operator",
                "chance",
                "sticky_turns",
                "cooldown_turns",
                "order",
                "insertion_position",
                "injection_depth",
                "injection_role",
                "injection_order",
                "recursive_enabled",
                "prevent_further_recursion",
            ]:
                if key in row:
                    merged[key] = row[key]
            merged_items.append(merged)

        store_to_save = {
            "settings": payload.settings.model_dump() if payload.settings is not None else existing_store["settings"],
            "entries": merged_items,
        }
        saved_store = ctx.save_worldbook_store(store_to_save, active_slot)
        return {"ok": True, "items": saved_store["entries"], "settings": saved_store["settings"]}

    @app.get("/api/worldbook/settings")
    async def api_get_worldbook_settings() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {"settings": ctx.get_worldbook_settings(active_slot)}

    @app.post("/api/worldbook/settings")
    async def api_save_worldbook_settings(payload: WorldbookSettingsPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        settings = ctx.save_worldbook_settings(payload.model_dump(), active_slot)
        return {"ok": True, "settings": settings}

    @app.get("/api/worldbook/entries")
    async def api_get_worldbook_entries() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {
            "items": ctx.get_worldbook_entries(active_slot),
            "settings": ctx.get_worldbook_settings(active_slot),
        }

    @app.post("/api/worldbook/entries")
    async def api_save_worldbook_entries(payload: WorldbookPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        items = ctx.save_worldbook_entries([item.model_dump() for item in payload.items], active_slot)
        return {"ok": True, "items": items, "settings": ctx.get_worldbook_settings(active_slot)}

    @app.post("/api/worldbook/dynamic-preview")
    async def api_preview_dynamic_worldbook(payload: DynamicWorldbookPreviewPayload) -> dict[str, Any]:
        effective_payload = payload.model_copy(
            update={"slot_id": payload.slot_id or ctx.get_active_slot_id()}
        )
        preview = ctx.slot_runtime_service.build_slot_injection_payload(effective_payload)
        return {"ok": True, **preview}

    @app.get("/api/sprites")
    async def api_get_sprites() -> dict[str, Any]:
        return {
            "active_slot": ctx.get_active_slot_id(),
            "base_path": ctx.default_sprite_base_path_for_slot(),
            "items": ctx.list_sprite_assets(),
        }

    @app.post("/api/sprites")
    async def api_upload_sprite(
        tag: str = Form(""),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ctx.ALLOWED_IMAGE_SUFFIXES:
            raise HTTPException(status_code=400, detail="Only png / jpg / jpeg / webp / gif sprites are supported.")
        if file.content_type and not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Uploaded sprite must be an image file.")

        content = await file.read(ctx.MAX_BACKGROUND_UPLOAD_SIZE_BYTES + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded sprite cannot be empty.")
        if len(content) > ctx.MAX_BACKGROUND_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Sprite image cannot be larger than 30 MB.")

        active_slot = ctx.get_active_slot_id()
        directory = ctx.sprite_dir_path()
        directory.mkdir(parents=True, exist_ok=True)

        normalized_tag = ctx.sanitize_sprite_filename_tag(tag) or ctx.sanitize_sprite_filename_tag(Path(file.filename or "").stem)
        if not normalized_tag:
            raise HTTPException(status_code=400, detail="Please provide a valid sprite tag.")

        for existing in directory.glob(f"{normalized_tag}.*"):
            if existing.is_file() and existing.suffix.lower() in ctx.ALLOWED_IMAGE_SUFFIXES:
                existing.unlink(missing_ok=True)

        target = directory / f"{normalized_tag}{suffix}"
        try:
            target.write_bytes(content)
        except OSError as exc:
            ctx.logger.exception("Sprite write failed: %s", target)
            raise HTTPException(
                status_code=500,
                detail="Sprite save failed. Please check disk space or file permissions.",
            ) from exc

        return {
            "ok": True,
            "active_slot": active_slot,
            "base_path": ctx.default_sprite_base_path_for_slot(),
            "uploaded": {
                "filename": target.name,
                "tag": normalized_tag,
                "url": f"{ctx.default_sprite_base_path_for_slot()}/{target.name}",
            },
            "items": ctx.list_sprite_assets(),
        }

    @app.post("/api/sprites/delete")
    async def api_delete_sprite(payload: SpriteDeletePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        filename = Path(str(payload.filename or "")).name
        if not filename:
            raise HTTPException(status_code=400, detail="Sprite filename is required.")

        target = ctx.sprite_dir_path() / filename
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Sprite file not found.")
        if target.suffix.lower() not in ctx.ALLOWED_IMAGE_SUFFIXES:
            raise HTTPException(status_code=400, detail="Unsupported sprite file type.")

        try:
            target.unlink()
        except OSError as exc:
            ctx.logger.exception("Sprite delete failed: %s", target)
            raise HTTPException(status_code=500, detail="Sprite delete failed. Please check file permissions.") from exc

        return {
            "ok": True,
            "active_slot": active_slot,
            "base_path": ctx.default_sprite_base_path_for_slot(),
            "items": ctx.list_sprite_assets(),
        }

    @app.get("/api/cards")
    async def api_get_cards() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        return {
            "items": ctx.list_role_card_files(),
            "current_card": ctx.get_current_card(active_slot),
            "workshop_state": ctx.get_workshop_state(active_slot),
        }

    @app.post("/api/cards/import")
    async def api_import_card(payload: RoleCardPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        card = ctx.parse_role_card_json(payload.raw_json)
        filename = Path(payload.filename.strip() or f"{card.get('name', 'role_card')}.json").name
        if not filename.lower().endswith(".json"):
            filename += ".json"

        ctx.persist_json(
            ctx.CARDS_DIR / filename,
            card,
            detail="Card save failed: could not write to the cards directory.",
        )

        result: dict[str, Any] = {"ok": True, "filename": filename}
        if payload.apply_now:
            result.update(ctx.apply_role_card(card, source_name=filename, slot_id=active_slot))
            result["workshop"] = ctx.evaluate_creative_workshop(slot_id=active_slot, reason="load")
        result["card"] = card
        return result

    @app.post("/api/cards/load")
    async def api_load_card(payload: RoleCardLoadPayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        filename = Path(payload.filename).name
        target = ctx.CARDS_DIR / filename
        if not target.exists():
            raise HTTPException(status_code=404, detail="The requested card file was not found.")
        if target.suffix.lower() not in ctx.ROLE_CARD_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Card files must use the .json or .txt extension.")

        raw_text = ctx.read_role_card_text(target)
        card = ctx.parse_role_card_json(raw_text)
        result = ctx.apply_role_card(card, source_name=filename, slot_id=active_slot)
        result["workshop"] = ctx.evaluate_creative_workshop(slot_id=active_slot, reason="load")
        result.update({"ok": True, "filename": filename, "card": card})
        return result

    @app.get("/api/cards/export/current")
    async def api_export_current_card() -> FileResponse:
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        current_card = ctx.get_current_card()
        card = current_card.get("raw", {})
        if not isinstance(card, dict) or not any(
            str(value).strip() for value in card.values() if not isinstance(value, (dict, list))
        ):
            raise HTTPException(status_code=404, detail="The current card is missing or not loaded yet.")

        source_name = Path(str(current_card.get("source_name", "")).strip() or "role_card_export.json").name
        if not source_name.lower().endswith(".json"):
            source_name += ".json"
        export_path = ctx.EXPORT_DIR / source_name
        ctx.persist_json(
            export_path,
            ctx.normalize_role_card(card),
            detail="Current card export failed. Please check file permissions.",
        )
        return FileResponse(
            path=export_path,
            filename=source_name,
            media_type="application/json",
        )

    @app.get("/api/export/current-bundle")
    async def api_export_current_bundle() -> FileResponse:
        ctx.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        bundle_label, current_card, card = build_bundle_label()
        export_path = ctx.EXPORT_DIR / f"{bundle_label}存档.zip"

        memories_payload = {"items": ctx.get_memories()}
        worldbook_payload = ctx.get_worldbook_store()
        preset_payload = ctx.get_preset_store()
        manifest_lines = [
            f"导出角色：{bundle_label}",
            "",
            f"1. {bundle_label}的人设卡.json",
            f"2. {bundle_label}的记忆.json",
            f"3. {bundle_label}的世界书.json",
            f"4. {bundle_label}的预设.json",
            "",
            f"原始角色卡文件：{str(current_card.get('source_name', '')).strip() or '未命名角色卡'}",
            f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        try:
            with ZipFile(export_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    f"{bundle_label}的人设卡.json",
                    json.dumps(card, ensure_ascii=False, indent=2),
                )
                archive.writestr(
                    f"{bundle_label}的记忆.json",
                    json.dumps(memories_payload, ensure_ascii=False, indent=2),
                )
                archive.writestr(
                    f"{bundle_label}的世界书.json",
                    json.dumps(worldbook_payload, ensure_ascii=False, indent=2),
                )
                archive.writestr(
                    f"{bundle_label}的预设.json",
                    json.dumps(preset_payload, ensure_ascii=False, indent=2),
                )
                archive.writestr(
                    f"{bundle_label}的导出说明.txt",
                    "\n".join(manifest_lines),
                )
        except OSError as exc:
            ctx.logger.exception("Bundle export failed: %s", export_path)
            raise HTTPException(
                status_code=500,
                detail="存档压缩包导出失败，请检查磁盘空间或文件权限。",
            ) from exc

        return FileResponse(
            path=export_path,
            filename=export_path.name,
            media_type="application/zip",
        )

    @app.get("/api/workshop/status")
    async def api_get_workshop_status() -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        current_card = ctx.get_current_card(active_slot)
        workshop = ctx.sanitize_creative_workshop(current_card.get("raw", {}).get("creativeWorkshop", {}))
        state = ctx.get_workshop_state(active_slot)
        stage = ctx.get_workshop_stage(state.get("temp", 0))
        return {
            "ok": True,
            "active_slot": active_slot,
            "current_card": current_card,
            "workshop": workshop,
            "state": state,
            "stage": stage,
            "stage_label": ctx.get_workshop_stage_label(stage),
            "signature": ctx.workshop_signature(current_card, workshop, stage),
        }

    @app.post("/api/workshop/save")
    async def api_save_workshop(payload: WorkshopSavePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        result = ctx.save_workshop_card(payload.creativeWorkshop, slot_id=active_slot)
        return {
            "ok": True,
            "active_slot": active_slot,
            "current_card": result["current_card"],
            "card": result["card"],
            "workshop": result["workshop"],
            "state": result["workshop_state"],
        }

    @app.post("/api/workshop/evaluate")
    async def api_evaluate_workshop(payload: WorkshopEvaluatePayload) -> dict[str, Any]:
        active_slot = ctx.get_active_slot_id()
        if payload.advance_temp:
            state = ctx.get_workshop_state(active_slot)
            state["temp"] = max(0, int(state.get("temp", 0) or 0) + 1)
            state["pending_temp"] = state["temp"]
            ctx.save_workshop_state(state, active_slot)
        workshop = ctx.evaluate_creative_workshop(slot_id=active_slot, reason=payload.reason)
        return {
            "ok": True,
            "active_slot": active_slot,
            "workshop": workshop,
            "state": ctx.get_workshop_state(active_slot),
        }

    @app.post("/api/background")
    async def api_upload_background(file: UploadFile = File(...)) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ctx.ALLOWED_IMAGE_SUFFIXES:
            raise HTTPException(status_code=400, detail="Only png / jpg / jpeg / webp / gif images are supported.")
        if file.content_type and not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="The uploaded file must be an image.")

        content = await file.read(ctx.MAX_BACKGROUND_UPLOAD_SIZE_BYTES + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file cannot be empty.")
        if len(content) > ctx.MAX_BACKGROUND_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Background image cannot be larger than 30 MB.")

        ctx.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"bg_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"
        target = ctx.UPLOAD_DIR / filename
        try:
            target.write_bytes(content)
        except OSError as exc:
            ctx.logger.exception("Background image write failed: %s", target)
            raise HTTPException(
                status_code=500,
                detail="Background image save failed. Please check disk space or file permissions.",
            ) from exc

        return {"ok": True, "url": f"/static/uploads/{filename}"}

    @app.post("/api/workshop/upload")
    async def api_upload_workshop_asset(
        kind: str = Form("image"),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        return await ctx.save_workshop_asset_upload(kind=kind, file=file)

    @app.post("/api/models")
    async def api_get_models() -> dict[str, Any]:
        llm_config = ctx.get_runtime_chat_config()
        models = await ctx.fetch_available_models(
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
        llm_config = ctx.get_runtime_chat_config()
        if not (llm_config["base_url"] and llm_config["model"]):
            raise HTTPException(status_code=400, detail="Please enter both the chat API URL and model name first.")

        reply = await ctx.request_minimal_model_reply()
        return {"ok": True, "reply": reply.get("reply", ""), "sprite_tag": reply.get("sprite_tag", "")}

    @app.post("/api/test-embedding")
    async def api_test_embedding() -> dict[str, Any]:
        embedding = ctx.get_runtime_embedding_config()
        if not (embedding["base_url"] and embedding["model"]):
            raise HTTPException(status_code=400, detail="Please enter both the embedding API URL and model name first.")

        vectors = await ctx.fetch_embeddings(["connection test", "vector search"])
        if not vectors:
            raise HTTPException(status_code=502, detail="The embedding model did not return any vectors.")

        return {"ok": True, "dimension": len(vectors[0]), "count": len(vectors)}
