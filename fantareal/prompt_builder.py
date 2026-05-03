
from __future__ import annotations

import re
from typing import Any, Callable

_DEPS: dict[str, Callable[..., Any]] = {}

V4F_OUTPUT_GUARD_MARKER = "[[RUNTIME_ONLY:V4F_OUTPUT_GUARD]]"
V4F_OUTPUT_GUARD_PROMPT = (
    "【V4F稳定器】\n"
    "本段是本轮回复前的临近约束，只用于稳定 DeepSeek V4-Flash 的 RP 输出，不要在回复中提及这些规则。\n"
    "严格遵守当前角色卡、预设、世界书、记忆和用户指定的输出格式。\n"
    "禁止输出规则解释、分析标题、总结列表、自我说明或与剧情无关的补充说明。\n"
    "严禁替用户补写未在本轮输入中明确出现的动作、台词、心理、决定、情绪结论和身体反应。\n"
    "可以承接或引用用户已经明确写出的动作、姿态、位置和可见状态，但不得新增、改写或推进用户未写出的行为。\n"
    "用户只能由用户自己推进；你的主要描写对象应是非用户角色、环境和当前场景变化。\n"
    "优先通过非用户角色的细微反应承接当前情绪，例如眼神、停顿、呼吸、手指动作、身体距离、语气变化。\n"
    "若场景不适合，不要强行堆叠动作描写。\n"
    "不要直接用“她很感动 / 她很害羞 / 她很难过”等情绪结论替代描写。\n"
    "优先通过动作、对白、停顿和场景互动表现情绪。\n"
    "避免反复使用同一种细微动作或固定句式。\n"
    "不要频繁重复“浅笑、垂眸、指尖、呼吸一滞、偏了偏头”等相似表达。\n"
    "保持角色原本的语气、性格和当前预设文风。\n"
    "不要为了执行本规则，把所有角色都写成温柔、克制、含蓄的同一种口吻。\n"
    "若当前角色卡、预设或用户输入中要求输出状态变量、好感变量、信任变量或类似结尾标签，则这些标签视为强制输出格式，每轮不得省略。 \n"
    "状态变量必须放在整条回复的最后，作为独立区块输出，不得混入正文叙述、旁白或角色台词中。 \n"
    "即使本轮关系没有明显变化，也必须按既定格式输出无变化状态，例如使用+0或原角色卡指定的无变化写法。 \n"
    "不得用“她更加信任你了 / 好感提升 / 关系变近了”等正文描述替代状态变量标签。 \n"
    "如果角色卡或预设已经指定了状态变量格式，必须优先沿用原格式，不得自行改名、改格式或省略字段。 \n"
    "若当前预设要求输出TTS标签，则只有角色直接台词可以附带TTS标签，旁白、动作、环境描写和心理描写不得附带TTS标签。 \n"
    "TTS标签必须严格使用预设指定格式，不得解释标签含义，不得把隐藏标签当作正文内容复述。 \n"
    "结尾应停在仍可继续互动的位置，不要写成总结、落幕、升华、回顾或明显收束。"
)


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


def _optional_dep(name: str) -> Callable[..., Any] | None:
    fn = _DEPS.get(name)
    return fn if callable(fn) else None


def _extract_runtime_guard_from_preset(preset_prompt: str) -> tuple[str, str]:
    text = str(preset_prompt or "")
    if V4F_OUTPUT_GUARD_MARKER not in text:
        return text.strip(), ""
    cleaned = text.replace(V4F_OUTPUT_GUARD_MARKER, "").strip()
    return cleaned, V4F_OUTPUT_GUARD_PROMPT.strip()


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
    if not llm_config.get("sprite_enabled", False):
        return ""

    return (
        "Always start every reply with a single sprite tag on the first line in the format [expression:tag].\n"
        "Do not omit the tag. Do not place anything before it.\n"
        "Keep the tag short and simple, such as happy, calm, angry, sad, or surprised.\n"
        "After the tag, write the normal reply. Do not explain the rule.\n"
    )


