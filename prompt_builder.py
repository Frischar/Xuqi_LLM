
from __future__ import annotations

from typing import Any, Callable

_DEPS: dict[str, Callable[..., Any]] = {}


def configure_prompt_builder(**deps: Callable[..., Any]) -> None:
    _DEPS.update({key: value for key, value in deps.items() if callable(value)})


def _dep(name: str) -> Callable[..., Any]:
    fn = _DEPS.get(name)
    if not callable(fn):
        raise RuntimeError(
            f"prompt_builder dependency '{name}' is not configured. "
            "Call configure_prompt_builder(...) during app startup."
        )
    return fn


def _worldbook_direct_question(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    markers = (
        "what", "who", "why", "how", "tell me", "explain", "?", "？",
        "什么", "是谁", "为啥", "为什么", "怎么", "如何", "解释", "告诉我", "说说", "介绍",
    )
    return any(marker in text for marker in markers)


def build_worldbook_prompt(
    matches: list[dict[str, Any]],
    *,
    heading: str = "The following are the worldbook notes matched in this turn.",
) -> str:
    if not matches:
        return ""

    blocks = [
        heading,
        "These are high-priority factual backdrops for the current conversation.",
        "If the user is asking about any of these items directly, answer from these notes first.",
        "Do not mention that you saw the worldbook notes in your answer.",
    ]
    for index, item in enumerate(matches, start=1):
        matched = item.get("matched", "")
        title = str(item.get("title", "")).strip()
        lines = [f"{index}. Title: {title or item['trigger']}"]
        source = str(item.get("source", "keyword")).strip()
        if source:
            lines.append(f"Source: {source}")
        group = str(item.get("group", "")).strip()
        if group:
            lines.append(f"Group: {group}")
        if item.get("trigger"):
            lines.append(f"Trigger: {item['trigger']}")
        if matched:
            lines.append(f"Matched: {matched}")
        if item.get("secondary_trigger"):
            lines.append(f"Secondary trigger: {item['secondary_trigger']}")
        lines.append(f"Content: {item['content']}")
        if item.get("comment"):
            lines.append(f"Comment: {item['comment']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_worldbook_answer_guard(user_message: str, matches: list[dict[str, Any]]) -> str:
    if not matches:
        return ""

    text = str(user_message or "").strip()
    if not text or not _worldbook_direct_question(text):
        return ""

    primary_match = matches[0]
    subject = primary_match.get("matched") or primary_match.get("title") or primary_match.get("trigger") or "this item"
    fact = str(primary_match.get("content", "")).strip()
    if not fact:
        return ""

    return (
        f'The user is directly asking about "{subject}".\n'
        f"Your first sentence must state the core fact directly, for example: {fact}\n"
        "Answer directly first, then continue in character without dodging or pretending not to know."
    )


def build_retrieval_prompt(retrieved_items: list[dict[str, Any]]) -> str:
    if not retrieved_items:
        return ""

    blocks = [
        "The following are the most relevant long-term memories for the current message.",
        "Use them as supporting context, but do not hallucinate details that are not present.",
    ]
    for index, item in enumerate(retrieved_items, start=1):
        title = str(item.get("title", "")).strip() or f"Memory {index}"
        blocks.append(f"{index}. {title}\n{item.get('text', '')}")
    return "\n\n".join(blocks)


def build_memory_recap_prompt(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""

    sanitize_tags = _dep("sanitize_tags")
    blocks = [
        "The following are long-term memories that should stay consistent over time.",
        "Treat them as durable background facts unless the user explicitly asks to revise them.",
    ]
    for index, item in enumerate(memories, start=1):
        title = str(item.get("title", "")).strip() or f"Memory {index}"
        content = str(item.get("content", "")).strip()
        tags = ", ".join(sanitize_tags(item.get("tags", [])))
        notes = str(item.get("notes", "")).strip()
        lines = [f"{index}. {title}"]
        if content:
            lines.append(f"Content: {content}")
        if tags:
            lines.append(f"Tags: {tags}")
        if notes:
            lines.append(f"Notes: {notes}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_user_profile_prompt(user_profile: dict[str, Any]) -> str:
    if not isinstance(user_profile, dict):
        return ""

    display_name = str(user_profile.get("display_name", "")).strip()
    nickname = str(user_profile.get("nickname", "")).strip()
    profile_text = str(user_profile.get("profile_text", "")).strip()
    notes = str(user_profile.get("notes", "")).strip()

    if display_name == "" and not any([nickname, profile_text, notes]):
        return ""

    blocks = [
        "The following are the user profile details bound to the current slot.",
        "Treat them as stable background information for addressing and understanding the user.",
        "Do not rewrite these details as if they were your own persona settings.",
    ]
    if display_name:
        blocks.append(f"Display name: {display_name}")
    if nickname:
        blocks.append(f"Nickname: {nickname}")
    if profile_text:
        blocks.append(f"Profile text: {profile_text}")
    if notes:
        blocks.append(f"Notes: {notes}")
    return "\n".join(blocks)


def build_sprite_prompt(llm_config: dict[str, Any]) -> str:
    if not llm_config.get("sprite_enabled", True):
        return ""

    return (
        "Always start every reply with a single sprite tag on the first line in the format [expression:tag].\n"
        "Do not omit the tag. Do not place anything before it.\n"
        "Keep the tag short and simple, such as happy, calm, angry, sad, or surprised.\n"
        "After the tag, write the normal reply. Do not explain the rule.\n"
    )


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


def build_prompt_package(
    user_message: str,
    retrieved_items: list[dict[str, Any]] | None = None,
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    get_persona = _dep("get_persona")
    get_conversation = _dep("get_conversation")
    get_memories = _dep("get_memories")
    get_user_profile = _dep("get_user_profile")
    get_runtime_chat_config = _dep("get_runtime_chat_config")
    bucket_worldbook_matches = _dep("bucket_worldbook_matches")
    normalize_worldbook_injection_role = _dep("normalize_worldbook_injection_role")
    build_preset_prompt = _dep("build_preset_prompt")

    persona = get_persona()
    history = get_conversation()
    memories = get_memories()
    user_profile = get_user_profile()
    llm_config = get_runtime_chat_config(runtime_overrides)

    matched_worldbook_entries = worldbook_matches or []
    recalled_memories = retrieved_items or []
    worldbook_buckets = bucket_worldbook_matches(matched_worldbook_entries)

    preset_prompt = build_preset_prompt()
    system_prompt = str(persona.get("system_prompt", "")).strip()
    memory_recap_prompt = build_memory_recap_prompt(memories)
    user_profile_prompt = build_user_profile_prompt(user_profile)
    worldbook_before_char_defs_prompt = build_worldbook_prompt(
        worldbook_buckets["before_char_defs"],
        heading="The following worldbook notes must be considered before the character definition.",
    )
    worldbook_after_char_defs_prompt = build_worldbook_prompt(
        worldbook_buckets["after_char_defs"],
        heading="The following worldbook notes refine or extend the character definition for this turn.",
    )
    worldbook_answer_guard = build_worldbook_answer_guard(user_message, matched_worldbook_entries)
    retrieval_prompt = build_retrieval_prompt(recalled_memories)
    sprite_prompt = build_sprite_prompt(llm_config)

    history_limit = max(1, int(llm_config["history_limit"]))
    recent_history = history[-history_limit:]
    recent_history_text = build_conversation_transcript(recent_history)

    actual_system_sections = [
        prompt
        for prompt in [
            preset_prompt,
            worldbook_before_char_defs_prompt,
            system_prompt,
            worldbook_after_char_defs_prompt,
            memory_recap_prompt,
            user_profile_prompt,
            retrieval_prompt,
            worldbook_answer_guard,
            sprite_prompt,
        ]
        if str(prompt or "").strip()
    ]

    messages: list[dict[str, str]] = []
    if actual_system_sections:
        messages.append({"role": "system", "content": "\n\n".join(actual_system_sections)})

    in_chat_buckets = worldbook_buckets.get("in_chat", {})

    def append_in_chat_bucket(depth: int) -> None:
        bucket = in_chat_buckets.get(depth, [])
        if not bucket:
            return

        system_items: list[dict[str, Any]] = []
        for item in bucket:
            role = normalize_worldbook_injection_role(item.get("injection_role", "system"), "system")
            if role == "system":
                system_items.append(item)

        if system_items:
            content = build_worldbook_prompt(
                system_items,
                heading=f"The following are in-chat worldbook notes at depth {depth}.",
            )
            if content:
                messages.append({"role": "system", "content": content})

    history_count = len(recent_history)
    for index, item in enumerate(recent_history):
        tail_depth = history_count - index
        append_in_chat_bucket(tail_depth)

        role = str(item.get("role", "assistant")).strip() or "assistant"
        content = str(item.get("content", "")).strip()
        if content:
            messages.append({"role": role, "content": content})

    append_in_chat_bucket(0)

    clean_user_message = str(user_message or "").strip()
    messages.append({"role": "user", "content": clean_user_message})

    layers: list[dict[str, Any]] = []

    def append_layer(layer_id: str, title: str, sections: list[str], **meta: Any) -> None:
        content = "\n\n".join(part for part in sections if str(part or "").strip()).strip()
        if not content:
            return
        layer: dict[str, Any] = {
            "id": layer_id,
            "title": title,
            "content": content,
        }
        if meta:
            layer["meta"] = meta
        layers.append(layer)

    append_layer(
        "system_main",
        "系统提示词 / 主提示",
        [preset_prompt],
        section_count=1 if preset_prompt else 0,
    )
    append_layer(
        "worldbook_before_char_defs",
        "世界书（角色定义前）",
        [worldbook_before_char_defs_prompt],
        hit_count=len(worldbook_buckets["before_char_defs"]),
    )
    append_layer(
        "role_card",
        "角色卡固定设定",
        [system_prompt],
        character_name=str(persona.get("name", "")).strip(),
    )
    append_layer(
        "worldbook_after_char_defs",
        "世界书（角色定义后）",
        [worldbook_after_char_defs_prompt],
        hit_count=len(worldbook_buckets["after_char_defs"]),
    )
    append_layer(
        "memory_context",
        "记忆 / 摘要 / 长期信息",
        [memory_recap_prompt, retrieval_prompt, user_profile_prompt],
        stored_memory_count=len(memories),
        recalled_memory_count=len(recalled_memories),
    )
    for depth in sorted(in_chat_buckets):
        append_layer(
            f"worldbook_in_chat_depth_{depth}",
            f"世界书（聊天深度 {depth}）",
            [build_worldbook_prompt(in_chat_buckets[depth], heading=f"In-chat depth {depth}")],
            hit_count=len(in_chat_buckets[depth]),
            depth=depth,
        )
    append_layer(
        "worldbook_answer_guard",
        "世界书回答守卫",
        [worldbook_answer_guard],
        hit_count=len(matched_worldbook_entries),
    )
    append_layer(
        "output_rules",
        "输出格式约束",
        [sprite_prompt],
        sprite_enabled=bool(llm_config.get("sprite_enabled", True)),
    )
    append_layer(
        "recent_history",
        "最近聊天记录",
        [recent_history_text],
        turn_count=len(recent_history),
    )
    append_layer(
        "user_input",
        "本轮新输入",
        [clean_user_message],
        char_count=len(clean_user_message),
    )

    preview_blocks: list[str] = []
    for index, layer in enumerate(layers, start=1):
        preview_blocks.append(f"[{index}. {layer['title']}]\n{layer['content']}")

    return {
        "layers": layers,
        "messages": messages,
        "preview_text": "\n\n".join(preview_blocks).strip(),
        "message_count": len(messages),
        "system_section_count": len(actual_system_sections),
        "recent_history_turns": len(recent_history),
    }


def build_messages(
    user_message: str,
    retrieved_items: list[dict[str, Any]] | None = None,
    *,
    runtime_overrides: dict[str, Any] | None = None,
    worldbook_matches: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    return build_prompt_package(
        user_message,
        retrieved_items,
        runtime_overrides=runtime_overrides,
        worldbook_matches=worldbook_matches,
    )["messages"]


__all__ = [
    "configure_prompt_builder",
    "build_conversation_transcript",
    "build_memory_recap_prompt",
    "build_messages",
    "build_prompt_package",
    "build_retrieval_prompt",
    "build_sprite_prompt",
    "build_user_profile_prompt",
    "build_worldbook_answer_guard",
    "build_worldbook_prompt",
]
