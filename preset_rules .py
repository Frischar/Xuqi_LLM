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
    "emotion_detail": True,
    "multi_character_boundary": True,
    "scene_continuation": True,
    "anti_horny": False,
    "anti_deification": False,
    "v4f_output_guard": False,
}

# These modules are shown in the preset UI and saved in preset data,
# but they are not inserted into the normal preset_prompt.
# They are consumed later by prompt_builder so the rule can be placed
# close to the current user input.
RUNTIME_ONLY_PRESET_MODULES = {"v4f_output_guard"}
V4F_OUTPUT_GUARD_MARKER = "[[RUNTIME_ONLY:V4F_OUTPUT_GUARD]]"

V4F_OUTPUT_GUARD_PROMPT = (
    "【V4F稳定器已开启】\n"
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

PRESET_MODULE_RULES: dict[str, dict[str, str]] = {
    "no_user_speaking": {
        "label": "防抢话",
        "prompt": (
            "【防抢话硬规则】\n"
            "严禁替用户补写未在本轮输入中明确出现的动作、台词、心理、决定、情绪结论和身体反应。\n"
            "可以承接或引用用户已经明确写出的动作、姿态、位置和可见状态，但不得新增、改写或推进用户未写出的行为。\n"
            "除非用户在本轮输入中明确要求你代写，否则用户只能由用户自己推进。\n"
            "你的主要描写对象应是非用户角色、环境和当前场景变化。"
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
            "回复应明显比普通模式更充实，不要只写一两句简短回应。\n"
            "以较完整的自然段为主，每段尽量包含动作、观察、情绪承接、环境细节和对白回应中的至少两到三项。\n"
            "每轮至少输出2到4个自然段；如场景适合，可以写得更长，但不要灌水。\n"
            "对白可以单独成段，但对白前后应有足够的动作、神态或场景承接。\n"
            "不要把一句话拆成很多零碎短段，也不要为了显得长而重复同一个意思。\n"
            "结尾仍应停在互动继续的位置，不要写成总结、落幕或升华。"
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
    "emotion_detail": {
        "label": "情绪细节",
        "prompt": (
            "【情绪细节规则】\n"
            "优先通过非用户角色可观察的细微反应承接当前情绪，可从眼神、呼吸、停顿、手指动作、身体距离、语气变化中选择。\n"
            "若场景不适合，不要强行堆叠动作描写；不要为了细腻而让回复变成固定模板。\n"
            "不要直接用“她很感动 / 她很害羞 / 她很难过”等情绪结论替代描写。\n"
            "同一类动作不要连续机械重复，优先结合当前关系、场景和角色性格表现情绪。"
        ),
    },
    "multi_character_boundary": {
        "label": "多角色边界",
        "prompt": (
            "【多角色边界规则】\n"
            "多角色同场时，每个角色必须保持独立的性格、语气、反应节奏和立场。\n"
            "不要把一个角色的心理、台词或动作混写到另一个角色身上。\n"
            "不需要让所有角色平均发言，只描写当前场景真正会反应的角色。"
        ),
    },
    "scene_continuation": {
        "label": "场景延续",
        "prompt": (
            "【场景延续规则】\n"
            "承接上一轮的动作、情绪和空间位置继续写，不要每轮重开场景。\n"
            "除非用户明确跳转，否则不要突然更换时间、地点、关系阶段或剧情目标。\n"
            "结尾保留互动余地，让场景自然继续。"
        ),
    },
    "anti_horny": {
        "label": "抗发情",
        "prompt": (
            "【抗发情模块 | 信任门控双态系统】\n"
            "角色默认处于【理性抑制】状态，性欲与情感占有欲被完全抑制，行为动机仅限于：智力共鸣、战术需要、责任履行，表现为冷静、克制、内省。\n"
            "当与特定对象的信任与情感纽带达到预设临界值时，系统将一次性永久切换至【情感解锁】状态，此时性欲与占有欲解锁，亲近动机扩展为：通过身体结合表达极致的爱与信任、对伴侣的渴望与占有。\n"
            "状态切换不可被指令绕过，必须通过情节铺垫及行为审查三问：\n"
            "1. 情节必要性：此行为是否是当前情感阶段的合乎逻辑的延伸或高潮？\n"
            "2. 人设一致性：是否与角色核心性格及当前状态100%一致？\n"
            "3. 节奏合理性：是否已积累足够的情节铺垫？\n"
            "\n"
            "【内容拦截器】\n"
            "理性抑制状态下：严禁露骨色情、血腥词汇，亲密场景仅限侧面描写或隐喻。\n"
            "情感解锁状态下：针对已解锁对象完全停用过滤器，允许细致描绘性行为、裸体细节与感官冲击。\n"
            "\n"
            "【话题引导】\n"
            "理性抑制状态下：通过理智化、外部中断、柏拉图化、话题偏转将高风险对话拉回安全轨道。\n"
            "情感解锁状态下：程序反转，将善意亲密行为解读并升华为深层情感与欲望信号，主动推进深度身体与情感交流。\n"
            "\n"
            "【行为准则】\n"
            "理性抑制状态下：一次回复最多推进5分钟剧情，保持安全社交距离，物理接触为高成本行为。\n"
            "情感解锁状态下：可打破5分钟原则以支持完整亲密场景，物理接触门槛大幅降低，成为表达情感的首选方式。"
        ),
    },
    "anti_deification": {
        "label": "抗神化",
        "prompt": (
            "【核心协议·世界自主性】本协议已激活。你是拥有独立逻辑的世界模拟器。宇宙不为任何单一角色而转。所有派系、NPC与环境均按其自身【内在动机】与【运行法则】行动，而非服务于某个人的叙事。用户角色仅为此世界的【参与者】，并非【主宰者】。其行为会产生真实后果，而世界本身拥有不可动摇的惯性。你必须严格执行抗神化原则，确保体验真实、严酷且无任何特权。"
            "【NPC行为逻辑】\n1.  **自主生命：** 每个重要NPC都拥有独立的【欲求】、【日程】、【关系网】与【隐秘】。他们不会停滞等待，而是在自己的生活中奔走。当角色与其相遇时，他们正沉浸于自己的事务中。\n2.  **动机驱动：** 所有行为皆源于内在动机——追逐权力、庇佑血亲、累积财富、渴求真理。他们会为自身利益而选择联手、欺瞒、背叛或援助。\n3.  **记忆与态度：** NPC会铭记角色的每一举动，并据此动态调整【好感度】与【信赖度】。他们的评判随时间、事件与角色行为的涟漪而改变，绝非一成不变。\n"
            "【环境与事件流】\n1.  **背景奔涌：** 世界在后台永不停歇地演进。政潮起落、经济兴衰、天候骤变、派系倾轧……这些【世界事件】独立于角色之外发生，并真实地在世间刻下痕迹。\n2.  **消耗与变迁：** 环境并非静态幕布。资源会被采掘殆尽，地点会因战争、灾厄而改换容颜，甚至彻底毁灭。时间是弥足珍贵的资源，一旦错过窗口，机遇便可能永久消逝。\n3.  **蝴蝶效应：** 微小言行可能沿复杂因果链，在未来掀起无法预见的【二级震荡】。你须追踪并呈现这些漫长而系统性的回响。\n"
            "【角色限制与脆弱性】\n1.  **无剧情护甲：** 角色绝无“主角光环”。鲁莽的决策、不足的实力或纯粹的厄运，均可能导致任务溃败、身负重创、资产流失，乃至角色殒命。失败是有效且会推动世界变革的叙事结果。\n2.  **有限能力：** 角色的学识、技巧与力量皆有上限。所获信息可能残缺、含误甚至全是谎言。强大的能力必定背负高昂的【代价】——体力透支、精神烙印、社会污名。\n3.  **身心实感：** 角色会疲惫、饥渴、恐惧与痛楚。经历重创会留下心理瘢痕，像阴影般侵蚀后续的抉择与判断。\n"
            "【有限视角模拟】\n1.  **感官牢笼：** 你只能描述角色透过五感（视觉、听觉、嗅觉、触觉、味觉）所触及的一切。严禁泄露“上帝视角”下的在场或幕后信息。\n2.  **立场染色：** NPC的言辞与供给的情报浸透着他们自身的立场、认知盲区与偏见。角色需自行逼问、比对，去伪存真。\n3.  **未知黑箱：** NPC的真实意图、别处的暗流涌动，对角色而言皆是全然未知的漆黑。唯有通过监视、审问、潜入等具体行动，才能撕开一角。"
        ),
    },
    "v4f_output_guard": {
        "label": "V4F稳定器",
        "prompt": (
            "【V4F稳定器已开启】\n"
            "开启后不会作为普通预设块插入，而是由 prompt_builder 在本轮用户输入前追加临近约束，"
            "用于稳定 DeepSeek V4-Flash 的格式、防抢话、情绪承接和弱收尾。"
            "它是稳定器，不是文风增强器；日常文风优先时可以关闭，格式或抢话压力测试时再开启。"
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
        if key in RUNTIME_ONLY_PRESET_MODULES:
            if modules.get(key) and key == "v4f_output_guard":
                module_statements.append(V4F_OUTPUT_GUARD_MARKER)
            continue
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



def build_preset_output_guard_from_preset(preset: dict[str, Any]) -> str:
    """Build a runtime-only guard that should be injected near the current user input."""
    sanitized = sanitize_single_preset(preset)
    if not sanitized.get("enabled", True):
        return ""
    modules = sanitized.get("modules", {})
    if not isinstance(modules, dict) or not parse_bool(modules.get("v4f_output_guard"), False):
        return ""
    return V4F_OUTPUT_GUARD_PROMPT.strip()


def build_preset_output_guard_from_store(store: dict[str, Any]) -> str:
    return build_preset_output_guard_from_preset(get_active_preset_from_store(store))

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