def strip_thought_blocks(text: Any) -> str:
    """Keep stored chat intact, but remove <think>...</think> blocks before building prompts."""
    content = str(text or "")

    # Remove completed thinking blocks.
    content = re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove an unfinished thinking block if a streamed reply was interrupted.
    content = re.sub(
        r"<think\b[^>]*>.*$",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return content.strip()


def _same_normalized_text(left: Any, right: Any) -> bool:
    """Compare long opening text safely without being too sensitive to whitespace."""
    left_text = re.sub(r"\s+", "\n", str(left or "").strip())
    right_text = re.sub(r"\s+", "\n", str(right or "").strip())
    return bool(left_text and right_text and left_text == right_text)


def _is_opening_only_message(item: dict[str, Any], persona: dict[str, Any] | None = None) -> bool:
    """Opening/greeting is UI-only. It must not be sent back as chat history context."""
    if not isinstance(item, dict):
        return False

    if item.get("source") in {"character_opening", "opening_message", "first_mes", "greeting"}:
        return True

    if item.get("is_opening") is True or item.get("opening_message") is True:
        return True

    if str(item.get("role", "")).strip() != "assistant":
        return False

    opening_text = ""
    if isinstance(persona, dict):
        opening_text = str(
            persona.get("opening_message")
            or persona.get("first_mes")
            or persona.get("first_message")
            or persona.get("greeting")
            or ""
        ).strip()

    return bool(opening_text and _same_normalized_text(item.get("content", ""), opening_text))


def filter_prompt_history(history: list[dict[str, Any]], persona: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Remove UI-only opening messages before building model prompts."""
    return [item for item in history if not _is_opening_only_message(item, persona)]


def build_conversation_transcript(history: list[dict[str, Any]], persona: dict[str, Any] | None = None) -> str:
    lines: list[str] = []
    for item in filter_prompt_history(history, persona):
        role = item.get("role", "")
        content = strip_thought_blocks(item.get("content", ""))
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
    build_preset_output_guard = _optional_dep("build_preset_output_guard")

    persona = get_persona()
    history = get_conversation()
    memories = get_memories()
    user_profile = get_user_profile()
    llm_config = get_runtime_chat_config(runtime_overrides)

    matched_worldbook_entries = worldbook_matches or []
    recalled_memories = retrieved_items or []
    worldbook_buckets = bucket_worldbook_matches(matched_worldbook_entries)

    preset_prompt = build_preset_prompt()
    preset_prompt, marker_output_guard_prompt = _extract_runtime_guard_from_preset(preset_prompt)
    system_prompt = str(persona.get("system_prompt", "")).strip()
    memory_recap_prompt = build_memory_recap_prompt(memories)
    user_profile_prompt = build_user_profile_prompt(user_profile)
    worldbook_stable_prompt = build_worldbook_prompt(
        worldbook_buckets.get("stable", []),
        heading="The following are stable worldbook notes for durable setting, character grounding, and long-running RP consistency.",
    )
    worldbook_current_state_prompt = build_worldbook_prompt(
        worldbook_buckets.get("current_state", []),
        heading="The following worldbook notes describe the current chapter, location, relationship, or temporary state.",
    )
    worldbook_before_char_defs_prompt = build_worldbook_prompt(
        worldbook_buckets.get("before_char_defs", []),
        heading="The following worldbook notes must be considered before the character definition.",
    )
    worldbook_after_char_defs_prompt = build_worldbook_prompt(
        worldbook_buckets.get("after_char_defs", []),
        heading="The following worldbook notes refine or extend the character definition for this turn.",
    )
    worldbook_dynamic_prompt = build_worldbook_prompt(
        worldbook_buckets.get("dynamic", []),
        heading="The following worldbook notes are temporary turn-level hints for the current message.",
    )
    worldbook_output_guard_prompt = build_worldbook_prompt(
        worldbook_buckets.get("output_guard", []),
        heading="The following worldbook notes are final output-format rules for this turn.",
    )
    worldbook_answer_guard = build_worldbook_answer_guard(user_message, matched_worldbook_entries)
    retrieval_prompt = build_retrieval_prompt(recalled_memories)
    sprite_prompt = build_sprite_prompt(llm_config)
    dependency_output_guard_prompt = str(build_preset_output_guard()).strip() if build_preset_output_guard else ""
    preset_output_guard_prompt = dependency_output_guard_prompt or marker_output_guard_prompt

    history_limit = max(1, int(llm_config["history_limit"]))
    prompt_history = filter_prompt_history(history, persona)
    recent_history = prompt_history[-history_limit:]
    recent_history_text = build_conversation_transcript(recent_history, persona)

    actual_system_sections = [
        prompt
        for prompt in [
            preset_prompt,
            worldbook_before_char_defs_prompt,
            system_prompt,
            worldbook_stable_prompt,
            worldbook_after_char_defs_prompt,
            memory_recap_prompt,
            user_profile_prompt,
            worldbook_current_state_prompt,
            retrieval_prompt,
            worldbook_dynamic_prompt,
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

        role_groups: list[tuple[str, list[dict[str, Any]]]] = []
        for item in bucket:
            role = normalize_worldbook_injection_role(item.get("injection_role", "system"), "system")
            if not role_groups or role_groups[-1][0] != role:
                role_groups.append((role, [item]))
            else:
                role_groups[-1][1].append(item)

        for role, role_items in role_groups:
            content = build_worldbook_prompt(
                role_items,
                heading=f"The following are in-chat worldbook notes at depth {depth}.",
            )
            if content:
                messages.append({"role": role, "content": content})

    history_count = len(recent_history)
    for index, item in enumerate(recent_history):
        tail_depth = history_count - index
        append_in_chat_bucket(tail_depth)

        role = str(item.get("role", "assistant")).strip() or "assistant"
        content = strip_thought_blocks(item.get("content", ""))
        if content:
            messages.append({"role": role, "content": content})

    append_in_chat_bucket(0)

    final_guard_sections = [
        prompt
        for prompt in [
            preset_output_guard_prompt,
            worldbook_output_guard_prompt,
        ]
        if str(prompt or "").strip()
    ]
    if final_guard_sections:
        messages.append({"role": "system", "content": "\n\n".join(final_guard_sections)})

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
        "preset_rules",
        "预设规则：基础系统规则 / 常用模块",
        [preset_prompt],
        preset_section_count=1 if preset_prompt else 0,
    )
    append_layer(
        "worldbook_before_char_defs",
        "角色定义前世界书：高优先级前置设定",
        [worldbook_before_char_defs_prompt],
        hit_count=len(worldbook_buckets.get("before_char_defs", [])),
    )
    append_layer(
        "character_definition",
        "角色卡：人物设定 / 场景 / 示例对话",
        [system_prompt],
        character_name=str(persona.get("name", "")).strip(),
    )
    append_layer(
        "stable_worldbook",
        "稳定世界书：常驻设定 / 固定世界观",
        [worldbook_stable_prompt],
        stable_worldbook_count=len(worldbook_buckets.get("stable", [])),
    )
    append_layer(
        "worldbook_after_char_defs",
        "角色定义后世界书：角色补充设定",
        [worldbook_after_char_defs_prompt],
        hit_count=len(worldbook_buckets.get("after_char_defs", [])),
    )
    append_layer(
        "memory_and_user_profile",
        "长期记忆与用户资料",
        [memory_recap_prompt, user_profile_prompt],
        stored_memory_count=len(memories),
        has_user_profile=bool(user_profile_prompt),
    )
    append_layer(
        "current_state_context",
        "当前状态区：地点 / 章节 / 关系状态",
        [worldbook_current_state_prompt],
        hit_count=len(worldbook_buckets.get("current_state", [])),
    )
    append_layer(
        "retrieval_context",
        "本轮相关记忆：检索召回",
        [retrieval_prompt],
        recalled_memory_count=len(recalled_memories),
    )
    append_layer(
        "dynamic_worldbook",
        "本轮命中世界书：关键词 / 递归 / 临时提示",
        [worldbook_dynamic_prompt],
        hit_count=len(worldbook_buckets.get("dynamic", [])),
    )
    for depth in sorted(in_chat_buckets):
        append_layer(
            f"worldbook_in_chat_depth_{depth}",
            f"聊天深度世界书：插入聊天记录附近 depth {depth}",
            [build_worldbook_prompt(in_chat_buckets[depth], heading=f"In-chat depth {depth}")],
            hit_count=len(in_chat_buckets[depth]),
            depth=depth,
        )
    append_layer(
        "worldbook_answer_guard",
        "设定问答提示：直接问设定时使用",
        [worldbook_answer_guard],
        hit_count=len(matched_worldbook_entries),
    )
    append_layer(
        "recent_history",
        "最近聊天记录：已移除思考链",
        [recent_history_text],
        turn_count=len(recent_history),
    )
    append_layer(
        "final_output_guard",
        "输出格式规则：V4F稳定器 / TTS / 状态变量",
        [sprite_prompt, preset_output_guard_prompt, worldbook_output_guard_prompt],
        sprite_enabled=bool(llm_config.get("sprite_enabled", False)),
        preset_guard_enabled=bool(preset_output_guard_prompt),
        output_worldbook_count=len(worldbook_buckets.get("output_guard", [])),
    )
    append_layer(
        "user_input",
        "本轮用户输入：当前这句话",
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
    "filter_prompt_history",
    "build_memory_recap_prompt",
    "build_messages",
    "build_prompt_package",
    "build_retrieval_prompt",
    "build_sprite_prompt",
    "build_user_profile_prompt",
    "strip_thought_blocks",
    "build_worldbook_answer_guard",
    "build_worldbook_prompt",
]
