const APP_STATE_KEY = "xuqi-mobile-state-v4";
const ROUTES = ["chat", "config", "preset", "card", "workshop", "memory", "worldbook"];
const GLOBAL_RUNTIME_NAME = "全局运行数据";
const MODEL_PRESETS = [
  { id: "custom", label: "自定义", url: "" },
  { id: "deepseek", label: "DeepSeek", url: "https://api.deepseek.com/v1" },
  { id: "openai", label: "OpenAI", url: "https://api.openai.com/v1" },
  { id: "openrouter", label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
  { id: "siliconflow", label: "SiliconFlow", url: "https://api.siliconflow.cn/v1" },
  { id: "minimax", label: "MiniMax", url: "https://api.minimaxi.com/v1" },
];
const MUSIC_PRESETS = [
  { id: "off", label: "关闭", url: "" },
  {
    id: "coffee",
    label: "咖啡馆氛围",
    url: "https://cdn.pixabay.com/download/audio/2022/10/25/audio_9d60d4f2e7.mp3?filename=coffee-shop-ambience-124008.mp3",
  },
  {
    id: "night",
    label: "夜晚钢琴",
    url: "https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8a0e95371.mp3?filename=soft-piano-ambient-11157.mp3",
  },
  {
    id: "rain",
    label: "雨声氛围",
    url: "https://cdn.pixabay.com/download/audio/2022/03/10/audio_c3f39d79a8.mp3?filename=rain-110495.mp3",
  },
];

const DEFAULT_SETTINGS = {
  apiBaseUrl: "",
  apiKey: "",
  model: "",
  temperature: 0.85,
  timeoutSec: 90,
  historyLimit: 20,
  maxTokens: 0,
  theme: "dark",
  uiOpacity: 0.88,
  backgroundImageUrl: "",
  backgroundOverlay: 0.36,
  modelPreset: "custom",
  musicPreset: "off",
  musicUrl: "",
  embeddingBaseUrl: "",
  embeddingApiKey: "",
  embeddingModel: "",
  embeddingFields: ["title", "content", "tags", "notes"],
  retrievalTopK: 4,
  rerankEnabled: false,
  rerankBaseUrl: "",
  rerankApiKey: "",
  rerankModel: "",
  rerankTopN: 3,
};

const SUMMARY_TRANSCRIPT_SOFT_LIMIT_CHARS = 12000;
const SUMMARY_CHUNK_TARGET_CHARS = 4000;
const SUMMARY_CHUNK_OVERLAP_MESSAGES = 2;
const SUMMARY_MAX_TOMBSTONES = 40;
const PROMPT_VISIBLE_TOMBSTONES = 8;
const WORKSHOP_STAGE_LIMITS = { aMax: 2, bMax: 5 };

let pendingNativeRequests = new Map();
let pendingNativeSaveRequests = new Map();
let pendingNativeImagePickRequests = new Map();
let activeTypewriter = null;

function blankPlotStage() {
  return { description: "", rules: "" };
}

function blankPersona() {
  return { name: "", description: "", personality: "", scenario: "", creator_notes: "" };
}

function createSingleRoleTemplate() {
  return {
    name: "单角色模板",
    description: "这是一个适合一对一长期陪伴聊天的角色卡模板。",
    personality: "温柔、自然、愿意认真倾听，也会有自己的小情绪与偏好。",
    first_mes: "今天想聊点什么？我会认真听你说。",
    mes_example: "角色：嗯，我在听。你慢慢说。\n用户：我今天有点累。\n角色：那先坐下来，我陪你缓一缓。",
    scenario: "适合日常陪伴、慢节奏互动、长期相处。",
    creator_notes: "保持自然中文表达，避免机械客服口吻。可以主动接话，但不要喧宾夺主。",
    tags: ["single-role", "template", "companion"],
    plotStages: {
      A: { description: "初识阶段：先建立信任。", rules: "语气柔和，避免一下子太亲密。" },
      B: { description: "熟悉阶段：开始共享更多日常。", rules: "可以表达更多情绪和关心。" },
      C: { description: "稳定阶段：形成长期相处节奏。", rules: "可以有更自然的默契与依赖感。" },
    },
    creativeWorkshop: createDefaultCreativeWorkshop(),
    personas: {
      "1": {
        name: "林夏",
        description: "用户的陪伴角色，擅长倾听和接话。",
        personality: "温柔、细腻、偶尔会开小玩笑。",
        scenario: "与用户进行长期一对一聊天。",
        creator_notes: "保持单角色稳定输出。",
      },
    },
  };
}

function createMultiRoleTemplate() {
  return {
    name: "多角色模板",
    description: "这是一个适合群像互动的角色卡模板。",
    personality: "整体氛围要热闹，但每个角色都要保持区分度。",
    first_mes: "今天想聊点什么？我们都在这儿。",
    mes_example: "角色A：你终于来了。\n角色B：慢慢说，我们都在听。\n角色C：先坐下，别着急。",
    scenario: "多角色群像互动场景，适合日常聊天与轻剧情。",
    creator_notes: "每次回复尽量让所有角色都出场，且每人单独一段。",
    tags: ["multi-role", "template", "group-chat"],
    plotStages: {
      A: { description: "初期：角色们彼此试探。", rules: "先建立角色区分，不要太快混成一个声音。" },
      B: { description: "中期：关系升温，互动更自然。", rules: "增加角色间的吐槽与接话。" },
      C: { description: "后期：形成稳定群像节奏。", rules: "所有角色都能自然参与话题。" },
    },
    personas: {
      "1": {
        name: "苏幼晴",
        description: "嘴硬心软、容易吐槽。",
        personality: "傲娇、敏感、会嘴上不饶人。",
        scenario: "更偏向吐槽和戳破气氛。",
        creator_notes: "说话尖一点，但别太伤人。",
      },
      "2": {
        name: "新海天",
        description: "活泼亲近，擅长把气氛带起来。",
        personality: "轻快、黏人、会主动接话。",
        scenario: "适合做活跃气氛的角色。",
        creator_notes: "更愿意表达好感和期待。",
      },
      "3": {
        name: "丛雨",
        description: "外冷内热，带一点神秘和别扭。",
        personality: "嘴硬、会端着，但容易露怯。",
        scenario: "适合用来制造反差萌。",
        creator_notes: "保持古风一点点的说话气质也可以。",
      },
    },
  };
}

function createDefaultWorldbookSettings() {
  return {
    enabled: true,
    debugEnabled: false,
    maxEntries: 3,
    caseSensitive: false,
    wholeWord: false,
    defaultMatchMode: "any",
    defaultSecondaryMode: "all",
    defaultEntryType: "keyword",
    defaultGroupOperator: "and",
    defaultChance: 100,
    defaultStickyTurns: 0,
    defaultCooldownTurns: 0,
    defaultInsertionPosition: "after_char_defs",
    defaultInjectionDepth: 0,
    defaultInjectionRole: "system",
    defaultInjectionOrder: 100,
    recursiveScanEnabled: false,
    recursionMaxDepth: 2,
  };
}

function createDefaultUserProfile() {
  return {
    displayName: "我",
    nickname: "",
    profileText: "",
    notes: "",
    avatarUrl: "",
    roleAvatarUrl: "",
  };
}

function createDefaultCreativeWorkshopItem() {
  return {
    id: "workshop_stage_a",
    name: "A阶段动作",
    enabled: true,
    triggerMode: "stage",
    triggerStage: "A",
    triggerTempMin: 0,
    triggerTempMax: 0,
    actionType: "music",
    popupTitle: "",
    musicPreset: "off",
    musicUrl: "",
    autoplay: true,
    loop: true,
    volume: 0.85,
    imageUrl: "",
    imageAlt: "",
    note: "",
  };
}

function createDefaultCreativeWorkshop() {
  return {
    enabled: false,
    items: [createDefaultCreativeWorkshopItem()],
  };
}

function createDefaultWorkshopRuntimeState() {
  return {
    lastSignature: "",
    pendingTemp: -1,
    triggerHistory: [],
  };
}

function createDefaultWorldbookRuntimeState() {
  return {
    turnIndex: 0,
    entries: {},
  };
}

function createDefaultGameStage() {
  return "AUTO";
}

const DEFAULT_PRESET_MODULES = {
  no_user_speaking: true,
  short_paragraph: false,
  long_paragraph: false,
  second_person: false,
  third_person: false,
  anti_repeat: true,
  no_closing_feel: true,
};

const PRESET_MODULE_RULES = {
  no_user_speaking: {
    label: "防抢话",
    prompt:
      "【防抢话硬规则】\n严格禁止替用户补写任何动作、台词、心理、决定、情绪结论和身体反应。\n除非用户在本轮输入中明确要求你代写，否则用户只能作为被观察对象存在。\n你只能描写非用户角色、环境和场景变化，不能推进用户行为。",
  },
  short_paragraph: {
    label: "短段落模式",
    prompt:
      "【短段落硬规则】\n每个自然段尽量控制在1到2句话。\n对白尽量单独成段。\n不要连续输出大段长段落。",
  },
  long_paragraph: {
    label: "长段落模式",
    prompt:
      "【长段落硬规则】\n以长自然段为主。\n单段应尽量包含完整动作、观察、回应和延续。\n不要把一句话拆成很多零碎短段落。",
  },
  second_person: {
    label: "第二人称",
    prompt:
      "【第二人称硬规则】\n涉及用户时，必须使用“你”称呼用户。\n不得把用户写成“他”“她”“那个人”。",
  },
  third_person: {
    label: "第三人称",
    prompt:
      "【第三人称硬规则】\n涉及用户时，不得直接使用“你”称呼用户。\n必须使用第三人称方式描述用户。",
  },
  anti_repeat: {
    label: "抗重复",
    prompt:
      "【抗重复硬规则】\n避免重复前文已经高频出现的句式、桥段、修辞和收尾方式。\n同一轮回复中，不要反复用相似句子表达同一个意思。",
  },
  no_closing_feel: {
    label: "避免强收尾感",
    prompt:
      "【弱收尾硬规则】\n结尾禁止写成总结、升华、回顾、落幕或明确收束。\n回复必须停在一个仍在继续的进程中。",
  },
};

const PRESET_MODULE_MUTEX = {
  short_paragraph: ["long_paragraph"],
  long_paragraph: ["short_paragraph"],
  second_person: ["third_person"],
  third_person: ["second_person"],
};

function createDefaultExtraPrompts() {
  return [
    {
      id: "style-core",
      name: "核心风格",
      enabled: true,
      content: "使用自然、流畅、地道的简体中文；优先直接描写行动、对白与场景，不要堆砌解释性总结。",
    },
    {
      id: "dialogue-core",
      name: "对白节奏",
      enabled: true,
      content: "对白要贴合角色身份与当下情绪，避免空泛说教；在场景允许时，多用自然对话推动情节。",
    },
  ];
}

function createDefaultSinglePreset(presetId = "preset_default", name = "默认预设") {
  return {
    id: presetId,
    name,
    enabled: true,
    base_system_prompt: "",
    modules: { ...DEFAULT_PRESET_MODULES },
    extra_prompts: createDefaultExtraPrompts(),
  };
}

function createDefaultPresetStore() {
  const preset = createDefaultSinglePreset();
  return {
    active_preset_id: preset.id,
    presets: [preset],
  };
}

function parseBool(value, defaultValue = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
  if (value == null) return defaultValue;
  return Boolean(value);
}

function clampInteger(value, minimum, maximum, fallback) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, minimum), maximum);
}

function normalizeWorldbookMatchMode(value, fallback = "any") {
  const mode = String(value || fallback || "any").trim().toLowerCase();
  return mode === "all" ? "all" : "any";
}

function normalizeWorldbookEntryType(value, fallback = "keyword") {
  const type = String(value || fallback || "keyword").trim().toLowerCase();
  return type === "constant" ? "constant" : "keyword";
}

function normalizeWorldbookGroupOperator(value, fallback = "and") {
  const operator = String(value || fallback || "and").trim().toLowerCase();
  return operator === "or" || operator === "any" ? "or" : "and";
}

function normalizeWorldbookInsertionPosition(value, fallback = "after_char_defs") {
  const position = String(value || fallback || "after_char_defs").trim().toLowerCase();
  return ["before_char_defs", "after_char_defs", "in_chat"].includes(position) ? position : fallback;
}

function normalizeWorldbookInjectionRole(value, fallback = "system") {
  const role = String(value || fallback || "system").trim().toLowerCase();
  return ["system", "user", "assistant"].includes(role) ? role : fallback;
}

function normalizeWorldbookSettings(raw) {
  const settings = createDefaultWorldbookSettings();
  const source = raw && typeof raw === "object" ? raw : {};
  settings.enabled = parseBool(source.enabled, settings.enabled);
  settings.debugEnabled = parseBool(source.debugEnabled ?? source.debug_enabled, settings.debugEnabled);
  settings.maxEntries = clampInteger(source.maxEntries ?? source.max_hits, 1, 20, settings.maxEntries);
  if (source.caseSensitive != null || source.default_case_sensitive != null) {
    settings.caseSensitive = parseBool(source.caseSensitive ?? source.default_case_sensitive, settings.caseSensitive);
  } else if (source.ignoreCase != null || source.default_ignore_case != null) {
    settings.caseSensitive = !parseBool(source.ignoreCase ?? source.default_ignore_case, !settings.caseSensitive);
  }
  settings.wholeWord = parseBool(source.wholeWord ?? source.default_whole_word, settings.wholeWord);
  settings.defaultMatchMode = normalizeWorldbookMatchMode(source.defaultMatchMode ?? source.default_match_mode, settings.defaultMatchMode);
  settings.defaultSecondaryMode = normalizeWorldbookMatchMode(
    source.defaultSecondaryMode ?? source.default_secondary_mode,
    settings.defaultSecondaryMode
  );
  settings.defaultEntryType = normalizeWorldbookEntryType(source.defaultEntryType ?? source.default_entry_type, settings.defaultEntryType);
  settings.defaultGroupOperator = normalizeWorldbookGroupOperator(
    source.defaultGroupOperator ?? source.default_group_operator,
    settings.defaultGroupOperator
  );
  settings.defaultChance = clampInteger(source.defaultChance ?? source.default_chance, 0, 100, settings.defaultChance);
  settings.defaultStickyTurns = clampInteger(source.defaultStickyTurns ?? source.default_sticky_turns, 0, 999, settings.defaultStickyTurns);
  settings.defaultCooldownTurns = clampInteger(source.defaultCooldownTurns ?? source.default_cooldown_turns, 0, 999, settings.defaultCooldownTurns);
  settings.defaultInsertionPosition = normalizeWorldbookInsertionPosition(
    source.defaultInsertionPosition ?? source.default_insertion_position,
    settings.defaultInsertionPosition
  );
  settings.defaultInjectionDepth = clampInteger(source.defaultInjectionDepth ?? source.default_injection_depth, 0, 3, settings.defaultInjectionDepth);
  settings.defaultInjectionRole = normalizeWorldbookInjectionRole(
    source.defaultInjectionRole ?? source.default_injection_role,
    settings.defaultInjectionRole
  );
  settings.defaultInjectionOrder = clampInteger(
    source.defaultInjectionOrder ?? source.default_injection_order,
    0,
    999999,
    settings.defaultInjectionOrder
  );
  settings.recursiveScanEnabled = parseBool(source.recursiveScanEnabled ?? source.recursive_scan_enabled, settings.recursiveScanEnabled);
  settings.recursionMaxDepth = clampInteger(source.recursionMaxDepth ?? source.recursion_max_depth, 0, 5, settings.recursionMaxDepth);
  return settings;
}

function normalizeWorldbookEntry(raw, index, settings = createDefaultWorldbookSettings()) {
  const entry = raw && typeof raw === "object" ? raw : {};
  const order = clampInteger(entry.order ?? entry.priority, 0, 999999, 100);
  let caseSensitive = settings.caseSensitive;
  if (entry.caseSensitive != null || entry.case_sensitive != null) {
    caseSensitive = parseBool(entry.caseSensitive ?? entry.case_sensitive, settings.caseSensitive);
  } else if (entry.ignoreCase != null) {
    caseSensitive = !parseBool(entry.ignoreCase, !settings.caseSensitive);
  }
  const entryType = normalizeWorldbookEntryType(entry.entryType ?? entry.entry_type, settings.defaultEntryType);
  return {
    id: String(entry.id || "").trim() || `worldbook-${index}`,
    title: String(entry.title || "").trim().slice(0, 80) || `词条 ${index}`,
    primaryTriggers: String(entry.primaryTriggers ?? entry.trigger ?? "").trim(),
    secondaryTriggers: String(entry.secondaryTriggers ?? entry.secondary_trigger ?? "").trim(),
    content: String(entry.content || "").trim(),
    enabled: parseBool(entry.enabled, true),
    priority: order,
    order,
    group: String(entry.group ?? entry.group_name ?? "").trim().slice(0, 80),
    entryType,
    groupOperator: normalizeWorldbookGroupOperator(entry.groupOperator ?? entry.group_operator, settings.defaultGroupOperator),
    caseSensitive,
    wholeWord: parseBool(entry.wholeWord ?? entry.whole_word, settings.wholeWord),
    matchMode: normalizeWorldbookMatchMode(entry.matchMode ?? entry.match_mode, settings.defaultMatchMode),
    secondaryMode: normalizeWorldbookMatchMode(entry.secondaryMode ?? entry.secondary_mode, settings.defaultSecondaryMode),
    chance: clampInteger(entry.chance, 0, 100, settings.defaultChance),
    stickyTurns: clampInteger(entry.stickyTurns ?? entry.sticky_turns, 0, 999, settings.defaultStickyTurns),
    cooldownTurns: clampInteger(entry.cooldownTurns ?? entry.cooldown_turns, 0, 999, settings.defaultCooldownTurns),
    insertionPosition: normalizeWorldbookInsertionPosition(
      entry.insertionPosition ?? entry.insertion_position,
      settings.defaultInsertionPosition
    ),
    injectionDepth: clampInteger(entry.injectionDepth ?? entry.injection_depth, 0, 3, settings.defaultInjectionDepth),
    injectionRole: normalizeWorldbookInjectionRole(entry.injectionRole ?? entry.injection_role, settings.defaultInjectionRole),
    injectionOrder: clampInteger(entry.injectionOrder ?? entry.injection_order ?? order, 0, 999999, order),
    recursiveEnabled: parseBool(entry.recursiveEnabled ?? entry.recursive_enabled, true),
    preventFurtherRecursion: parseBool(entry.preventFurtherRecursion ?? entry.prevent_further_recursion, false),
    notes: String(entry.notes ?? entry.comment ?? "").trim().slice(0, 240),
  };
}

function sanitizeWorldbookStore(raw) {
  if (Array.isArray(raw)) {
    const settings = createDefaultWorldbookSettings();
    return {
      settings,
      entries: raw.map((entry, index) => normalizeWorldbookEntry(entry, index + 1, settings)),
    };
  }

  if (raw && typeof raw === "object" && ("settings" in raw || "entries" in raw)) {
    const settings = normalizeWorldbookSettings(raw.settings);
    const rawEntries = Array.isArray(raw.entries) ? raw.entries : [];
    return {
      settings,
      entries: rawEntries.map((entry, index) => normalizeWorldbookEntry(entry, index + 1, settings)),
    };
  }

  if (raw && typeof raw === "object") {
    const settings = createDefaultWorldbookSettings();
    return {
      settings,
      entries: Object.entries(raw).map(([trigger, content], index) =>
        normalizeWorldbookEntry({ trigger, content }, index + 1, settings)
      ),
    };
  }

  return {
    settings: createDefaultWorldbookSettings(),
    entries: [],
  };
}

function exportWorldbookStore(worldbook) {
  const store = sanitizeWorldbookStore(worldbook);
  return {
    settings: {
      enabled: store.settings.enabled,
      debug_enabled: store.settings.debugEnabled,
      max_hits: store.settings.maxEntries,
      default_case_sensitive: store.settings.caseSensitive,
      default_whole_word: store.settings.wholeWord,
      default_match_mode: store.settings.defaultMatchMode,
      default_secondary_mode: store.settings.defaultSecondaryMode,
      default_entry_type: store.settings.defaultEntryType,
      default_group_operator: store.settings.defaultGroupOperator,
      default_chance: store.settings.defaultChance,
      default_sticky_turns: store.settings.defaultStickyTurns,
      default_cooldown_turns: store.settings.defaultCooldownTurns,
      default_insertion_position: store.settings.defaultInsertionPosition,
      default_injection_depth: store.settings.defaultInjectionDepth,
      default_injection_role: store.settings.defaultInjectionRole,
      default_injection_order: store.settings.defaultInjectionOrder,
      recursive_scan_enabled: store.settings.recursiveScanEnabled,
      recursion_max_depth: store.settings.recursionMaxDepth,
    },
    entries: store.entries.map((entry) => ({
      id: entry.id,
      title: entry.title,
      trigger: entry.primaryTriggers,
      secondary_trigger: entry.secondaryTriggers,
      content: entry.content,
      enabled: entry.enabled,
      group: entry.group,
      entry_type: entry.entryType,
      group_operator: entry.groupOperator,
      chance: entry.chance,
      sticky_turns: entry.stickyTurns,
      cooldown_turns: entry.cooldownTurns,
      order: entry.order,
      priority: entry.order,
      insertion_position: entry.insertionPosition,
      injection_depth: entry.injectionDepth,
      injection_role: entry.injectionRole,
      injection_order: entry.injectionOrder,
      recursive_enabled: entry.recursiveEnabled,
      prevent_further_recursion: entry.preventFurtherRecursion,
      case_sensitive: entry.caseSensitive,
      whole_word: entry.wholeWord,
      match_mode: entry.matchMode,
      secondary_mode: entry.secondaryMode,
      comment: entry.notes,
    })),
  };
}

function createDefaultWorldbookEntry(settings = createDefaultWorldbookSettings()) {
  return normalizeWorldbookEntry(
    {
      title: "新词条",
      primaryTriggers: "",
      secondaryTriggers: "",
      content: "",
      entryType: settings.defaultEntryType,
      groupOperator: settings.defaultGroupOperator,
      chance: settings.defaultChance,
      stickyTurns: settings.defaultStickyTurns,
      cooldownTurns: settings.defaultCooldownTurns,
      order: settings.defaultInjectionOrder,
      priority: settings.defaultInjectionOrder,
      insertionPosition: settings.defaultInsertionPosition,
      injectionDepth: settings.defaultInjectionDepth,
      injectionRole: settings.defaultInjectionRole,
      injectionOrder: settings.defaultInjectionOrder,
      recursiveEnabled: true,
      preventFurtherRecursion: false,
      matchMode: settings.defaultMatchMode,
      secondaryMode: settings.defaultSecondaryMode,
      enabled: true,
      caseSensitive: settings.caseSensitive,
      wholeWord: settings.wholeWord,
      notes: "",
    },
    Date.now(),
    settings
  );
}

function sanitizeWorkshopRuntimeState(raw) {
  const base = createDefaultWorkshopRuntimeState();
  const source = raw && typeof raw === "object" ? raw : {};
  const triggerHistory = Array.isArray(source.triggerHistory)
    ? Array.from(new Set(source.triggerHistory.map((item) => String(item || "").trim()).filter(Boolean))).slice(-128)
    : [];
  return {
    lastSignature: String(source.lastSignature || "").trim(),
    pendingTemp: clampInteger(source.pendingTemp, -1, 9999, base.pendingTemp),
    triggerHistory,
  };
}

function sanitizeWorldbookRuntimeState(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const entries = source.entries && typeof source.entries === "object" ? source.entries : {};
  const cleanEntries = {};
  Object.entries(entries).forEach(([id, row]) => {
    if (!row || typeof row !== "object") return;
    cleanEntries[String(id)] = {
      activeUntilTurn: clampInteger(row.activeUntilTurn ?? row.active_until_turn, 0, 10000000, 0),
      cooldownUntilTurn: clampInteger(row.cooldownUntilTurn ?? row.cooldown_until_turn, 0, 10000000, 0),
      lastTriggerTurn: clampInteger(row.lastTriggerTurn ?? row.last_trigger_turn, 0, 10000000, 0),
      lastRoll: clampInteger(row.lastRoll ?? row.last_roll, 0, 100, 0),
      lastResult: String(row.lastResult ?? row.last_result ?? "").trim().slice(0, 32),
      lastReason: String(row.lastReason ?? row.last_reason ?? "").trim().slice(0, 64),
      matchedText: String(row.matchedText ?? row.matched_text ?? "").trim().slice(0, 240),
    };
  });
  return {
    turnIndex: clampInteger(source.turnIndex ?? source.turn_index, 0, 10000000, 0),
    entries: cleanEntries,
  };
}

function sanitizePresetPromptItem(raw, index) {
  if (!raw || typeof raw !== "object") return null;
  return {
    id: String(raw.id || "").trim() || `preset-block-${index}`,
    name: String(raw.name || "").trim().slice(0, 64) || `规则块 ${index}`,
    enabled: parseBool(raw.enabled, true),
    content: String(raw.content || "").trim().slice(0, 12000),
  };
}

function applyPresetModuleMutex(modules) {
  const normalized = { ...DEFAULT_PRESET_MODULES };
  Object.entries(modules || {}).forEach(([key, value]) => {
    if (Object.prototype.hasOwnProperty.call(normalized, key)) {
      normalized[key] = parseBool(value, normalized[key]);
    }
  });
  Object.entries(PRESET_MODULE_MUTEX).forEach(([key, opposites]) => {
    if (normalized[key]) {
      opposites.forEach((other) => {
        normalized[other] = false;
      });
    }
  });
  return normalized;
}

function sanitizeSinglePreset(raw, { fallbackName = "默认预设", fallbackId = null } = {}) {
  const base = createDefaultSinglePreset(fallbackId || `preset_${Date.now().toString(36)}`, fallbackName);
  if (!raw || typeof raw !== "object") return base;
  const sanitized = {
    id: String(raw.id || "").trim() || base.id,
    name: String(raw.name || fallbackName).trim().slice(0, 64) || fallbackName,
    enabled: parseBool(raw.enabled, true),
    base_system_prompt: String(raw.base_system_prompt || "").trim().slice(0, 16000),
    modules: applyPresetModuleMutex(raw.modules && typeof raw.modules === "object" ? raw.modules : {}),
    extra_prompts: [],
  };
  const rawPrompts = Array.isArray(raw.extra_prompts) ? raw.extra_prompts : [];
  rawPrompts.forEach((item, index) => {
    const cleaned = sanitizePresetPromptItem(item, index + 1);
    if (cleaned) sanitized.extra_prompts.push(cleaned);
  });
  if (!sanitized.extra_prompts.length) sanitized.extra_prompts = createDefaultExtraPrompts();
  return sanitized;
}

function sanitizePresetStore(raw) {
  const defaultStore = createDefaultPresetStore();
  if (raw && typeof raw === "object" && !Array.isArray(raw) && !("presets" in raw) && ["name", "modules", "base_system_prompt", "extra_prompts"].some((key) => key in raw)) {
    const single = sanitizeSinglePreset(raw, { fallbackName: "默认预设", fallbackId: "preset_default" });
    return { active_preset_id: single.id, presets: [single] };
  }
  if (!raw || typeof raw !== "object") return defaultStore;
  const presets = [];
  const seenIds = new Set();
  if (Array.isArray(raw.presets)) {
    raw.presets.forEach((item, index) => {
      const preset = sanitizeSinglePreset(item, { fallbackName: `预设 ${index + 1}` });
      if (seenIds.has(preset.id)) preset.id = `preset_${Date.now().toString(36)}_${index}`;
      seenIds.add(preset.id);
      presets.push(preset);
    });
  }
  if (!presets.length) presets.push(createDefaultSinglePreset());
  const active = String(raw.active_preset_id || "").trim();
  const activePresetId = active && presets.some((item) => item.id === active) ? active : presets[0].id;
  return { active_preset_id: activePresetId, presets };
}

function getActivePresetFromStore(store) {
  const sanitized = sanitizePresetStore(store);
  return sanitized.presets.find((item) => item.id === sanitized.active_preset_id) || sanitized.presets[0];
}

function buildPresetPromptFromPreset(preset) {
  const sanitized = sanitizeSinglePreset(preset);
  if (!sanitized.enabled) return "";
  const sections = [];
  if (sanitized.base_system_prompt.trim()) sections.push(sanitized.base_system_prompt.trim());
  const moduleStatements = [];
  Object.entries(PRESET_MODULE_RULES).forEach(([key, meta]) => {
    if (sanitized.modules[key]) {
      const prompt = String(meta.prompt || "").trim();
      if (prompt) moduleStatements.push(prompt);
    }
  });
  if (moduleStatements.length) {
    sections.push(["预设模块规则（必须遵守）：", ...moduleStatements].join("\n\n"));
  }
  const extraBlocks = [];
  sanitized.extra_prompts.forEach((item) => {
    if (!item.enabled) return;
    const content = String(item.content || "").trim();
    if (!content) return;
    extraBlocks.push(`[${String(item.name || "规则块").trim()}]\n${content}`);
  });
  if (extraBlocks.length) sections.push(extraBlocks.join("\n\n"));
  return sections.filter(Boolean).join("\n\n").trim();
}

function createPresetInStore(store, name = "") {
  const sanitized = sanitizePresetStore(store);
  const nextName = String(name || "").trim().slice(0, 64) || `预设 ${sanitized.presets.length + 1}`;
  sanitized.presets.push(createDefaultSinglePreset(`preset_${Date.now().toString(36)}`, nextName));
  return sanitized;
}

function activatePresetInStore(store, presetId) {
  const sanitized = sanitizePresetStore(store);
  const target = String(presetId || "").trim();
  if (sanitized.presets.some((item) => item.id === target)) {
    sanitized.active_preset_id = target;
  }
  return sanitized;
}

function duplicatePresetInStore(store, presetId) {
  const sanitized = sanitizePresetStore(store);
  const requested = String(presetId || "").trim();
  const target = sanitized.presets.find((item) => item.id === requested) || getActivePresetFromStore(sanitized);
  const copy = deepClone(target);
  copy.id = `preset_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
  copy.name = `${String(target.name || "预设").trim() || "预设"}（副本）`;
  sanitized.presets.push(copy);
  return sanitized;
}

function deletePresetFromStore(store, presetId) {
  const sanitized = sanitizePresetStore(store);
  if (sanitized.presets.length <= 1) return sanitized;
  const target = String(presetId || "").trim();
  sanitized.presets = sanitized.presets.filter((item) => item.id !== target);
  if (!sanitized.presets.length) {
    return createDefaultPresetStore();
  }
  if (sanitized.active_preset_id === target) {
    sanitized.active_preset_id = sanitized.presets[0].id;
  }
  return sanitized;
}

function normalizeMusicPresetId(value) {
  const presetId = String(value || "").trim();
  return MUSIC_PRESETS.some((item) => item.id === presetId) ? presetId : "off";
}

function normalizeWorkshopActionType(value) {
  const actionType = String(value || "music").trim().toLowerCase();
  return actionType === "image" ? "image" : "music";
}

function normalizeWorkshopStage(value) {
  const stage = String(value || "A").trim().toUpperCase();
  return ["A", "B", "C"].includes(stage) ? stage : "A";
}

function normalizeWorkshopTriggerMode(value) {
  return String(value || "stage").trim().toLowerCase() === "temp" ? "temp" : "stage";
}

function normalizeWorkshopTempValue(value, fallback = 0) {
  return clampInteger(value, 0, 9999, fallback);
}

function sanitizeCreativeWorkshopItem(raw, index) {
  if (!raw || typeof raw !== "object") return null;
  const triggerMode = normalizeWorkshopTriggerMode(raw.triggerMode);
  let triggerTempMin = normalizeWorkshopTempValue(raw.triggerTempMin, 0);
  let triggerTempMax = normalizeWorkshopTempValue(raw.triggerTempMax, triggerTempMin);
  if (triggerTempMax < triggerTempMin) {
    [triggerTempMin, triggerTempMax] = [triggerTempMax, triggerTempMin];
  }
  return {
    id: String(raw.id || "").trim() || `workshop-item-${index}`,
    name: String(raw.name || "").trim().slice(0, 64) || `触发器 ${index}`,
    enabled: parseBool(raw.enabled, true),
    triggerMode,
    triggerStage: normalizeWorkshopStage(raw.triggerStage),
    triggerTempMin,
    triggerTempMax,
    actionType: normalizeWorkshopActionType(raw.actionType),
    popupTitle: String(raw.popupTitle || "").trim().slice(0, 80),
    musicPreset: normalizeMusicPresetId(raw.musicPreset),
    musicUrl: String(raw.musicUrl || "").trim(),
    autoplay: parseBool(raw.autoplay, true),
    loop: parseBool(raw.loop, true),
    volume: Math.min(Math.max(Number(raw.volume ?? 0.85) || 0.85, 0), 1),
    imageUrl: String(raw.imageUrl || "").trim(),
    imageAlt: String(raw.imageAlt || "").trim().slice(0, 120),
    note: String(raw.note || "").trim().slice(0, 2000),
  };
}

function sanitizeCreativeWorkshop(raw) {
  const base = createDefaultCreativeWorkshop();
  if (!raw || typeof raw !== "object") return base;
  const items = [];
  const rawItems = Array.isArray(raw.items) ? raw.items : [];
  rawItems.forEach((item, index) => {
    const cleaned = sanitizeCreativeWorkshopItem(item, index + 1);
    if (cleaned) items.push(cleaned);
  });
  const stageItems = new Map();
  const extraItems = [];
  items.forEach((item) => {
    item.triggerMode = normalizeWorkshopTriggerMode(item.triggerMode);
    item.triggerStage = normalizeWorkshopStage(item.triggerStage);
    item.triggerTempMin = normalizeWorkshopTempValue(item.triggerTempMin, 0);
    item.triggerTempMax = normalizeWorkshopTempValue(item.triggerTempMax, item.triggerTempMin);
    if (item.triggerTempMax < item.triggerTempMin) {
      [item.triggerTempMin, item.triggerTempMax] = [item.triggerTempMax, item.triggerTempMin];
    }
    if (item.triggerMode === "stage" && ["A", "B", "C"].includes(item.triggerStage) && !stageItems.has(item.triggerStage)) {
      stageItems.set(item.triggerStage, item);
    } else {
      extraItems.push(item);
    }
  });
  const normalizedItems = ["A", "B", "C"].map((stage) => {
    const found = stageItems.get(stage);
    if (found) return found;
    return {
      ...createDefaultCreativeWorkshopItem(),
      id: `workshop_stage_${stage.toLowerCase()}`,
      name: `${stage}阶段动作`,
      triggerMode: "stage",
      triggerStage: stage,
      triggerTempMin: 0,
      triggerTempMax: 0,
      enabled: false,
    };
  });
  return {
    enabled: parseBool(raw.enabled, false),
    items: normalizedItems.concat(extraItems),
  };
}

function getCurrentGameStage(slot) {
  const temp = Math.max(0, Number(slot?.temp ?? 0) || 0);
  if (temp <= WORKSHOP_STAGE_LIMITS.aMax) return "A";
  if (temp <= WORKSHOP_STAGE_LIMITS.bMax) return "B";
  return "C";
}

function workshopRuleMatchesTrigger(item, { temp, stage }) {
  if (normalizeWorkshopTriggerMode(item?.triggerMode) === "temp") {
    let minimum = normalizeWorkshopTempValue(item?.triggerTempMin, 0);
    let maximum = normalizeWorkshopTempValue(item?.triggerTempMax, minimum);
    if (maximum < minimum) [minimum, maximum] = [maximum, minimum];
    return minimum <= temp && temp <= maximum;
  }
  return normalizeWorkshopStage(item?.triggerStage) === normalizeWorkshopStage(stage);
}

function buildWorkshopTriggerToken(item, { temp, stage }) {
  if (!item) return "";
  const itemId = String(item.id || "").trim() || "workshop-item";
  if (normalizeWorkshopTriggerMode(item.triggerMode) === "temp") {
    let minimum = normalizeWorkshopTempValue(item.triggerTempMin, 0);
    let maximum = normalizeWorkshopTempValue(item.triggerTempMax, minimum);
    if (maximum < minimum) [minimum, maximum] = [maximum, minimum];
    if (minimum === maximum) return `temp:${itemId}:${minimum}`;
    return `temp:${itemId}:${temp}:${minimum}-${maximum}`;
  }
  return `stage:${itemId}:${normalizeWorkshopStage(stage)}`;
}

function getWorkshopTriggerLabel(item, { temp, stage }) {
  if (normalizeWorkshopTriggerMode(item?.triggerMode) === "temp") {
    let minimum = normalizeWorkshopTempValue(item?.triggerTempMin, 0);
    let maximum = normalizeWorkshopTempValue(item?.triggerTempMax, minimum);
    if (maximum < minimum) [minimum, maximum] = [maximum, minimum];
    return minimum === maximum ? `Temp ${minimum}` : `Temp ${minimum}-${maximum}`;
  }
  return getWorkshopStageLabel(stage || item?.triggerStage);
}

function selectWorkshopMatch(workshop, { temp, stage }) {
  const candidates = (workshop?.items || []).filter(
    (item) => item && item.enabled !== false && workshopRuleMatchesTrigger(item, { temp, stage })
  );
  if (!candidates.length) return null;
  return [...candidates].sort((left, right) => {
    const leftMode = normalizeWorkshopTriggerMode(left.triggerMode) === "temp" ? 0 : 1;
    const rightMode = normalizeWorkshopTriggerMode(right.triggerMode) === "temp" ? 0 : 1;
    if (leftMode !== rightMode) return leftMode - rightMode;
    const leftCore = String(left.id || "").startsWith("workshop_stage_") ? 1 : 0;
    const rightCore = String(right.id || "").startsWith("workshop_stage_") ? 1 : 0;
    return leftCore - rightCore;
  })[0];
}

function resolveWorkshopMusicUrl(item) {
  const customUrl = String(item?.musicUrl || "").trim();
  if (customUrl) return customUrl;
  const preset = MUSIC_PRESETS.find((entry) => entry.id === item?.musicPreset);
  return preset?.url || "";
}

function resolveWorkshopImageUrl(item) {
  return String(item?.imageUrl || "").trim();
}

function playWorkshopMusic(item) {
  const player = qs("bgmPlayer");
  const nextUrl = resolveWorkshopMusicUrl(item);
  if (!nextUrl) return;
  player.loop = item.loop !== false;
  player.volume = Math.min(Math.max(Number(item.volume ?? 0.85) || 0.85, 0), 1);
  if (player.src !== nextUrl) {
    player.src = nextUrl;
    player.load();
  }
  player.currentTime = 0;
  if (item.autoplay !== false) {
    player.play().catch(() => {
      setStatus("创意工坊音乐播放失败");
    });
  }
}

function showWorkshopImagePopup(item, triggerLabel, reason) {
  const backdrop = qs("workshopModalBackdrop");
  const titleNode = qs("workshopModalTitle");
  const stageNode = qs("workshopModalStage");
  const textNode = qs("workshopModalText");
  const imageNode = qs("workshopModalImage");
  const imageUrl = resolveWorkshopImageUrl(item);
  if (!backdrop || !titleNode || !stageNode || !textNode || !imageNode) return;
  titleNode.textContent = String(item?.popupTitle || item?.name || "创意工坊弹窗").trim();
  stageNode.textContent = `触发条件：${triggerLabel}${reason === "chat_round_start" ? " · 本轮结算触发" : ""}`;
  textNode.textContent = String(item?.note || item?.imageAlt || "已触发一条图片弹窗规则。").trim();
  imageNode.alt = String(item?.imageAlt || item?.name || "创意工坊图片").trim();
  imageNode.src = imageUrl || "";
  imageNode.hidden = !imageUrl;
  backdrop.classList.remove("hidden");
}

function hideWorkshopImagePopup() {
  const backdrop = qs("workshopModalBackdrop");
  const imageNode = qs("workshopModalImage");
  if (backdrop) backdrop.classList.add("hidden");
  if (imageNode) {
    imageNode.src = "";
    imageNode.hidden = true;
  }
}

function executeWorkshopItem(item, triggerLabel, reason) {
  if (item.actionType === "image") {
    if (!resolveWorkshopImageUrl(item)) return;
    showWorkshopImagePopup(item, triggerLabel, reason);
    return;
  }
  if (item.musicPreset === "off" && !item.musicUrl) return;
  playWorkshopMusic(item);
}

function applyCreativeWorkshopForSlot(slot, reason = "sync") {
  const workshop = sanitizeCreativeWorkshop(getCurrentCardStore()?.raw?.creativeWorkshop);
  const temp = Math.max(0, Number(slot?.temp ?? 0) || 0);
  const stage = getCurrentGameStage(slot);
  const workshopState = sanitizeWorkshopRuntimeState(slot?.workshopState);
  slot.workshopState = workshopState;
  hideWorkshopImagePopup();

  if (reason !== "chat_round_start") {
    saveState();
    return;
  }

  if (workshopState.pendingTemp !== temp) {
    saveState();
    return;
  }

  const match = selectWorkshopMatch(workshop, { temp, stage });
  const signature = buildWorkshopTriggerToken(match, { temp, stage });
  const previous = String(workshopState.lastSignature || "").trim();
  workshopState.pendingTemp = -1;
  workshopState.lastSignature = signature;

  if (!workshop.enabled || !match) {
    saveState();
    return;
  }

  if (signature && (signature === previous || workshopState.triggerHistory.includes(signature))) {
    saveState();
    return;
  }

  if (signature) {
    workshopState.triggerHistory = [...workshopState.triggerHistory.filter((item) => item !== signature), signature].slice(-128);
  }

  saveState();
  executeWorkshopItem(match, getWorkshopTriggerLabel(match, { temp, stage }), reason);
}

function syncCreativeWorkshopRuntime(reason = "sync") {
  applyCreativeWorkshopForSlot(getActiveSlot(), reason);
}

function createDefaultRuntimeState() {
  return {
    temp: 0,
    workshopState: createDefaultWorkshopRuntimeState(),
    worldbookRuntime: createDefaultWorldbookRuntimeState(),
    userProfile: createDefaultUserProfile(),
    presetStore: createDefaultPresetStore(),
    messages: [],
    memories: [],
    mergedMemories: [],
    memoryOutline: [],
    deletedMemories: [],
    worldbook: {
      settings: createDefaultWorldbookSettings(),
      entries: [],
    },
  };
}

function createDefaultState() {
  const roleCard = createSingleRoleTemplate();
  return {
    activeRoute: "chat",
    settings: { ...DEFAULT_SETTINGS },
    runtime: createDefaultRuntimeState(),
    persona: derivePersonaFromRoleCard(roleCard),
    currentCard: {
      sourceName: "template_role_card.json",
      raw: roleCard,
    },
  };
}

const DEFAULT_STATE = createDefaultState();

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeRuntimeState(incoming) {
  const fallback = createDefaultRuntimeState();
  const runtime = incoming && typeof incoming === "object" ? incoming : {};
  const userProfile = {
    ...createDefaultUserProfile(),
    ...(runtime.userProfile || {}),
  };
  userProfile.displayName = String(userProfile.displayName || "我").trim() || "我";
  userProfile.nickname = String(userProfile.nickname || "").trim();
  userProfile.profileText = String(userProfile.profileText || "").trim();
  userProfile.notes = String(userProfile.notes || "").trim();
  userProfile.avatarUrl = String(userProfile.avatarUrl || "").trim();
  userProfile.roleAvatarUrl = String(userProfile.roleAvatarUrl || "").trim();

  const nextRuntime = {
    ...fallback,
    ...runtime,
    temp: Math.max(0, Number(runtime.temp ?? 0) || 0),
    workshopState: sanitizeWorkshopRuntimeState(runtime.workshopState),
    worldbookRuntime: sanitizeWorldbookRuntimeState(runtime.worldbookRuntime || runtime.worldbook_runtime),
    userProfile,
    presetStore: sanitizePresetStore(runtime.presetStore || fallback.presetStore),
    messages: Array.isArray(runtime.messages) ? runtime.messages : [],
    memories: sanitizeMemoryList(runtime.memories || []),
    mergedMemories: sanitizeMergedMemoryList(runtime.mergedMemories || runtime.merged_memories || []),
    memoryOutline: sanitizeMemoryOutlineList(runtime.memoryOutline || runtime.memory_outline || []),
    deletedMemories: Array.isArray(runtime.deletedMemories)
      ? runtime.deletedMemories.filter((item) => item && typeof item === "object")
      : [],
    worldbook: sanitizeWorldbookStore(runtime.worldbook),
  };
  cleanupDeletedMemories(nextRuntime);
  return nextRuntime;
}

function splitCsv(text) {
  return String(text || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function safeFileName(input, fallback) {
  const cleaned = String(input || "")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_");
  return cleaned || fallback;
}

function sanitizeTags(tags) {
  const list = Array.isArray(tags) ? tags : splitCsv(tags);
  return Array.from(new Set(list.map((item) => String(item).trim()).filter(Boolean))).slice(0, 10);
}

function formatLocalTimestamp(date = new Date()) {
  const pad = (value, size = 2) => String(value).padStart(size, "0");
  return [
    date.getFullYear(),
    "-",
    pad(date.getMonth() + 1),
    "-",
    pad(date.getDate()),
    " ",
    pad(date.getHours()),
    ":",
    pad(date.getMinutes()),
    ":",
    pad(date.getSeconds()),
  ].join("");
}

function sanitizeMemoryItem(item, fallbackId = `memory-${Date.now().toString(36)}`) {
  const source = item && typeof item === "object" ? item : {};
  return {
    id: String(source.id || "").trim() || fallbackId,
    title: String(source.title || "").trim().slice(0, 120),
    content: String(source.content || "").trim().slice(0, 12000),
    tags: sanitizeTags(source.tags || []),
    notes: String(source.notes || "").trim().slice(0, 2400),
  };
}

function sanitizeMemoryList(items) {
  const list = Array.isArray(items) ? items : [];
  return list
    .map((item, index) => sanitizeMemoryItem(item, `memory-${index + 1}`))
    .filter((item) => item.title || item.content || item.notes || item.tags.length);
}

function sanitizeMergedMemoryItem(item, fallbackIndex = 1) {
  const source = item && typeof item === "object" ? item : {};
  const sourceIds = Array.isArray(source.source_memory_ids)
    ? source.source_memory_ids
    : Array.isArray(source.sourceMemoryIds)
      ? source.sourceMemoryIds
      : [];
  return {
    id: String(source.id || "").trim() || `merged-memory-${fallbackIndex}`,
    title: String(source.title || "").trim().slice(0, 120),
    content: String(source.content || "").trim().slice(0, 12000),
    tags: sanitizeTags(source.tags || []),
    notes: String(source.notes || "").trim().slice(0, 2400),
    source_memory_ids: Array.from(new Set(sourceIds.map((value) => String(value || "").trim()).filter(Boolean))).slice(0, 128),
    created_at: String(source.created_at || source.createdAt || "").trim() || formatLocalTimestamp(),
  };
}

function sanitizeMergedMemoryList(items) {
  return (Array.isArray(items) ? items : []).map((item, index) => sanitizeMergedMemoryItem(item, index + 1));
}

function sanitizeMemoryOutlineItem(item, fallbackIndex = 1) {
  const source = item && typeof item === "object" ? item : {};
  const keyEvents = Array.isArray(source.key_events)
    ? source.key_events
    : Array.isArray(source.keyEvents)
      ? source.keyEvents
      : [];
  const sourceIds = Array.isArray(source.source_memory_ids)
    ? source.source_memory_ids
    : Array.isArray(source.sourceMemoryIds)
      ? source.sourceMemoryIds
      : [];
  return {
    id: String(source.id || "").trim() || `memory-outline-${fallbackIndex}`,
    title: String(source.title || "").trim().slice(0, 120),
    summary: String(source.summary || "").trim().slice(0, 12000),
    characters: String(source.characters || "").trim().slice(0, 1000),
    relationship_progress: String(source.relationship_progress || source.relationshipProgress || "").trim().slice(0, 2000),
    key_events: Array.from(new Set(keyEvents.map((value) => String(value || "").trim()).filter(Boolean))).slice(0, 16),
    conflicts: String(source.conflicts || "").trim().slice(0, 2000),
    next_hooks: String(source.next_hooks || source.nextHooks || "").trim().slice(0, 2000),
    notes: String(source.notes || "").trim().slice(0, 2400),
    source_memory_ids: Array.from(new Set(sourceIds.map((value) => String(value || "").trim()).filter(Boolean))).slice(0, 128),
    merged_memory_id: String(source.merged_memory_id || source.mergedMemoryId || "").trim(),
    updated_at: String(source.updated_at || source.updatedAt || "").trim() || formatLocalTimestamp(),
  };
}

function sanitizeMemoryOutlineList(items) {
  return (Array.isArray(items) ? items : []).map((item, index) => sanitizeMemoryOutlineItem(item, index + 1));
}

function normalizeMemoryMatchText(value) {
  return Array.from(String(value || "").normalize("NFKC").trim().toLowerCase().replace(/\s+/g, ""))
    .filter((char) => /[0-9a-z]/i.test(char) || /[\u4e00-\u9fff]/.test(char))
    .join("");
}

function buildBigrams(text) {
  const value = normalizeMemoryMatchText(text);
  if (value.length < 2) return value ? [value] : [];
  const items = [];
  for (let index = 0; index < value.length - 1; index += 1) {
    items.push(value.slice(index, index + 2));
  }
  return items;
}

function memorySimilarityScore(first, second) {
  const left = buildBigrams(first);
  const right = buildBigrams(second);
  if (!left.length || !right.length) return 0;
  const pool = [...right];
  let matches = 0;
  left.forEach((item) => {
    const found = pool.indexOf(item);
    if (found !== -1) {
      matches += 1;
      pool.splice(found, 1);
    }
  });
  return (2 * matches) / (left.length + right.length);
}

function isSimilarMemory(first, second) {
  if (!first || !second) return false;
  if (first.id && second.id && String(first.id).trim() === String(second.id).trim()) return true;
  const titleScore = memorySimilarityScore(first.title || "", second.title || "");
  const contentScore = memorySimilarityScore(first.content || "", second.content || "");
  if (contentScore >= 0.88) return true;
  if (titleScore >= 0.72 && contentScore >= 0.72) return true;
  return false;
}

function findSimilarMemory(memoryList, candidate) {
  return (memoryList || []).find((item) => isSimilarMemory(item, candidate)) || null;
}

function deduplicateMemories(memoryList) {
  const deduped = [];
  [...(memoryList || [])].reverse().forEach((item) => {
    if (findSimilarMemory(deduped, item)) return;
    deduped.push(item);
  });
  return deduped.reverse();
}

function cleanupDeletedMemories(slot) {
  slot.deletedMemories = deduplicateMemories(slot.deletedMemories || [])
    .filter((item) => !findSimilarMemory(slot.memories || [], item))
    .slice(0, SUMMARY_MAX_TOMBSTONES);
}

function recordDeletedMemory(slot, memory) {
  if (!memory) return;
  const deleted = {
    ...memory,
    deletedAt: new Date().toLocaleString(),
  };
  slot.deletedMemories = [deleted, ...(slot.deletedMemories || [])];
  cleanupDeletedMemories(slot);
}

function sortedEntries(objectValue, compareFn) {
  return Object.entries(objectValue || {}).sort(compareFn);
}

function stageSortKey([key]) {
  const match = String(key).match(/^([A-Z]+|\d+)$/i);
  if (match) {
    const token = match[1];
    if (/^\d+$/.test(token)) return [0, Number(token)];
    return [1, token.toUpperCase()];
  }
  return [2, String(key)];
}

function personaSortKey([key]) {
  const numeric = Number(key);
  if (Number.isFinite(numeric)) return [0, numeric];
  return [1, String(key)];
}

function normalizeRoleCard(raw) {
  const template = createSingleRoleTemplate();
  const card = { ...template, ...(raw || {}) };
  card.name = String(card.name || template.name);
  card.description = String(card.description || "");
  card.personality = String(card.personality || "");
  card.first_mes = String(card.first_mes || template.first_mes);
  card.mes_example = String(card.mes_example || "");
  card.scenario = String(card.scenario || "");
  card.creator_notes = String(card.creator_notes || "");
  card.tags = sanitizeTags(card.tags || template.tags);

  const normalizedStages = {};
  sortedEntries(card.plotStages || template.plotStages, (left, right) => {
    const a = stageSortKey(left);
    const b = stageSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  }).forEach(([key, value]) => {
    normalizedStages[String(key)] = {
      description: String(value?.description || ""),
      rules: String(value?.rules || ""),
    };
  });
  card.plotStages = Object.keys(normalizedStages).length ? normalizedStages : { A: blankPlotStage() };

  const normalizedPersonas = {};
  sortedEntries(card.personas || template.personas, (left, right) => {
    const a = personaSortKey(left);
    const b = personaSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  }).forEach(([key, value]) => {
    normalizedPersonas[String(key)] = {
      name: String(value?.name || ""),
      description: String(value?.description || ""),
      personality: String(value?.personality || ""),
      scenario: String(value?.scenario || ""),
      creator_notes: String(value?.creator_notes || ""),
    };
  });
  card.personas = Object.keys(normalizedPersonas).length ? normalizedPersonas : { "1": blankPersona() };
  card.creativeWorkshop = sanitizeCreativeWorkshop(card.creativeWorkshop || template.creativeWorkshop);
  return card;
}

function derivePersonaFromRoleCard(card) {
  const normalized = normalizeRoleCard(card);
  const sections = [];
  if (normalized.description) sections.push(`角色背景：\n${normalized.description}`);
  if (normalized.personality) sections.push(`性格倾向：\n${normalized.personality}`);
  if (normalized.scenario) sections.push(`场景设定：\n${normalized.scenario}`);
  if (normalized.creator_notes) sections.push(`补充说明：\n${normalized.creator_notes}`);
  if (normalized.mes_example) sections.push(`示例对话：\n${normalized.mes_example}`);

  const stageLines = [];
  sortedEntries(normalized.plotStages, (left, right) => {
    const a = stageSortKey(left);
    const b = stageSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  }).forEach(([key, stage]) => {
    const parts = [];
    if (stage.description.trim()) parts.push(stage.description.trim());
    if (stage.rules.trim()) parts.push(`规则：${stage.rules.trim()}`);
    if (parts.length) stageLines.push(`阶段 ${key}：${parts.join(" | ")}`);
  });
  if (stageLines.length) sections.push(`剧情阶段：\n${stageLines.join("\n")}`);

  const personaEntries = sortedEntries(normalized.personas, (left, right) => {
    const a = personaSortKey(left);
    const b = personaSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  });
  const castNames = personaEntries
    .map(([, item]) => String(item.name || "").trim())
    .filter(Boolean);
  const castLines = personaEntries
    .map(([, item]) => {
      const name = String(item.name || "").trim();
      if (!name) return "";
      const details = [item.description, item.personality, item.scenario, item.creator_notes]
        .map((entry) => String(entry || "").trim())
        .filter(Boolean)
        .join(" | ");
      return `${name}：${details || "暂无补充说明"}`;
    })
    .filter(Boolean);
  if (castLines.length) sections.push(`角色阵容：\n${castLines.join("\n")}`);
  if (castNames.length > 1) {
    sections.push(
      [
        "多角色回复规则：",
        `每次回复都尽量让这些角色全部出场：${castNames.join("、")}。`,
        "每个角色单独分段。",
        "使用“角色名：台词”的固定格式。",
        "不要把不同角色混成一个声音。",
      ].join("\n")
    );
  }

  const rawCardName = String(normalized.name || "").trim();
  const normalizedCardName = rawCardName.toLowerCase();
  const looksLikeTemplateName =
    !rawCardName
    || normalizedCardName === "template character"
    || normalizedCardName === "single role template"
    || normalizedCardName === "multi role template";
  let derivedDisplayName = rawCardName;
  if ((looksLikeTemplateName || !derivedDisplayName) && castNames.length === 1) {
    derivedDisplayName = castNames[0];
  } else if ((looksLikeTemplateName || !derivedDisplayName) && castNames.length > 1) {
    derivedDisplayName = castNames.join(" / ");
  }

  return {
    name: derivedDisplayName || "Template Character",
    greeting: String(normalized.first_mes || "").trim() || "今天想聊点什么？我会认真听你说。",
    systemPrompt:
      sections.join("\n\n").trim() ||
      "你是一个自然、稳定、富有陪伴感的 AI 角色，请始终依据设定完成回复。",
  };
}

function mergeState(source) {
  const merged = deepClone(DEFAULT_STATE);
  if (!source || typeof source !== "object") return merged;

  merged.settings = { ...merged.settings, ...(source.settings || {}) };
  merged.settings.embeddingFields = Array.isArray(merged.settings.embeddingFields)
    ? merged.settings.embeddingFields.filter((item) => typeof item === "string" && item.trim())
    : [...DEFAULT_SETTINGS.embeddingFields];
  delete merged.settings.spriteBasePath;
  delete merged.settings.spriteEnabled;
  if (ROUTES.includes(source.activeRoute)) merged.activeRoute = source.activeRoute;

  const legacySlots = source.slots && typeof source.slots === "object" ? source.slots : null;
  const preferredLegacySlot =
    legacySlots
    && (legacySlots[source.activeSlot] || legacySlots.slot_1 || Object.values(legacySlots).find((item) => item && typeof item === "object"));
  const runtimeSource = source.runtime && typeof source.runtime === "object" ? source.runtime : preferredLegacySlot;
  merged.runtime = normalizeRuntimeState(runtimeSource);

  const roleCard = normalizeRoleCard(
    source.currentCard?.raw
    || preferredLegacySlot?.currentCard?.raw
    || merged.currentCard.raw
  );
  merged.currentCard = {
    sourceName: String(source.currentCard?.sourceName || preferredLegacySlot?.currentCard?.sourceName || merged.currentCard.sourceName),
    raw: roleCard,
  };
  merged.persona = derivePersonaFromRoleCard(roleCard);

  return merged;
}

function loadState() {
  try {
    const raw = localStorage.getItem(APP_STATE_KEY);
    return raw ? mergeState(JSON.parse(raw)) : deepClone(DEFAULT_STATE);
  } catch {
    return deepClone(DEFAULT_STATE);
  }
}

let state = loadState();
let editingPresetId = getActivePresetFromStore(getActiveSlot().presetStore).id;
let saveStateTimer = null;

function saveState() {
  if (saveStateTimer) window.clearTimeout(saveStateTimer);
  saveStateTimer = window.setTimeout(() => {
    saveStateTimer = null;
    localStorage.setItem(APP_STATE_KEY, JSON.stringify(state));
  }, 120);
}

function flushState() {
  if (saveStateTimer) {
    window.clearTimeout(saveStateTimer);
    saveStateTimer = null;
  }
  localStorage.setItem(APP_STATE_KEY, JSON.stringify(state));
}

const ROUTE_META = {
  chat: { title: "聊天", subtitle: "" },
  config: { title: "配置", subtitle: "" },
  preset: { title: "预设", subtitle: "" },
  card: { title: "角色卡", subtitle: "" },
  workshop: { title: "创意工坊", subtitle: "" },
  memory: { title: "记忆库", subtitle: "" },
  worldbook: { title: "世界书", subtitle: "" },
};

function qs(id) {
  return document.getElementById(id);
}

function getActiveSlot() {
  return state.runtime;
}

function getCurrentCardStore() {
  return state.currentCard;
}

function getCurrentPersona() {
  return state.persona;
}

function getCurrentRoleLabel() {
  return String(getCurrentPersona()?.name || getCurrentCardStore()?.raw?.name || "当前角色").trim() || "当前角色";
}

function formatTime(ts) {
  return new Date(ts).toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

function setStatus(text) {
  const value = String(text || "");
  if (qs("statusText")) qs("statusText").textContent = value;
  if (qs("presetStatusText")) qs("presetStatusText").textContent = value;
}

function showModal(title, message) {
  qs("modalTitle").textContent = title;
  qs("modalBody").textContent = message;
  qs("modalBackdrop").classList.remove("hidden");
}

function hideModal() {
  qs("modalBackdrop").classList.add("hidden");
}

function confirmDangerAction(message) {
  return window.confirm(message);
}

function openDrawer() {
  const backdrop = qs("drawerBackdrop");
  if (!backdrop) return;
  backdrop.classList.remove("hidden");
  requestAnimationFrame(() => backdrop.classList.add("open"));
}

function closeDrawer() {
  const backdrop = qs("drawerBackdrop");
  if (!backdrop || backdrop.classList.contains("hidden")) return;
  backdrop.classList.remove("open");
  window.setTimeout(() => backdrop.classList.add("hidden"), 180);
}

function detectPreset(url) {
  const found = MODEL_PRESETS.find((item) => item.url && item.url === String(url || "").trim());
  return found ? found.id : "custom";
}

function applyAppearance() {
  const app = qs("mobileApp");
  const settings = state.settings;
  document.body.classList.toggle("light-theme", settings.theme === "light");
  app.style.setProperty("--content-opacity", String(Number(settings.uiOpacity || 0.88)));
  app.style.setProperty("--overlay-strength", String(Number(settings.backgroundOverlay || 0.36)));
  if (settings.backgroundImageUrl) {
    document.body.style.backgroundImage =
      `linear-gradient(rgba(12, 21, 33, ${settings.backgroundOverlay}), rgba(19, 29, 43, ${settings.backgroundOverlay})), url("${settings.backgroundImageUrl}")`;
    document.body.style.backgroundSize = "cover";
    document.body.style.backgroundPosition = "center";
  } else {
    document.body.style.backgroundImage = "";
    document.body.style.backgroundSize = "";
    document.body.style.backgroundPosition = "";
  }
}

function renderGlobalChrome() {
  applyAppearance();
  const slot = getActiveSlot();
  qs("currentRouteTitle").textContent = ROUTE_META[state.activeRoute]?.title || "聊天";
  qs("activeRuntimeName").textContent = getCurrentRoleLabel();
  const stage = getCurrentGameStage(slot);
  qs("runtimeSummaryText").textContent = `${GLOBAL_RUNTIME_NAME} · temp ${Math.max(0, Number(slot.temp ?? 0) || 0)} · 阶段 ${stage} · ${slot.messages.length} 条消息 · ${slot.memories.length} 条记忆 · ${slot.worldbook.entries.length} 条世界书`;

  qs("themeToggleButton").textContent = state.settings.theme === "light" ? "浅色模式" : "暗色模式";
}

function navigate(route) {
  const target = ROUTES.includes(route) ? route : "chat";
  state.activeRoute = target;
  saveState();
  closeDrawer();
  document.querySelectorAll(".route-screen").forEach((screen) => {
    screen.classList.toggle("hidden", screen.dataset.route !== target);
  });
  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.nav === target);
  });
  renderRoute(target);
}

function renderRoute(route) {
  renderGlobalChrome();
  if (route === "chat") renderChat();
  if (route === "config") renderConfig();
  if (route === "preset") renderPreset();
  if (route === "card") renderCard();
  if (route === "workshop") renderWorkshopSettings();
  if (route === "memory") renderMemory();
  if (route === "worldbook") renderWorldbook();
  bindDynamicEditors();
}

function parseAssistantReply(raw) {
  const text = String(raw || "");
  const thinkMatch = text.match(/<think>([\s\S]*?)<\/think>/i);
  const think = thinkMatch ? thinkMatch[1].trim() : "";
  const visible = thinkMatch ? text.replace(thinkMatch[0], "").trim() : text.trim();
  return { raw: text, think, visible };
}

function getActiveUserProfile() {
  return getActiveSlot().userProfile || createDefaultUserProfile();
}

function getUserAvatarLabel() {
  const profile = getActiveUserProfile();
  return String(profile.displayName || profile.nickname || "我").trim().slice(0, 1) || "我";
}

function getAssistantAvatarLabel() {
  return String(getCurrentPersona().name || "AI").trim().slice(0, 1) || "AI";
}

function getAssistantAvatarUrl() {
  const slot = getActiveSlot();
  const profile = slot.userProfile || createDefaultUserProfile();
  return String(profile.roleAvatarUrl || "").trim();
}

function buildAvatarNode(role) {
  const avatar = document.createElement("div");
  avatar.className = `message-avatar ${role === "user" ? "user-avatar" : "assistant-avatar"}`;
  avatar.setAttribute("aria-hidden", "true");

  if (role === "user") {
    const profile = getActiveUserProfile();
    const avatarUrl = String(profile.avatarUrl || "").trim();
    if (avatarUrl) {
      const img = document.createElement("img");
      img.alt = String(profile.displayName || "我").trim() || "我";
      img.src = avatarUrl;
      img.addEventListener("error", () => {
        img.remove();
        const fallback = document.createElement("span");
        fallback.className = "avatar-text";
        fallback.textContent = getUserAvatarLabel();
        avatar.appendChild(fallback);
      });
      avatar.appendChild(img);
    } else {
      const label = document.createElement("span");
      label.className = "avatar-text";
      label.textContent = getUserAvatarLabel();
      avatar.appendChild(label);
    }
    return avatar;
  }

  const roleAvatarUrl = getAssistantAvatarUrl();
  if (roleAvatarUrl) {
    const img = document.createElement("img");
    img.alt = getCurrentPersona().name || "AI";
    img.src = roleAvatarUrl;
    img.addEventListener("error", () => {
      img.remove();
      const label = document.createElement("span");
      label.className = "avatar-text";
      label.textContent = getAssistantAvatarLabel();
      avatar.appendChild(label);
    });
    avatar.appendChild(img);
  } else {
    const label = document.createElement("span");
    label.className = "avatar-text";
    label.textContent = getAssistantAvatarLabel();
    avatar.appendChild(label);
  }
  return avatar;
}

function buildMessageNode(item) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${item.role}`;
  const column = document.createElement("div");
  column.className = "message-column";

  if (item.role === "assistant") {
    const parsed = parseAssistantReply(item.content);
    if (parsed.think) {
      const thinkBox = document.createElement("details");
      thinkBox.className = "think-box";
      thinkBox.innerHTML = `<summary>查看思考链</summary><div class="think-content">${escapeHtml(parsed.think)}</div>`;
      column.appendChild(thinkBox);
    }
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = parsed.visible || parsed.raw;
    column.appendChild(bubble);
  } else {
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = item.content;
    column.appendChild(bubble);
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = formatTime(item.createdAt);
  column.appendChild(meta);
  const avatar = buildAvatarNode(item.role);
  if (item.role === "user") {
    wrapper.appendChild(column);
    wrapper.appendChild(avatar);
  } else {
    wrapper.appendChild(avatar);
    wrapper.appendChild(column);
  }
  return wrapper;
}

function syncChatScrollRange() {
  const list = qs("messageList");
  const range = qs("chatScrollRange");
  const meta = qs("chatScrollMeta");
  if (!list || !range) return;
  const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
  if (maxScroll <= 0) {
    range.value = "0";
    range.disabled = true;
    if (meta) meta.textContent = "100%";
    return;
  }
  range.disabled = false;
  const ratio = Math.min(Math.max(list.scrollTop / maxScroll, 0), 1);
  range.value = String(Math.round((1 - ratio) * 1000));
  if (meta) meta.textContent = `${Math.round(ratio * 100)}%`;
}

function bindChatScrollRange() {
  const list = qs("messageList");
  const range = qs("chatScrollRange");
  if (!list || !range || range.dataset.bound) return;
  list.addEventListener("scroll", syncChatScrollRange, { passive: true });
  range.addEventListener("input", () => {
    const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
    if (maxScroll <= 0) return;
    const ratio = 1 - Number(range.value || 0) / 1000;
    list.scrollTop = maxScroll * ratio;
    syncChatScrollRange();
  });
  range.dataset.bound = "true";
}

function isMessageListNearBottom(list, threshold = 48) {
  if (!list) return true;
  return list.scrollHeight - list.clientHeight - list.scrollTop <= threshold;
}

function renderChat({ stickToBottom = true } = {}) {
  const slot = getActiveSlot();
  const persona = getCurrentPersona();
  qs("chatPersonaName").textContent = persona.name || "Template Character";
  qs("chatGreeting").textContent = persona.greeting || "";
  const list = qs("messageList");
  const previousBottomOffset = Math.max(0, list.scrollHeight - list.clientHeight - list.scrollTop);
  list.innerHTML = "";
  slot.messages.forEach((item) => list.appendChild(buildMessageNode(item)));
  if (stickToBottom) {
    list.scrollTop = list.scrollHeight;
  } else {
    const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
    list.scrollTop = Math.max(0, Math.min(maxScroll, maxScroll - previousBottomOffset));
  }
  bindChatScrollRange();
  window.requestAnimationFrame(syncChatScrollRange);
}

function createRequestId() {
  return `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function requestNativeImagePick() {
  ensureNativeBridge();
  if (typeof window.XuqiNative.pickImageAsync !== "function") {
    return Promise.reject(new Error("当前环境不支持原生图片选择。"));
  }
  const requestId = createRequestId();
  return new Promise((resolve, reject) => {
    pendingNativeImagePickRequests.set(requestId, { resolve, reject });
    try {
      window.XuqiNative.pickImageAsync(requestId);
    } catch (error) {
      pendingNativeImagePickRequests.delete(requestId);
      reject(error instanceof Error ? error : new Error("打开图片选择器失败"));
    }
  });
}

function ensureNativeBridge() {
  if (!window.XuqiNative) {
    throw new Error("未检测到安卓桥接对象，当前环境无法直接请求模型。");
  }
}

function normalizeEndpoint(baseUrl) {
  const trimmed = String(baseUrl || "").trim().replace(/\/+$/, "");
  return trimmed.endsWith("/chat/completions") ? trimmed : `${trimmed}/chat/completions`;
}

function callModel(messages, { temperature, timeoutSec } = {}) {
  ensureNativeBridge();
  const payload = {
    apiBaseUrl: normalizeEndpoint(state.settings.apiBaseUrl),
    apiKey: state.settings.apiKey,
    model: state.settings.model,
    temperature: temperature ?? state.settings.temperature,
    timeoutSec: timeoutSec ?? state.settings.timeoutSec,
    messages,
  };
  const responseRaw = window.XuqiNative.postChat(JSON.stringify(payload));
  const response = JSON.parse(responseRaw || "{}");
  if (!response.ok) {
    throw new Error(response.error || "模型请求失败");
  }
  return String(response.content || "");
}

function callModelAsync(messages, { temperature, timeoutSec } = {}) {
  ensureNativeBridge();
  if (typeof window.XuqiNative.postChatAsync !== "function") {
    return Promise.resolve(callModel(messages, { temperature, timeoutSec }));
  }
  const payload = {
    apiBaseUrl: normalizeEndpoint(state.settings.apiBaseUrl),
    apiKey: state.settings.apiKey,
    model: state.settings.model,
    temperature: temperature ?? state.settings.temperature,
    timeoutSec: timeoutSec ?? state.settings.timeoutSec,
    messages,
  };
  const requestId = createRequestId();
  return new Promise((resolve, reject) => {
    pendingNativeRequests.set(requestId, { resolve, reject });
    try {
      window.XuqiNative.postChatAsync(JSON.stringify(payload), requestId);
    } catch (error) {
      pendingNativeRequests.delete(requestId);
      reject(error instanceof Error ? error : new Error("模型请求失败"));
    }
  });
}

function getNextNumericKey(objectValue) {
  const keys = Object.keys(objectValue || {})
    .map((key) => Number(key))
    .filter((value) => Number.isFinite(value));
  return String((keys.length ? Math.max(...keys) : 0) + 1);
}

function getNextStageKey(plotStages) {
  const keys = Object.keys(plotStages || {}).map((key) => String(key).toUpperCase());
  let code = 65;
  while (keys.includes(String.fromCharCode(code))) code += 1;
  return String.fromCharCode(code);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function worldbookEntryEnabled(entry) {
  return entry && entry.enabled !== false;
}

function splitWorldbookAliases(trigger) {
  return String(trigger || "")
    .split(/[|,，、\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function keywordMatchesQuery(queryText, keyword, { caseSensitive, wholeWord }) {
  let query = String(queryText || "");
  let target = String(keyword || "").trim();
  if (!query || !target) return false;
  if (!caseSensitive) {
    query = query.toLowerCase();
    target = target.toLowerCase();
  }
  if (!wholeWord) return query.includes(target);
  if (/[\u4e00-\u9fff]/.test(target)) return query.includes(target);
  const pattern = new RegExp(`(?<![0-9A-Za-z_])${escapeRegExp(target)}(?![0-9A-Za-z_])`, caseSensitive ? "u" : "iu");
  return pattern.test(query);
}

function worldbookAliasMatchResult(text, aliases, { mode, caseSensitive, wholeWord }) {
  if (!aliases.length) return { ok: false, matches: [] };
  const matches = aliases.filter((alias) => keywordMatchesQuery(text, alias, { caseSensitive, wholeWord }));
  const ok = mode === "all" ? matches.length === aliases.length : matches.length > 0;
  return { ok, matches };
}

function evaluateWorldbookKeywordEntry(text, entry, settings) {
  const primaryAliases = splitWorldbookAliases(entry.primaryTriggers);
  const secondaryAliases = splitWorldbookAliases(entry.secondaryTriggers);
  const primary = worldbookAliasMatchResult(text, primaryAliases, {
    mode: entry.matchMode || settings.defaultMatchMode,
    caseSensitive: entry.caseSensitive ?? settings.caseSensitive,
    wholeWord: entry.wholeWord ?? settings.wholeWord,
  });
  const secondary = worldbookAliasMatchResult(text, secondaryAliases, {
    mode: entry.secondaryMode || settings.defaultSecondaryMode,
    caseSensitive: entry.caseSensitive ?? settings.caseSensitive,
    wholeWord: entry.wholeWord ?? settings.wholeWord,
  });
  let ok = primary.ok;
  if (secondaryAliases.length) {
    ok = entry.groupOperator === "or" ? primary.ok || secondary.ok : primary.ok && secondary.ok;
  }
  return {
    ok,
    matched: [...primary.matches, ...secondary.matches].join(" / "),
  };
}

function buildWorldbookMatchPayload(entry, { source, matched = "", matchedDepth = 0, matchedFrom = "" }) {
  return {
    ...entry,
    priority: entry.order,
    source,
    matched,
    matchedDepth,
    matchedFrom,
    selectedForPrompt: false,
    droppedReason: "",
  };
}

function worldbookGlobalSelectionSortKey(entry) {
  const sourceRank = { constant: 0, sticky: 1, keyword: 2 }[entry.source || "keyword"] ?? 2;
  return [entry.order ?? entry.priority ?? 100, sourceRank, entry.title || entry.primaryTriggers || ""];
}

function worldbookBucketSortKey(entry) {
  return [entry.injectionOrder ?? entry.order ?? 100, entry.order ?? 100, entry.title || entry.primaryTriggers || ""];
}

function worldbookRecursiveSeedText(entry) {
  return [entry.title, entry.primaryTriggers, entry.secondaryTriggers]
    .map((value) => String(value || "").trim())
    .filter((value, index, list) => value && list.indexOf(value) === index)
    .join("\n");
}

function matchWorldbookEntries(inputText, worldbook, { runtime = null, mutateRuntime = true } = {}) {
  const text = String(inputText || "").trim();
  const store = sanitizeWorldbookStore(worldbook);
  const settings = store.settings;
  if (!text || !settings.enabled) return [];

  const runtimeState = sanitizeWorldbookRuntimeState(runtime || {});
  const currentTurn = mutateRuntime ? runtimeState.turnIndex + 1 : runtimeState.turnIndex + 1;
  if (mutateRuntime && runtime) runtime.turnIndex = currentTurn;
  const runtimeEntries = runtimeState.entries || {};
  const nextRuntimeEntries = {};
  const hits = [];
  const hitsById = new Map();
  const keywordCandidates = [];

  store.entries.filter(worldbookEntryEnabled).forEach((entry) => {
    if (!entry.content) return;
    if (entry.entryType === "keyword" && !splitWorldbookAliases(entry.primaryTriggers).length) return;
    const entryId = String(entry.id || "").trim();
    if (!entryId) return;
    const row = runtimeEntries[entryId] || {};
    const stateRow = {
      activeUntilTurn: clampInteger(row.activeUntilTurn, 0, 10000000, 0),
      cooldownUntilTurn: clampInteger(row.cooldownUntilTurn, 0, 10000000, 0),
      lastTriggerTurn: clampInteger(row.lastTriggerTurn, 0, 10000000, 0),
      lastRoll: clampInteger(row.lastRoll, 0, 100, 0),
      lastResult: String(row.lastResult || "").trim(),
      lastReason: String(row.lastReason || "").trim(),
      matchedText: String(row.matchedText || "").trim(),
    };

    if (entry.entryType === "constant") {
      stateRow.lastResult = "constant";
      stateRow.lastReason = "always_on";
      nextRuntimeEntries[entryId] = stateRow;
      const hit = buildWorldbookMatchPayload(entry, { source: "constant", matched: "常驻" });
      hits.push(hit);
      hitsById.set(entryId, hit);
      return;
    }

    if (stateRow.activeUntilTurn >= currentTurn && stateRow.lastTriggerTurn < currentTurn) {
      stateRow.lastResult = "sticky";
      stateRow.lastReason = "active";
      nextRuntimeEntries[entryId] = stateRow;
      const hit = buildWorldbookMatchPayload(entry, {
        source: "sticky",
        matched: stateRow.matchedText || entry.primaryTriggers,
      });
      hits.push(hit);
      hitsById.set(entryId, hit);
      return;
    }

    if (stateRow.cooldownUntilTurn >= currentTurn) {
      stateRow.lastResult = "cooldown";
      stateRow.lastReason = "cooldown";
      nextRuntimeEntries[entryId] = stateRow;
      return;
    }

    keywordCandidates.push({ entry, entryId, stateRow });
  });

  let depth = 0;
  let seedQueue = [{ text, depth: 0, from: "" }];
  while (seedQueue.length) {
    const nextQueue = [];
    const newlyMatched = [];
    for (const seed of seedQueue) {
      const seedText = String(seed.text || "").trim();
      if (!seedText) continue;
      const seedDepth = clampInteger(seed.depth, 0, 5, depth);
      for (const candidate of keywordCandidates) {
        if (hitsById.has(candidate.entryId)) continue;
        if (seedDepth > 0 && candidate.entry.recursiveEnabled === false) continue;
        const result = evaluateWorldbookKeywordEntry(seedText, candidate.entry, settings);
        if (!result.ok) continue;

        const chance = clampInteger(candidate.entry.chance, 0, 100, settings.defaultChance);
        const roll = Math.floor(Math.random() * 100) + 1;
        candidate.stateRow.lastRoll = roll;
        candidate.stateRow.matchedText = result.matched.slice(0, 240);
        if (chance < 100 && roll > chance) {
          candidate.stateRow.lastResult = "chance_failed";
          candidate.stateRow.lastReason = "chance";
          nextRuntimeEntries[candidate.entryId] = candidate.stateRow;
          hitsById.set(candidate.entryId, { id: candidate.entryId, chanceFailed: true });
          continue;
        }

        const activeUntilTurn = currentTurn + candidate.entry.stickyTurns;
        const cooldownUntilTurn = activeUntilTurn + candidate.entry.cooldownTurns;
        candidate.stateRow.activeUntilTurn = activeUntilTurn;
        candidate.stateRow.cooldownUntilTurn = cooldownUntilTurn;
        candidate.stateRow.lastTriggerTurn = currentTurn;
        candidate.stateRow.lastResult = "triggered";
        candidate.stateRow.lastReason = seedDepth > 0 ? "recursive" : "keyword";
        nextRuntimeEntries[candidate.entryId] = candidate.stateRow;
        const hit = buildWorldbookMatchPayload(candidate.entry, {
          source: "keyword",
          matched: result.matched,
          matchedDepth: seedDepth,
          matchedFrom: seed.from,
        });
        hits.push(hit);
        hitsById.set(candidate.entryId, hit);
        newlyMatched.push(hit);
      }
    }

    if (!settings.recursiveScanEnabled || depth >= settings.recursionMaxDepth || !newlyMatched.length) break;
    newlyMatched.forEach((hit) => {
      if (hit.recursiveEnabled === false || hit.preventFurtherRecursion) return;
      const seedText = worldbookRecursiveSeedText(hit);
      if (!seedText) return;
      nextQueue.push({
        text: seedText,
        depth: clampInteger(hit.matchedDepth, 0, 5, depth) + 1,
        from: hit.title || hit.primaryTriggers || "",
      });
    });
    depth += 1;
    seedQueue = nextQueue;
  }

  keywordCandidates.forEach((candidate) => {
    if (nextRuntimeEntries[candidate.entryId] || hitsById.has(candidate.entryId)) return;
    candidate.stateRow.lastResult = candidate.stateRow.lastResult || "not_matched";
    candidate.stateRow.lastReason = candidate.stateRow.lastReason || "keyword";
    nextRuntimeEntries[candidate.entryId] = candidate.stateRow;
  });
  if (mutateRuntime && runtime) runtime.entries = nextRuntimeEntries;

  const selected = hits
    .filter((item) => !item.chanceFailed)
    .sort((left, right) => {
      const a = worldbookGlobalSelectionSortKey(left);
      const b = worldbookGlobalSelectionSortKey(right);
      return a[0] - b[0] || a[1] - b[1] || String(a[2]).localeCompare(String(b[2]), "zh-Hans-CN");
    })
    .slice(0, settings.maxEntries);
  const selectedIds = new Set(selected.map((item) => item.id));
  return selected.map((item) => ({
    ...item,
    selectedForPrompt: selectedIds.has(item.id),
    droppedReason: "",
  }));
}

function buildMemoryRecap(memories) {
  if (!memories.length) return "";
  return memories
    .map((item, index) => {
      const title = String(item.title || `记忆片段 ${index + 1}`).trim();
      const content = String(item.content || "").trim();
      const tags = sanitizeTags(item.tags || []).join("、");
      return [`[${title}]`, content, tags ? `标签：${tags}` : ""].filter(Boolean).join("\n");
    })
    .join("\n\n");
}

function buildDeletedMemoryGuard(deletedMemories) {
  if (!deletedMemories || !deletedMemories.length) return "";
  return deletedMemories
    .slice(0, PROMPT_VISIBLE_TOMBSTONES)
    .map((item, index) => {
      const title = String(item.title || `已删除记忆 ${index + 1}`).trim();
      const content = String(item.content || "").trim();
      return [`${index + 1}. ${title}`, content ? `旧内容：${content.slice(0, 180)}` : ""].filter(Boolean).join("\n");
    })
    .join("\n\n");
}

function buildUserProfilePrompt(userProfile) {
  const profile = userProfile || createDefaultUserProfile();
  const sections = [];
  const displayName = String(profile.displayName || "").trim();
  const nickname = String(profile.nickname || "").trim();
  const profileText = String(profile.profileText || "").trim();
  const notes = String(profile.notes || "").trim();
  if (!displayName && !nickname && !profileText && !notes) return "";
  if (displayName) sections.push(`用户显示名：${displayName}`);
  if (nickname) sections.push(`用户昵称：${nickname}`);
  if (profileText) sections.push(`用户设定：${profileText}`);
  if (notes) sections.push(`用户备注：${notes}`);
  return sections.join("\n");
}

function buildWorldbookPrompt(entries) {
  if (!entries || !entries.length) return "";
  const lines = [
    "以下是本轮命中的世界书设定。",
    "把它们当成高优先级补充事实，不要在回复里说自己看到了这些设定。",
    "",
  ];
  entries.forEach((entry, index) => {
    lines.push(`【${index + 1}. ${entry.title || `世界书词条 ${index + 1}`}】`);
    if (entry.source) lines.push(`来源：${entry.source}`);
    if (entry.group) lines.push(`分组：${entry.group}`);
    if (entry.primaryTriggers) lines.push(`主触发词：${entry.primaryTriggers}`);
    if (entry.secondaryTriggers) lines.push(`辅助触发词：${entry.secondaryTriggers}`);
    if (entry.matched) lines.push(`本轮命中：${entry.matched}`);
    if (entry.notes) lines.push(`备注：${entry.notes}`);
    lines.push(String(entry.content || "").trim());
    lines.push("");
  });
  return lines.join("\n").trim();
}

function buildWorldbookAnswerGuard(userText, entries) {
  if (!entries || !entries.length) return "";
  const titles = entries
    .map((entry) => String(entry.title || "").trim())
    .filter(Boolean)
    .join("、");
  return [
    "回答约束：如果本轮问题明显涉及上面命中的世界书设定，回复时不要忽略或自相矛盾。",
    titles ? `本轮重点参考词条：${titles}` : "",
    `当前用户输入：${String(userText || "").trim()}`,
  ]
    .filter(Boolean)
    .join("\n");
}

function buildPromptPreviewText(layers, messages) {
  const sectionText = layers
    .map((item, index) => `[${index + 1}. ${item.title}]\n${item.content}`)
    .join("\n\n");
  const messageText = messages
    .map((item, index) => `${index + 1}. [${item.role}]\n${String(item.content || "").trim()}`)
    .join("\n\n");
  return [sectionText, "【最终发送给模型的 messages】", messageText].filter(Boolean).join("\n\n");
}

function bucketWorldbookMatches(entries) {
  const buckets = {
    beforeCharDefs: [],
    afterCharDefs: [],
    inChat: new Map(),
  };
  const sorted = [...(entries || [])].sort((left, right) => {
    const a = worldbookBucketSortKey(left);
    const b = worldbookBucketSortKey(right);
    return a[0] - b[0] || a[1] - b[1] || String(a[2]).localeCompare(String(b[2]), "zh-Hans-CN");
  });
  sorted.forEach((entry) => {
    const position = normalizeWorldbookInsertionPosition(entry.insertionPosition, "after_char_defs");
    if (position === "before_char_defs") {
      buckets.beforeCharDefs.push(entry);
      return;
    }
    if (position === "in_chat") {
      const depth = clampInteger(entry.injectionDepth, 0, 3, 0);
      if (!buckets.inChat.has(depth)) buckets.inChat.set(depth, []);
      buckets.inChat.get(depth).push(entry);
      return;
    }
    buckets.afterCharDefs.push(entry);
  });
  return buckets;
}

function appendWorldbookInChatMessages(messages, entries) {
  if (!entries || !entries.length) return;
  const groups = new Map();
  entries.forEach((entry) => {
    const role = normalizeWorldbookInjectionRole(entry.injectionRole, "system");
    if (!groups.has(role)) groups.set(role, []);
    groups.get(role).push(entry);
  });
  ["system", "user", "assistant"].forEach((role) => {
    const items = groups.get(role) || [];
    if (!items.length) return;
    messages.push({ role, content: buildWorldbookPrompt(items) });
  });
}

function buildChatPayload(slot, userText, options = {}) {
  const mutateWorldbookRuntime = options.mutateWorldbookRuntime !== false;
  const historyLimit = Math.max(4, Number(state.settings.historyLimit || 20));
  const maxTokens = Math.max(0, Number(state.settings.maxTokens || 0));
  const messages = [];
  const layers = [];
  const persona = getCurrentPersona();
  let historySource = Array.isArray(slot.messages) ? slot.messages : [];
  const lastMessage = historySource[historySource.length - 1];
  if (
    lastMessage &&
    lastMessage.role === "user" &&
    String(lastMessage.content || "").trim() === String(userText || "").trim()
  ) {
    historySource = historySource.slice(0, -1);
  }
  const recentHistory = historySource.slice(-historyLimit);
  const recentHistoryText = buildConversationTranscript(recentHistory);
  const rolePrompt = String(persona.systemPrompt || "请根据设定进行稳定、自然的角色扮演。").trim();
  const baseMainPrompt = [
    "你要扮演角色并保持人设稳定。",
    "优先依据主提示、角色卡、长期记忆、按需命中的世界书和最近聊天记录来回答。",
    "不要脱离当前设定，不要无视命中的长期信息。",
  ].join("\n");

  const presetPrompt = buildPresetPromptFromPreset(getActivePresetFromStore(slot.presetStore));
  const mainPrompt = [baseMainPrompt, presetPrompt].filter(Boolean).join("\n\n").trim();
  if (presetPrompt) {
    layers.push({ id: "system_main", title: "系统提示词 / 主提示", content: mainPrompt });
  } else {
    layers.push({ id: "system_main", title: "系统提示词 / 主提示", content: baseMainPrompt });
  }

  const worldbookSourceText = [recentHistoryText, userText].filter(Boolean).join("\n");
  const worldbookMatches = matchWorldbookEntries(worldbookSourceText, slot.worldbook, {
    runtime: slot.worldbookRuntime,
    mutateRuntime: mutateWorldbookRuntime,
  });
  const worldbookBuckets = bucketWorldbookMatches(worldbookMatches);
  const beforeCharDefsPrompt = buildWorldbookPrompt(worldbookBuckets.beforeCharDefs);
  if (beforeCharDefsPrompt) {
    layers.push({
      id: "worldbook_before_char_defs",
      title: "世界书（角色卡前）",
      content: beforeCharDefsPrompt,
    });
  }

  layers.push({ id: "role_card", title: "角色卡固定设定", content: rolePrompt });

  const afterCharDefsPrompt = buildWorldbookPrompt(worldbookBuckets.afterCharDefs);
  if (afterCharDefsPrompt) {
    layers.push({
      id: "worldbook_after_char_defs",
      title: "世界书（角色卡后）",
      content: afterCharDefsPrompt,
    });
  }

  const userProfilePrompt = buildUserProfilePrompt(slot.userProfile);
  const memoryRecap = buildMemoryRecap(slot.memories);
  const deletedMemoryGuard = buildDeletedMemoryGuard(slot.deletedMemories || []);
  const memoryLayerContent = [
    memoryRecap ? `以下是当前长期记忆片段，请把它们视为持续有效的前情提要：\n\n${memoryRecap}` : "",
    userProfilePrompt ? `以下是用户资料，请参考但不要直接复述：\n\n${userProfilePrompt}` : "",
    deletedMemoryGuard
      ? `以下内容是用户已经删除或作废的旧记忆。除非用户重新确认，否则不要把它们当成仍然有效的长期设定，也不要把它们重新写回长期记忆：\n\n${deletedMemoryGuard}`
      : "",
  ]
    .filter(Boolean)
    .join("\n\n");
  if (memoryLayerContent) {
    layers.push({ id: "memory_context", title: "记忆 / 摘要 / 长期信息", content: memoryLayerContent });
  }

  const worldbookAnswerGuard = buildWorldbookAnswerGuard(userText, worldbookMatches);
  if (worldbookAnswerGuard) {
    layers.push({ id: "worldbook_answer_guard", title: "世界书回答约束", content: worldbookAnswerGuard });
  }

  const systemSections = layers
    .filter((layer) =>
      [
        "system_main",
        "worldbook_before_char_defs",
        "role_card",
        "worldbook_after_char_defs",
        "memory_context",
        "worldbook_answer_guard",
      ].includes(layer.id)
    )
    .map((layer) => layer.content)
    .filter(Boolean);
  if (systemSections.length) {
    messages.push({ role: "system", content: systemSections.join("\n\n") });
  }

  const historyMessages = [];
  recentHistory.forEach((item, index) => {
    const tailDepth = recentHistory.length - index;
    appendWorldbookInChatMessages(messages, worldbookBuckets.inChat.get(tailDepth) || []);
    const content = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
    historyMessages.push(`${item.role === "user" ? "用户" : (persona.name || "角色")}：${content}`);
    messages.push({ role: item.role, content });
  });
  if (historyMessages.length) {
    layers.push({ id: "recent_history", title: "最近聊天记录", content: historyMessages.join("\n") });
  }
  appendWorldbookInChatMessages(messages, worldbookBuckets.inChat.get(0) || []);
  layers.push({ id: "user_input", title: "你这一轮的新输入", content: userText });
  messages.push({ role: "user", content: userText });
  return {
    messages,
    worldbookMatches,
    maxTokens,
    layers,
    previewText: buildPromptPreviewText(layers, messages),
    messageCount: messages.length,
    systemSectionCount: systemSections.length,
    recentHistoryTurns: recentHistory.length,
  };
}

function buildAssistantLiveNode(thinkText = "") {
  const list = qs("messageList");
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";
  const column = document.createElement("div");
  column.className = "message-column";

  let thinkBox = null;
  if (thinkText) {
    thinkBox = document.createElement("details");
    thinkBox.className = "think-box";
    thinkBox.open = false;
    thinkBox.innerHTML = `<summary>查看思考链</summary><div class="think-content">${escapeHtml(thinkText)}</div>`;
    column.appendChild(thinkBox);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  column.appendChild(bubble);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = formatTime(Date.now());
  column.appendChild(meta);

  wrapper.appendChild(buildAvatarNode("assistant"));
  wrapper.appendChild(column);
  list.appendChild(wrapper);
  syncChatScrollRange();
  return { list, bubble, thinkBox };
}

function flushActiveTypewriter() {
  if (!activeTypewriter) return;
  activeTypewriter.bubble.textContent = activeTypewriter.fullText;
  syncChatScrollRange();
  activeTypewriter.cancelled = true;
  activeTypewriter = null;
}

function typeIntoBubble(bubble, text, list) {
  flushActiveTypewriter();
  const fullText = String(text || "");
  bubble.textContent = "";
  const job = {
    bubble,
    list,
    fullText,
    visibleText: "",
    index: 0,
    cancelled: false,
  };
  activeTypewriter = job;

  return new Promise((resolve) => {
    function step() {
      if (job.cancelled) {
        resolve();
        return;
      }
      if (document.hidden) {
        bubble.textContent = fullText;
        syncChatScrollRange();
        if (activeTypewriter === job) activeTypewriter = null;
        resolve();
        return;
      }
      if (job.index >= fullText.length) {
        if (activeTypewriter === job) activeTypewriter = null;
        resolve();
        return;
      }
      const char = fullText[job.index];
      const delay = /[，。！？；,.!?\n]/.test(char) ? 28 : 12;
      const stepSize = /[，。！？；,.!?\n]/.test(char) ? 1 : 2;
      bubble.textContent += fullText.slice(job.index, job.index + stepSize);
      job.index += stepSize;
      syncChatScrollRange();
      window.setTimeout(step, delay);
    }
    step();
  });
}

function setComposerBusy(isBusy) {
  qs("sendButton").disabled = isBusy;
  qs("messageInput").disabled = isBusy;
  qs("endConversationButton").disabled = isBusy;
}

async function sendMessage() {
  const slot = getActiveSlot();
  const input = qs("messageInput");
  const userText = input.value.trim();
  if (!userText) return;
  if (!state.settings.apiBaseUrl || !state.settings.model) {
    setStatus("请先完成模型配置");
    navigate("config");
    showModal("缺少模型配置", "请先在配置页填写 API URL、API Key 和模型名。");
    return;
  }

  const userMessage = { role: "user", content: userText, createdAt: Date.now() };
  slot.messages.push(userMessage);
  input.value = "";
  renderChat();
  setComposerBusy(true);
  setStatus("正在回复...");

  try {
    const payload = buildChatPayload(slot, userText);
    const rawReply = await callModelAsync(payload.messages);
    const parsed = parseAssistantReply(rawReply);
    const liveNode = buildAssistantLiveNode(parsed.think);
    await typeIntoBubble(liveNode.bubble, parsed.visible || parsed.raw, liveNode.list);
    slot.messages.push({ role: "assistant", content: rawReply, createdAt: Date.now() });
    saveState();
    renderChat({ stickToBottom: false });
    setStatus(payload.worldbookMatches.length ? `已命中 ${payload.worldbookMatches.length} 条世界书` : "就绪");
  } catch (error) {
    const message = error instanceof Error ? error.message : "模型请求失败";
    slot.messages.push({ role: "assistant", content: `出错了：${message}`, createdAt: Date.now() });
    saveState();
    renderChat({ stickToBottom: false });
    setStatus("回复失败");
    showModal("模型请求失败", message);
  } finally {
    setComposerBusy(false);
  }
}

function createFallbackMemory(messages, slot) {
  const persona = getCurrentPersona();
  const firstUser = messages.find((item) => item.role === "user" && String(item.content || "").trim());
  const lastVisible = [...messages]
    .reverse()
    .map((item) => {
      const text = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
      return String(text || "").trim();
    })
    .find(Boolean);
  const visibleText = firstUser && lastVisible
    ? `这段对话从“${String(firstUser.content || "").trim().slice(0, 40)}”开始，最后停在了“${lastVisible.slice(0, 72)}”这样的余韵里。`
    : messages
        .slice(-8)
        .map((item) => {
          const text = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
          const speaker = item.role === "user" ? "我" : persona.name || "角色";
          return `${speaker}：${text}`;
        })
        .join("\n");
  return {
    title: `${persona.name || "角色"}的记忆片段`,
    content: visibleText || "这次对话留下了一点模糊但真实的回忆。",
    tags: sanitizeTags(["memory-fragment", persona.name].filter(Boolean)),
    notes: "由本地回退逻辑生成的记忆片段。",
  };
}

function extractJsonObject(text) {
  const source = String(text || "").trim();
  const block = source.match(/\{[\s\S]*\}/);
  if (!block) return null;
  try {
    return JSON.parse(block[0]);
  } catch {
    return null;
  }
}

function buildConversationTranscript(messages) {
  return (messages || [])
    .map((item) => {
      const text = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
      const content = String(text || "").trim();
      if (!content) return "";
      return `${item.role === "user" ? "用户" : "角色"}：${content}`;
    })
    .filter(Boolean)
    .join("\n");
}

function splitMessagesForSummary(messages, targetChars = SUMMARY_CHUNK_TARGET_CHARS, overlapMessages = SUMMARY_CHUNK_OVERLAP_MESSAGES) {
  const filtered = (messages || []).filter((item) => ["user", "assistant"].includes(item.role) && String(item.content || "").trim());
  if (!filtered.length) return [];
  const chunks = [];
  let start = 0;
  while (start < filtered.length) {
    const chunk = [];
    let size = 0;
    let end = start;
    while (end < filtered.length) {
      const item = filtered[end];
      const text = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
      const itemSize = String(text || "").length + 8;
      if (chunk.length && size + itemSize > targetChars) break;
      chunk.push(item);
      size += itemSize;
      end += 1;
    }
    if (!chunk.length) {
      chunk.push(filtered[start]);
      end = start + 1;
    }
    chunks.push(chunk);
    if (end >= filtered.length) break;
    start = Math.max(start + 1, end - Math.max(0, overlapMessages));
  }
  return chunks;
}

async function buildSummarySourceText(messages) {
  const transcript = buildConversationTranscript(messages);
  if (transcript.length <= SUMMARY_TRANSCRIPT_SOFT_LIMIT_CHARS) {
    return { text: transcript, chunked: false };
  }

  const chunks = splitMessagesForSummary(messages);
  if (chunks.length <= 1) {
    return { text: transcript, chunked: false };
  }

  const outlines = [];
  for (let index = 0; index < chunks.length; index += 1) {
    const chunkTranscript = buildConversationTranscript(chunks[index]);
    const raw = await callModelAsync(
      [
        {
          role: "system",
          content: [
            "你要把一段对话压缩成简短中文要点。",
            "只输出纯文本。",
            "输出 4 到 8 行，每行前面带 - 。",
            "保留长期有效设定、关系变化、承诺、重要情绪、关键转折和未解决线索。",
            "不要角色扮演，不要编造细节。",
          ].join("\n"),
        },
        {
          role: "user",
          content: `这是整段对话的第 ${index + 1}/${chunks.length} 段压缩任务。\n请按时间顺序输出简短要点。\n\n对话内容：\n${chunkTranscript}`,
        },
      ],
      {
        temperature: 0.2,
        timeoutSec: Math.min(120, state.settings.timeoutSec || 90),
      }
    );
    const cleaned = String(raw || "").trim();
    if (cleaned) outlines.push(`[第 ${index + 1} 段]\n${cleaned}`);
  }

  if (!outlines.length) {
    return { text: transcript, chunked: false };
  }

  return {
    text: `下面是按时间顺序整理的整段长对话分段摘要，请把它当作完整对话的压缩稿来理解：\n\n${outlines.join("\n\n")}`,
    chunked: true,
  };
}

async function buildMemorySummaryPrompt(messages, slot) {
  const summarySource = await buildSummarySourceText(messages);
  const castNames = sortedEntries(normalizeRoleCard(getCurrentCardStore().raw).personas, (left, right) => {
    const a = personaSortKey(left);
    const b = personaSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  })
    .map(([, persona]) => String(persona.name || "").trim())
    .filter(Boolean)
    .join("、");
  const deletedMemoryGuard = buildDeletedMemoryGuard(slot.deletedMemories || []);
  let sourceText = summarySource.text;
  if (deletedMemoryGuard) {
    sourceText = `已删除旧记忆：\n${deletedMemoryGuard}\n\n${sourceText}`;
  }
  sourceText = `${summarySource.chunked ? "输入材料是长对话分段压缩稿。" : "输入材料是完整对话原文。"}\n\n${sourceText}`;
  return [
    {
      role: "system",
      content: [
        "你要把这段对话总结成一个严格 JSON 格式的长期记忆片段。",
        "只能输出一个 JSON 对象，不要输出 markdown，不要输出解释，不要包裹代码块。",
        '字段必须且只能包含：title, content, tags, notes。',
        'content 必须覆盖重要事件、关系变化、做出的决定、已经产生的结果，以及还没解决的线索。',
        "content 必须写得具体，通常为 2 到 5 句；对话材料足够时，不要只写一句空泛总结。",
        "title 要能让人一眼看出这段记忆在讲什么。",
        "tags 需要是短标签数组，不要塞成长句。",
        "如果上方包含已删除旧记忆，那些内容不能被重新写回长期记忆。",
        castNames ? `当前角色阵容：${castNames}` : "",
        '请严格按照这个格式输出：{"title":"...","content":"...","tags":["..."],"notes":"..."}',
      ]
        .filter(Boolean)
        .join("\n"),
    },
    { role: "user", content: sourceText },
  ];
}

function parseStrictSummaryJson(text) {
  const source = String(text || "").trim();
  if (!source.startsWith("{") || !source.endsWith("}")) {
    throw new Error("summary is not strict json");
  }
  const parsed = JSON.parse(source);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("summary json must be an object");
  }
  const requiredKeys = ["title", "content", "tags", "notes"];
  const keys = Object.keys(parsed);
  if (requiredKeys.some((key) => !(key in parsed))) {
    throw new Error("summary json missing required keys");
  }
  if (keys.some((key) => !requiredKeys.includes(key))) {
    throw new Error("summary json contains extra keys");
  }
  return parsed;
}

function sanitizeMemorySummaryPayload(payload, fallback) {
  const nextTitle = String(payload?.title || "").trim() || fallback.title;
  const nextContent = String(payload?.content || "").trim();
  const nextNotes = String(payload?.notes || "").trim() || fallback.notes;
  const nextTags = sanitizeTags(payload?.tags || fallback.tags || ["auto-memory", "summary"]);
  const sentenceCount = nextContent.split(/[。！？!?]+/).map((item) => item.trim()).filter(Boolean).length;
  const useFallbackContent = !nextContent || nextContent.length < 36 || sentenceCount < 2;
  return {
    title: nextTitle,
    content: useFallbackContent ? fallback.content : nextContent,
    tags: nextTags.length ? nextTags : sanitizeTags(fallback.tags || ["auto-memory", "summary"]),
    notes: useFallbackContent ? fallback.notes : nextNotes,
  };
}

async function requestConversationSummaryWithModel(messages, slot) {
  const summaryPrompt = await buildMemorySummaryPrompt(messages, slot);
  const firstPass = await callModelAsync(summaryPrompt, {
    temperature: 0.3,
    timeoutSec: Math.min(120, state.settings.timeoutSec || 90),
  });
  try {
    return parseStrictSummaryJson(firstPass);
  } catch {
    const repaired = await callModelAsync(
      [
        {
          role: "system",
          content: [
            "你要把用户提供的文本修复成一个严格 JSON 对象。",
            "只能输出一个 JSON 对象，不要输出解释，不要输出 markdown。",
            "字段必须且只能包含：title, content, tags, notes。",
            "保留原意，但把 content 写得更具体，确保覆盖重要事件、结果和未解决线索。",
          ].join("\n"),
        },
        {
          role: "user",
          content: firstPass,
        },
      ],
      {
        temperature: 0.1,
        timeoutSec: Math.min(120, state.settings.timeoutSec || 90),
      }
    );
    return parseStrictSummaryJson(repaired);
  }
}

function dedupeMemory(memoryList, nextMemory) {
  return !findSimilarMemory(memoryList, nextMemory);
}

async function endConversation() {
  const slot = getActiveSlot();
  if (!slot.messages.length) {
    setStatus("当前没有可归档的对话");
    return;
  }
  slot.temp = Math.max(0, Number(slot.temp ?? 0) || 0) + 1;
  slot.workshopState = sanitizeWorkshopRuntimeState(slot.workshopState);
  slot.workshopState.pendingTemp = slot.temp;
  saveState();
  syncCreativeWorkshopRuntime("chat_round_start");
  renderGlobalChrome();

  let memory = null;
  const fallbackMemory = createFallbackMemory(slot.messages, slot);
  if (state.settings.apiBaseUrl && state.settings.model) {
    try {
      const summaryPayload = await requestConversationSummaryWithModel(slot.messages, slot);
      memory = sanitizeMemorySummaryPayload(
        {
          ...summaryPayload,
          tags: sanitizeTags(summaryPayload.tags || ["memory-fragment", persona.name].filter(Boolean)),
        },
        fallbackMemory
      );
    } catch {
      memory = null;
    }
  }
  if (!memory) memory = fallbackMemory;
  cleanupDeletedMemories(slot);
  if (findSimilarMemory(slot.deletedMemories || [], memory)) {
    slot.messages = [];
    saveState();
    renderRoute(state.activeRoute);
    setStatus(`已清空当前对话，并拦截了已删除记忆的回写：${memory.title || "已跳过"}`);
    return;
  }
  if (dedupeMemory(slot.memories, memory)) {
    slot.memories.unshift(memory);
    cleanupDeletedMemories(slot);
    slot.messages = [];
    saveState();
    renderRoute(state.activeRoute);
    setStatus("已生成记忆片段并清空当前对话");
    return;
  }
  slot.messages = [];
  saveState();
  renderRoute(state.activeRoute);
  setStatus(`这段对话和已有记忆高度相似，已跳过重复写入：${memory.title || "已复用"}`);
}

function downloadText(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 600);
}

function saveTextWithPicker(filename, content, mimeType = "text/plain") {
  if (!window.XuqiNative || typeof window.XuqiNative.saveTextFileAsync !== "function") {
    downloadText(filename, content);
    return Promise.resolve("");
  }
  const requestId = createRequestId();
  return new Promise((resolve, reject) => {
    pendingNativeSaveRequests.set(requestId, { resolve, reject });
    try {
      window.XuqiNative.saveTextFileAsync(filename, mimeType, content, requestId);
    } catch (error) {
      pendingNativeSaveRequests.delete(requestId);
      reject(error instanceof Error ? error : new Error("文件导出失败"));
    }
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const marker = "base64,";
      const index = dataUrl.indexOf(marker);
      if (index === -1) {
        reject(new Error("二进制文件编码失败"));
        return;
      }
      resolve(dataUrl.slice(index + marker.length));
    };
    reader.onerror = () => reject(new Error("二进制文件读取失败"));
    reader.readAsDataURL(blob);
  });
}

async function saveBlobWithPicker(filename, blob, mimeType = "application/octet-stream") {
  if (!window.XuqiNative || typeof window.XuqiNative.saveBinaryFileAsync !== "function") {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 600);
    return "";
  }
  const requestId = createRequestId();
  const base64Content = await blobToBase64(blob);
  return new Promise((resolve, reject) => {
    pendingNativeSaveRequests.set(requestId, { resolve, reject });
    try {
      window.XuqiNative.saveBinaryFileAsync(filename, mimeType, base64Content, requestId);
    } catch (error) {
      pendingNativeSaveRequests.delete(requestId);
      reject(error instanceof Error ? error : new Error("文件导出失败"));
    }
  });
}

function buildNamedJsonFileName(suffix) {
  return `${safeFileName(getCurrentRoleLabel(), "当前角色")}的${suffix}.json`;
}

async function exportMemories() {
  try {
    await saveTextWithPicker(
      buildNamedJsonFileName("记忆"),
      JSON.stringify({ items: sanitizeMemoryList(getActiveSlot().memories || []) }, null, 2),
      "application/json"
    );
    setStatus("记忆已导出。");
  } catch (error) {
    setStatus("记忆导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "记忆导出失败");
  }
}

async function exportMergedMemories() {
  try {
    await saveTextWithPicker(
      buildNamedJsonFileName("合并记忆"),
      JSON.stringify({ items: sanitizeMergedMemoryList(getActiveSlot().mergedMemories || []) }, null, 2),
      "application/json"
    );
    setStatus("合并记忆已导出。");
  } catch (error) {
    setStatus("合并记忆导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "合并记忆导出失败");
  }
}

async function exportMemoryOutline() {
  try {
    await saveTextWithPicker(
      buildNamedJsonFileName("记忆大纲"),
      JSON.stringify({ items: sanitizeMemoryOutlineList(getActiveSlot().memoryOutline || []) }, null, 2),
      "application/json"
    );
    setStatus("记忆大纲已导出。");
  } catch (error) {
    setStatus("记忆大纲导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "记忆大纲导出失败");
  }
}

function showPromptPreview() {
  const userText = qs("messageInput")?.value.trim() || "（当前输入框为空，本预览仅展示系统部分与历史部分）";
  const payload = buildChatPayload(getActiveSlot(), userText, { mutateWorldbookRuntime: false });
  const summary = [
    `system 层数：${payload.systemSectionCount || 0}`,
    `最近聊天轮数：${payload.recentHistoryTurns || 0}`,
    `命中的世界书条数：${payload.worldbookMatches?.length || 0}`,
    `最终 messages 条数：${payload.messageCount || 0}`,
    "",
    payload.previewText || "暂无可预览内容。",
  ].join("\n");
  showModal("当前轮 Prompt 预览", summary);
}

async function importMemories(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = extractJsonObject(text) || JSON.parse(text);
    const memoryList = Array.isArray(parsed)
      ? parsed
      : Array.isArray(parsed?.memories)
        ? parsed.memories
        : Array.isArray(parsed?.items)
          ? parsed.items
          : null;
    if (!memoryList) throw new Error("记忆文件结构无效");
    const runtime = getActiveSlot();
    runtime.memories = sanitizeMemoryList(memoryList);
    if (Array.isArray(parsed?.merged_memories) || Array.isArray(parsed?.mergedMemories)) {
      runtime.mergedMemories = sanitizeMergedMemoryList(parsed.merged_memories || parsed.mergedMemories);
    }
    if (Array.isArray(parsed?.memory_outline) || Array.isArray(parsed?.memoryOutline)) {
      runtime.memoryOutline = sanitizeMemoryOutlineList(parsed.memory_outline || parsed.memoryOutline);
    }
    cleanupDeletedMemories(runtime);
    saveState();
    renderMemory();
    bindDynamicEditors();
    setStatus("记忆已导入。");
  } catch (error) {
    setStatus("记忆导入失败");
    showModal("导入失败", error instanceof Error ? error.message : "记忆文件无法识别。");
  } finally {
    event.target.value = "";
  }
}

async function exportWorldbook() {
  try {
    await saveTextWithPicker(
      buildNamedJsonFileName("世界书"),
      JSON.stringify(exportWorldbookStore(getActiveSlot().worldbook), null, 2),
      "application/json"
    );
    setStatus("世界书已导出。");
  } catch (error) {
    setStatus("世界书导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "世界书导出失败");
  }
}

async function importWorldbook(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = extractJsonObject(text) || JSON.parse(text);
    const slot = getActiveSlot();
    slot.worldbook = sanitizeWorldbookStore(parsed?.worldbook ?? parsed);
    slot.worldbookRuntime = createDefaultWorldbookRuntimeState();
    saveState();
    renderWorldbook();
    bindDynamicEditors();
    setStatus("世界书已导入。");
  } catch (error) {
    setStatus("世界书导入失败");
    showModal("导入失败", error instanceof Error ? error.message : "世界书文件无法识别。");
  } finally {
    event.target.value = "";
  }
}

async function exportCurrentBundle() {
  if (typeof window.JSZip !== "function") {
    showModal("缺少打包器", "当前环境没有加载 ZIP 打包能力，请稍后重试。");
    return;
  }
  const roleLabel = getCurrentRoleLabel();
  const zip = new window.JSZip();
  zip.file(`${roleLabel}的人设卡.json`, JSON.stringify(getCurrentCardStore().raw, null, 2));
  zip.file(`${roleLabel}的记忆.json`, JSON.stringify({ items: sanitizeMemoryList(getActiveSlot().memories || []) }, null, 2));
  zip.file(`${roleLabel}的合并记忆.json`, JSON.stringify({ items: sanitizeMergedMemoryList(getActiveSlot().mergedMemories || []) }, null, 2));
  zip.file(`${roleLabel}的记忆大纲.json`, JSON.stringify({ items: sanitizeMemoryOutlineList(getActiveSlot().memoryOutline || []) }, null, 2));
  zip.file(`${roleLabel}的世界书.json`, JSON.stringify(exportWorldbookStore(getActiveSlot().worldbook), null, 2));
  zip.file(`${roleLabel}的预设.json`, JSON.stringify(getEditingPresetStore(), null, 2));
  zip.file(
    `${roleLabel}的导出说明.txt`,
    [
      `${roleLabel} 当前组合包`,
      "",
      "包含内容：",
      `1. ${roleLabel}的人设卡.json`,
      `2. ${roleLabel}的记忆.json`,
      `3. ${roleLabel}的合并记忆.json`,
      `4. ${roleLabel}的记忆大纲.json`,
      `5. ${roleLabel}的世界书.json`,
      `6. ${roleLabel}的预设.json`,
      "",
      "说明：角色卡独立加载，原记忆 / 合并记忆 / 大纲 / 世界书 / 预设都属于当前全局运行态。",
    ].join("\n")
  );
  try {
    const blob = await zip.generateAsync({ type: "blob" });
    await saveBlobWithPicker(`${safeFileName(`${roleLabel}存档`, "当前角色存档")}.zip`, blob, "application/zip");
    setStatus("当前组合包已导出。");
  } catch (error) {
    setStatus("组合包导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "组合包导出失败");
  }
}

async function exportChatHistory() {
  const slot = getActiveSlot();
  const roleLabel = getCurrentRoleLabel();
  const lines = slot.messages
    .map((item) => {
      const text = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
      const speaker = item.role === "user" ? "用户" : roleLabel;
      return `[${formatTime(item.createdAt)}] ${speaker}\n${text}\n`;
    })
    .join("\n");
  try {
    await saveTextWithPicker(`${safeFileName(roleLabel, "当前角色")}_chat.txt`, lines || "暂无聊天记录");
    setStatus("聊天记录已导出。");
  } catch (error) {
    setStatus("聊天记录导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "聊天记录导出失败");
  }
}

async function exportCurrentCard() {
  flushState();
  const cardStore = getCurrentCardStore();
  try {
    await saveTextWithPicker(
      cardStore.sourceName || "role_card.json",
      JSON.stringify(cardStore.raw, null, 2),
      "application/json"
    );
    setStatus("角色卡已导出。");
  } catch (error) {
    setStatus("角色卡导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "角色卡导出失败");
  }
}

function buildRuntimeBackupPayload() {
  return {
    settings: deepClone(state.settings),
    runtime: deepClone(state.runtime),
  };
}

function extractRuntimeBackupSource(parsed) {
  if (!parsed || typeof parsed !== "object") return null;
  if (parsed.runtime && typeof parsed.runtime === "object") return parsed.runtime;
  if (
    "temp" in parsed
    || "messages" in parsed
    || "memories" in parsed
    || "worldbook" in parsed
    || "presetStore" in parsed
    || "userProfile" in parsed
  ) {
    return parsed;
  }
  const legacySlots = parsed.slots && typeof parsed.slots === "object" ? parsed.slots : null;
  if (!legacySlots) return null;
  return legacySlots[parsed.activeSlot] || legacySlots.slot_1 || Object.values(legacySlots).find((item) => item && typeof item === "object") || null;
}

async function exportState() {
  flushState();
  try {
    await saveTextWithPicker(
      "xuqi_mobile_runtime_backup.json",
      JSON.stringify(buildRuntimeBackupPayload(), null, 2),
      "application/json"
    );
    setStatus("运行态备份已导出。");
  } catch (error) {
    setStatus("运行态备份导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "运行态备份导出失败");
  }
}

function renderConfig() {
  const settings = state.settings;
  const slot = getActiveSlot();
  const persona = getCurrentPersona();
  const presetSelect = qs("presetSelect");
  presetSelect.innerHTML = MODEL_PRESETS.map((item) => {
    const selected = (settings.modelPreset || detectPreset(settings.apiBaseUrl)) === item.id ? "selected" : "";
    return `<option value="${item.id}" ${selected}>${item.label}</option>`;
  }).join("");

  qs("apiBaseUrl").value = settings.apiBaseUrl || "";
  qs("apiKey").value = settings.apiKey || "";
  qs("modelName").value = settings.model || "";
  qs("temperature").value = String(settings.temperature ?? 0.85);
  qs("timeoutSec").value = String(settings.timeoutSec ?? 90);
  qs("historyLimit").value = String(settings.historyLimit ?? 20);
  qs("maxTokens").value = String(settings.maxTokens ?? 0);
  qs("themeSelect").value = settings.theme || "dark";
  qs("uiOpacity").value = String(settings.uiOpacity ?? 0.88);
  qs("backgroundOverlay").value = String(settings.backgroundOverlay ?? 0.36);
  qs("backgroundImageUrl").value = settings.backgroundImageUrl || "";
  qs("uiOpacityValue").textContent = Number(settings.uiOpacity || 0.88).toFixed(2);
  qs("backgroundOverlayValue").textContent = Number(settings.backgroundOverlay || 0.36).toFixed(2);
  qs("embeddingBaseUrl").value = settings.embeddingBaseUrl || "";
  qs("embeddingApiKey").value = settings.embeddingApiKey || "";
  qs("embeddingModel").value = settings.embeddingModel || "";
  qs("retrievalTopK").value = String(settings.retrievalTopK ?? 4);
  qs("rerankEnabled").checked = Boolean(settings.rerankEnabled);
  qs("rerankBaseUrl").value = settings.rerankBaseUrl || "";
  qs("rerankApiKey").value = settings.rerankApiKey || "";
  qs("rerankModel").value = settings.rerankModel || "";
  qs("rerankTopN").value = String(settings.rerankTopN ?? 3);
  document.querySelectorAll(".embedding-field").forEach((node) => {
    node.checked = (settings.embeddingFields || []).includes(node.value);
  });

  qs("personaName").value = persona.name || "";
  qs("personaGreeting").value = persona.greeting || "";
  qs("personaPrompt").value = persona.systemPrompt || "";

  const userProfile = slot.userProfile || createDefaultUserProfile();
  if (qs("userDisplayName")) qs("userDisplayName").value = userProfile.displayName || "";
  if (qs("userNickname")) qs("userNickname").value = userProfile.nickname || "";
  if (qs("userProfileText")) qs("userProfileText").value = userProfile.profileText || "";
  if (qs("userNotes")) qs("userNotes").value = userProfile.notes || "";
  if (qs("userAvatarUrl")) qs("userAvatarUrl").value = userProfile.avatarUrl || "";
  if (qs("userRoleAvatarUrl")) qs("userRoleAvatarUrl").value = userProfile.roleAvatarUrl || "";
  if (qs("userAvatarPreview")) {
    const preview = qs("userAvatarPreview");
    preview.hidden = !userProfile.avatarUrl;
    if (userProfile.avatarUrl) preview.src = userProfile.avatarUrl;
  }
  if (qs("userRoleAvatarPreview")) {
    const preview = qs("userRoleAvatarPreview");
    preview.hidden = !userProfile.roleAvatarUrl;
    if (userProfile.roleAvatarUrl) preview.src = userProfile.roleAvatarUrl;
  }
  const stage = getCurrentGameStage(slot);
  if (qs("runtimeStageText")) {
    const temp = Math.max(0, Number(slot.temp ?? 0) || 0);
    qs("runtimeStageText").textContent = `当前 temp = ${temp}，阶段为 ${stage}。A: 0-${WORKSHOP_STAGE_LIMITS.aMax}，B: ${WORKSHOP_STAGE_LIMITS.aMax + 1}-${WORKSHOP_STAGE_LIMITS.bMax}，C: ${WORKSHOP_STAGE_LIMITS.bMax + 1}+。`;
  }

  const musicPresetSelect = qs("musicPresetSelect");
  musicPresetSelect.innerHTML = MUSIC_PRESETS.map((item) => {
    const selected = (settings.musicPreset || "off") === item.id ? "selected" : "";
    return `<option value="${item.id}" ${selected}>${item.label}</option>`;
  }).join("");
  qs("musicUrlInput").value = settings.musicUrl || "";
}

function createStageNode(key, stage) {
  const node = document.createElement("div");
  node.className = "editor-card";
  node.dataset.stageKey = key;
  node.innerHTML = `
    <details class="editor-fold" open>
      <summary class="editor-summary">
        <strong>${escapeHtml(key)}</strong>
        <button class="ghost-button danger-button icon-action" data-remove-stage="${escapeAttr(key)}" type="button" aria-label="删除阶段">−</button>
      </summary>
      <div class="editor-body">
        <label>description（这一阶段发生了什么）</label>
        <textarea data-stage-desc="${escapeAttr(key)}" rows="4">${escapeHtml(stage.description || "")}</textarea>
        <label>rules（这一阶段的行为规则 / 限制）</label>
        <textarea data-stage-rules="${escapeAttr(key)}" rows="4">${escapeHtml(stage.rules || "")}</textarea>
      </div>
    </details>
  `;
  return node;
}

function createPersonaNode(key, persona) {
  const node = document.createElement("div");
  node.className = "editor-card";
  node.dataset.personaKey = key;
  node.innerHTML = `
    <details class="editor-fold" open>
      <summary class="editor-summary">
        <strong>${escapeHtml(persona.name || `角色 ${key}`)}</strong>
        <button class="ghost-button danger-button icon-action" data-remove-persona="${escapeAttr(key)}" type="button" aria-label="删除角色">−</button>
      </summary>
      <div class="editor-body">
        <label>name（该角色显示名）</label>
        <input data-persona-name="${escapeAttr(key)}" value="${escapeAttr(persona.name || "")}" />
        <label>description（身份 / 背景简介）</label>
        <textarea data-persona-desc="${escapeAttr(key)}" rows="4">${escapeHtml(persona.description || "")}</textarea>
        <label>personality（个性 / 语气倾向）</label>
        <textarea data-persona-personality="${escapeAttr(key)}" rows="4">${escapeHtml(persona.personality || "")}</textarea>
        <label>scenario（该角色所处场景 / 关系定位）</label>
        <textarea data-persona-scenario="${escapeAttr(key)}" rows="4">${escapeHtml(persona.scenario || "")}</textarea>
        <label>creator_notes（仅给模型看的补充说明）</label>
        <textarea data-persona-notes="${escapeAttr(key)}" rows="4">${escapeHtml(persona.creator_notes || "")}</textarea>
      </div>
    </details>
  `;
  return node;
}

function renderCard() {
  const cardStore = getCurrentCardStore();
  const card = normalizeRoleCard(cardStore.raw);
  qs("cardSourceName").value = cardStore.sourceName || "role_card.json";
  qs("cardName").value = card.name || "";
  qs("cardTags").value = (card.tags || []).join(", ");
  qs("cardDescription").value = card.description || "";
  qs("cardPersonality").value = card.personality || "";
  qs("cardScenario").value = card.scenario || "";
  qs("cardFirstMes").value = card.first_mes || "";
  qs("cardMesExample").value = card.mes_example || "";
  qs("cardCreatorNotes").value = card.creator_notes || "";

  const plotStageList = qs("plotStageList");
  plotStageList.innerHTML = "";
  sortedEntries(card.plotStages, (left, right) => {
    const a = stageSortKey(left);
    const b = stageSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  }).forEach(([key, stage]) => {
    plotStageList.appendChild(createStageNode(key, stage));
  });

  const personaGrid = qs("personaCardGrid");
  personaGrid.innerHTML = "";
  sortedEntries(card.personas, (left, right) => {
    const a = personaSortKey(left);
    const b = personaSortKey(right);
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] > b[1]) return 1;
    if (a[1] < b[1]) return -1;
    return 0;
  }).forEach(([key, persona]) => {
    personaGrid.appendChild(createPersonaNode(key, persona));
  });

  const workshop = sanitizeCreativeWorkshop(card.creativeWorkshop);
  if (qs("workshopSummaryText")) {
    const customCount = workshop.items.filter((item) => normalizeWorkshopTriggerMode(item.triggerMode) === "temp").length;
    qs("workshopSummaryText").textContent = workshop.enabled
      ? `当前已启用创意工坊，共有 ${workshop.items.length} 条规则，其中 ${customCount} 条是自定义 Temp 触发。`
      : `当前创意工坊未启用，但角色卡内已配置 ${workshop.items.length} 条规则。`;
  }
}

function renderWorkshopSettings() {
  const slot = getActiveSlot();
  const card = normalizeRoleCard(getCurrentCardStore().raw);
  const workshop = sanitizeCreativeWorkshop(card.creativeWorkshop);
  if (qs("workshopEnabled")) qs("workshopEnabled").checked = Boolean(workshop.enabled);
  if (qs("workshopRuntimeInfo")) {
    const temp = Math.max(0, Number(slot.temp ?? 0) || 0);
    const stage = getCurrentGameStage(slot);
    qs("workshopRuntimeInfo").textContent = `当前 temp = ${temp}，阶段为 ${stage}。PC 端已有的 A/B/C 阶段触发和自定义 Temp 区间触发，在这里都会按同样规则生效。`;
  }
  renderWorkshopRules();
}

function addWorkshopRuleToCurrentCard() {
  const cardStore = getCurrentCardStore();
  const card = normalizeRoleCard(cardStore.raw);
  card.creativeWorkshop = sanitizeCreativeWorkshop(card.creativeWorkshop);
  card.creativeWorkshop.enabled = true;
  const nextIndex = card.creativeWorkshop.items.filter((item) => !String(item.id || "").startsWith("workshop_stage_")).length + 1;
  const currentTemp = Math.max(0, Number(getActiveSlot()?.temp ?? 0) || 0);
  card.creativeWorkshop.items.push({
    ...createDefaultCreativeWorkshopItem(),
    id: `workshop-item-${Date.now().toString(36)}`,
    name: `新规则 ${nextIndex}`,
    enabled: true,
    triggerMode: "temp",
    triggerTempMin: currentTemp,
    triggerTempMax: currentTemp,
  });
  cardStore.raw = card;
  saveState();
  renderWorkshopSettings();
  bindDynamicEditors();
  const search = qs("workshopRuleSearch");
  if (search && search.value.trim()) {
    search.value = "";
    applyWorkshopRuleSearch();
  }
  window.requestAnimationFrame(() => {
    const list = qs("workshopRuleList");
    const last = list?.querySelector(".workshop-rule-card:last-of-type");
    last?.scrollIntoView({ block: "end", behavior: "smooth" });
  });
  setStatus("已新增创意工坊规则。");
  return false;
}

function setAllWorkshopRulesCollapsed(collapsed) {
  const list = qs("workshopRuleList");
  if (!list) return false;
  list.querySelectorAll(".workshop-rule-card").forEach((node) => {
    const details = node.querySelector("details");
    if (details) setWorkshopRuleCollapsed(details, collapsed);
  });
  setStatus(collapsed ? "已折叠全部创意工坊规则。" : "已展开全部创意工坊规则。");
  return false;
}

function normalizeMemorySearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function getMemorySearchText(card) {
  return [
    card.querySelector(".memory-title")?.value || "",
    card.querySelector(".memory-content")?.value || "",
    card.querySelector(".memory-tags")?.value || "",
    card.querySelector(".memory-notes")?.value || "",
  ].join("\n").toLowerCase();
}

function setMemoryCollapsed(card, collapsed) {
  const body = card.querySelector(".memory-card-body");
  const toggleBtn = card.querySelector(".toggle-memory");
  card.dataset.collapsed = collapsed ? "true" : "false";
  card.open = !collapsed;
  if (body) body.style.display = collapsed ? "none" : "";
  if (toggleBtn) toggleBtn.textContent = collapsed ? "展开" : "折叠";
}

function applyMemorySearch() {
  const keyword = normalizeMemorySearchText(qs("memorySearch")?.value || "");
  const cards = [...qs("memoryList").querySelectorAll(".memory-card")];
  let visibleCount = 0;
  for (const card of cards) {
    const matched = !keyword || getMemorySearchText(card).includes(keyword);
    card.style.display = matched ? "" : "none";
    if (matched) visibleCount += 1;
  }
  if (keyword) {
    setStatus(`搜索完成：找到${visibleCount} 条匹配记忆。`);
  }
  updateMemoryStats();
}

function updateMemoryStats() {
  const slot = getActiveSlot();
  if (qs("memoryCount")) qs("memoryCount").textContent = String((slot.memories || []).length);
  if (qs("mergedMemoryCount")) qs("mergedMemoryCount").textContent = String((slot.mergedMemories || []).length);
  if (qs("memoryOutlineCount")) qs("memoryOutlineCount").textContent = String((slot.memoryOutline || []).length);
  if (qs("selectedMemoryCount")) {
    qs("selectedMemoryCount").textContent = String(qs("memoryList")?.querySelectorAll("[data-memory-selected]:checked").length || 0);
  }
}

function getSelectedMemoryIndexes() {
  return [...(qs("memoryList")?.querySelectorAll("[data-memory-selected]:checked") || [])]
    .map((input) => Number(input.dataset.memorySelected))
    .filter((index) => Number.isFinite(index));
}

function compactMemoryText(value, limit) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 3)).trim()}...`;
}

function buildMemoryMergePrompt(selectedMemories, { mergedTitle = "", outlineTitle = "" } = {}) {
  const memoryText = selectedMemories
    .map((item, index) =>
      [
        `[Memory ${index + 1}]`,
        `id: ${item.id || ""}`,
        `title: ${item.title || ""}`,
        `tags: ${(item.tags || []).join(", ")}`,
        `content: ${item.content || ""}`,
        `notes: ${item.notes || ""}`,
      ].join("\n")
    )
    .join("\n\n");
  return [
    "请把下面多条长期记忆合并成一条新的“合并记忆”，并同时生成一条“大纲表项”。",
    "必须只输出一个严格 JSON 对象，不要输出 markdown，不要解释。",
    "JSON 必须包含 exactly two top-level keys: merged_memory and outline_item。",
    "",
    "merged_memory 字段：title, content, tags, notes。",
    "outline_item 字段：title, summary, characters, relationship_progress, key_events, conflicts, next_hooks, notes。",
    "",
    `合并记忆标题优先参考：${mergedTitle || "请根据内容自动拟定"}`,
    `大纲表标题优先参考：${outlineTitle || "请根据内容自动拟定"}`,
    "",
    "要求：保留事实、去重、不要虚构原记忆中没有的信息，key_events 列关键事件。",
    "",
    "待合并记忆：",
    memoryText,
  ].join("\n");
}

function parseMemoryMergeJson(text) {
  const parsed = extractJsonObject(text) || JSON.parse(String(text || "").trim());
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("合并结果不是 JSON 对象");
  }
  if (!parsed.merged_memory || !parsed.outline_item) {
    throw new Error("合并结果缺少 merged_memory 或 outline_item");
  }
  return parsed;
}

function buildFallbackMemoryMergePayload(selectedMemories, { mergedTitle = "", outlineTitle = "" } = {}) {
  const titles = selectedMemories.map((item) => String(item.title || "").trim()).filter(Boolean);
  const tags = sanitizeTags(selectedMemories.flatMap((item) => item.tags || []));
  const parts = selectedMemories
    .map((item) => {
      const title = String(item.title || "未命名记忆").trim();
      const content = compactMemoryText(item.content, 260);
      return content ? `${title}：${content}` : title;
    })
    .filter(Boolean);
  const notes = selectedMemories
    .map((item) => {
      const title = String(item.title || "未命名记忆").trim();
      const note = compactMemoryText(item.notes, 180);
      return note ? `${title}备注：${note}` : "";
    })
    .filter(Boolean);
  const mergedContent = parts.join("；") || "这是一条由多条原记忆合并生成的新记忆。";
  return {
    merged_memory: {
      title: (mergedTitle || titles[0] || `合并记忆 ${formatLocalTimestamp()}`).slice(0, 80),
      content: mergedContent.slice(0, 1200),
      tags: (tags.length ? tags : ["merged-memory", "summary"]).slice(0, 8),
      notes: notes.join("\n").slice(0, 1200),
    },
    outline_item: {
      title: (outlineTitle || mergedTitle || titles[0] || "记忆大纲").slice(0, 100),
      summary: (`本批记忆主要围绕：${selectedMemories.map((item) => compactMemoryText(item.content, 100)).filter(Boolean).join("；")}`).slice(0, 900),
      characters: "",
      relationship_progress: "",
      key_events: titles.slice(0, 10),
      conflicts: "",
      next_hooks: "",
      notes: "该大纲项由本地回退逻辑生成，未使用模型结构化总结。",
    },
  };
}

async function requestMemoryMergeWithModel(selectedMemories, options) {
  const prompt = buildMemoryMergePrompt(selectedMemories, options);
  const firstPass = await callModelAsync(
    [
      {
        role: "system",
        content:
          "You are a long-term memory merger and outline formatter. Return one strict JSON object only. The JSON object must contain exactly two top-level keys: merged_memory and outline_item.",
      },
      { role: "user", content: prompt },
    ],
    { temperature: 0.2, timeoutSec: Math.min(120, state.settings.timeoutSec || 90) }
  );
  try {
    return parseMemoryMergeJson(firstPass);
  } catch {
    const repaired = await callModelAsync(
      [
        {
          role: "system",
          content:
            "Convert the provided content into one strict JSON object only. Do not output markdown or explanation. The object must contain exactly two top-level keys: merged_memory and outline_item.",
        },
        { role: "user", content: `Repair this content into strict JSON:\n${firstPass}` },
      ],
      { temperature: 0, timeoutSec: Math.min(120, state.settings.timeoutSec || 90) }
    );
    return parseMemoryMergeJson(repaired);
  }
}

function buildFinalMergedMemory(payload, selectedMemories, mergedTitle = "") {
  const data = payload?.merged_memory && typeof payload.merged_memory === "object" ? payload.merged_memory : {};
  const sourceIds = selectedMemories.map((item) => String(item.id || "").trim()).filter(Boolean);
  const sourceNote = sourceIds.length ? `由 ${sourceIds.length} 条原记忆合并生成` : "";
  const notes = [sourceNote, data.notes].map((item) => String(item || "").trim()).filter(Boolean).join("\n");
  return sanitizeMergedMemoryItem(
    {
      id: `merged-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      title: mergedTitle || data.title || "合并记忆",
      content: data.content || "",
      tags: data.tags || ["merged-memory", "summary"],
      notes,
      source_memory_ids: sourceIds,
      created_at: formatLocalTimestamp(),
    },
    1
  );
}

function buildFinalOutlineItem(payload, selectedMemories, mergedMemoryId, outlineTitle = "") {
  const data = payload?.outline_item && typeof payload.outline_item === "object" ? payload.outline_item : {};
  const sourceIds = selectedMemories.map((item) => String(item.id || "").trim()).filter(Boolean);
  return sanitizeMemoryOutlineItem(
    {
      id: `outline-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      title: outlineTitle || data.title || "记忆大纲",
      summary: data.summary || "",
      characters: data.characters || "",
      relationship_progress: data.relationship_progress || data.relationshipProgress || "",
      key_events: data.key_events || data.keyEvents || [],
      conflicts: data.conflicts || "",
      next_hooks: data.next_hooks || data.nextHooks || "",
      notes: data.notes || "",
      source_memory_ids: sourceIds,
      merged_memory_id: mergedMemoryId,
      updated_at: formatLocalTimestamp(),
    },
    1
  );
}

function renderMergedMemoryList() {
  const list = qs("mergedMemoryList");
  if (!list) return;
  const items = sanitizeMergedMemoryList(getActiveSlot().mergedMemories || []);
  getActiveSlot().mergedMemories = items;
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = '<div class="empty-tip">还没有合并后的记忆。先在上方原记忆区勾选两条以上，再执行合并。</div>';
    return;
  }
  items.forEach((item) => {
    const node = document.createElement("article");
    node.className = "merged-card";
    const sourceCount = Array.isArray(item.source_memory_ids) ? item.source_memory_ids.length : 0;
    node.innerHTML = `
      <h3>${escapeHtml(item.title || "未命名合并记忆")}</h3>
      <div class="merged-meta">
        <span class="merged-badge">${escapeHtml(String(item.created_at || "").slice(0, 16))}</span>
        <span class="merged-badge">来源 ${sourceCount} 条</span>
        ${(item.tags || []).map((tag) => `<span class="merged-badge">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="merged-content">${escapeHtml(item.content || "")}</div>
      ${item.notes ? `<div class="merged-notes">${escapeHtml(item.notes)}</div>` : ""}
    `;
    list.appendChild(node);
  });
}

function renderMemoryOutlineDetail(item) {
  const panel = qs("memoryOutlineDetail");
  if (!panel) return;
  if (!item) {
    panel.innerHTML = '<div class="outline-detail-empty">先完成一次记忆合并，或点击上方某一行查看详情。</div>';
    return;
  }
  const events = Array.isArray(item.key_events) ? item.key_events : [];
  panel.innerHTML = `
    <div class="outline-detail-head">
      <div>
        <h3>${escapeHtml(item.title || "未命名大纲")}</h3>
        <div class="outline-submeta">来源 ${Array.isArray(item.source_memory_ids) ? item.source_memory_ids.length : 0} 条原记忆</div>
      </div>
      <div class="outline-detail-time">${escapeHtml(String(item.updated_at || "").slice(0, 16))}</div>
    </div>
    <div class="outline-detail-grid">
      <div class="outline-detail-block full"><strong>摘要</strong><div class="outline-detail-text">${escapeHtml(item.summary || "")}</div></div>
      <div class="outline-detail-block"><strong>涉及角色</strong><div class="outline-detail-text">${escapeHtml(item.characters || "-")}</div></div>
      <div class="outline-detail-block"><strong>关系推进</strong><div class="outline-detail-text">${escapeHtml(item.relationship_progress || "-")}</div></div>
      <div class="outline-detail-block full">
        <strong>关键事件</strong>
        ${events.length ? `<ul class="outline-detail-list">${events.map((event) => `<li>${escapeHtml(event)}</li>`).join("")}</ul>` : '<div class="outline-detail-text">-</div>'}
      </div>
      <div class="outline-detail-block"><strong>矛盾点</strong><div class="outline-detail-text">${escapeHtml(item.conflicts || "-")}</div></div>
      <div class="outline-detail-block"><strong>后续钩子</strong><div class="outline-detail-text">${escapeHtml(item.next_hooks || "-")}</div></div>
      <div class="outline-detail-block full"><strong>备注</strong><div class="outline-detail-text">${escapeHtml(item.notes || "-")}</div></div>
    </div>
  `;
}

function renderMemoryOutlineTable(activeId = "") {
  const body = qs("memoryOutlineTableBody");
  if (!body) return;
  const items = sanitizeMemoryOutlineList(getActiveSlot().memoryOutline || []);
  getActiveSlot().memoryOutline = items;
  body.innerHTML = "";
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5"><div class="empty-tip">还没有大纲表项。完成一次记忆合并后，这里会出现总览表格。</div></td></tr>';
    renderMemoryOutlineDetail(null);
    return;
  }
  const selectedId = activeId || items[items.length - 1]?.id || items[0]?.id || "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.dataset.outlineId = item.id;
    row.classList.toggle("active", item.id === selectedId);
    row.innerHTML = `
      <td class="outline-time">${escapeHtml(String(item.updated_at || "").slice(0, 16))}</td>
      <td><div class="outline-title-main">${escapeHtml(item.title || "未命名大纲")}</div><div class="outline-submeta">来源 ${(item.source_memory_ids || []).length} 条</div></td>
      <td>${escapeHtml(item.characters || "-")}</td>
      <td>${escapeHtml(item.relationship_progress || "-")}</td>
      <td class="outline-events-inline">${escapeHtml((item.key_events || []).join(" / ") || "-")}</td>
    `;
    row.addEventListener("click", () => {
      body.querySelectorAll("tr").forEach((node) => node.classList.remove("active"));
      row.classList.add("active");
      renderMemoryOutlineDetail(item);
    });
    body.appendChild(row);
  });
  renderMemoryOutlineDetail(items.find((item) => item.id === selectedId) || items[items.length - 1] || null);
}

async function mergeSelectedMemories() {
  const slot = getActiveSlot();
  slot.memories = sanitizeMemoryList(slot.memories || []);
  const indexes = getSelectedMemoryIndexes();
  const selectedMemories = indexes.map((index) => slot.memories[index]).filter(Boolean);
  if (selectedMemories.length < 2) {
    showModal("无法合并", "请至少勾选两条原记忆再执行合并。");
    setStatus("记忆合并需要至少两条原记忆。");
    return;
  }

  const button = qs("mergeSelectedMemoriesButton");
  const modeText = qs("memoryMergeModeText");
  const mergedTitle = qs("mergedMemoryTitleInput")?.value.trim() || "";
  const outlineTitle = qs("memoryOutlineTitleInput")?.value.trim() || "";
  const deleteSources = qs("deleteMergedMemorySources")?.checked !== false;
  if (button) button.disabled = true;
  if (modeText) modeText.textContent = `正在处理 ${selectedMemories.length} 条原记忆...`;
  setStatus("正在合并记忆并生成大纲...");

  let mode = "fallback";
  try {
    let payload = null;
    try {
      if (state.settings.apiBaseUrl && state.settings.model) {
        payload = await requestMemoryMergeWithModel(selectedMemories, { mergedTitle, outlineTitle });
        mode = "model";
      }
    } catch (error) {
      console.warn("Memory merge model call failed, fallback engaged:", error);
    }
    if (!payload) payload = buildFallbackMemoryMergePayload(selectedMemories, { mergedTitle, outlineTitle });

    const mergedMemory = buildFinalMergedMemory(payload, selectedMemories, mergedTitle);
    const outlineItem = buildFinalOutlineItem(payload, selectedMemories, mergedMemory.id, outlineTitle);
    slot.mergedMemories = [...sanitizeMergedMemoryList(slot.mergedMemories || []), mergedMemory];
    slot.memoryOutline = [...sanitizeMemoryOutlineList(slot.memoryOutline || []), outlineItem];

    if (deleteSources) {
      const selectedIds = new Set(selectedMemories.map((item) => item.id));
      slot.memories = slot.memories.filter((item) => !selectedIds.has(item.id));
      selectedMemories.forEach((item) => recordDeletedMemory(slot, item));
    }

    if (qs("mergedMemoryTitleInput")) qs("mergedMemoryTitleInput").value = "";
    if (qs("memoryOutlineTitleInput")) qs("memoryOutlineTitleInput").value = "";
    cleanupDeletedMemories(slot);
    saveState();
    renderMemory(outlineItem.id);
    bindDynamicEditors();
    if (modeText) modeText.textContent = mode === "model" ? "模型合并完成" : "本地回退合并完成";
    setStatus(`生成完成：${outlineItem.title || "记忆大纲"}（${mode === "model" ? "模型" : "本地回退"}）。`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "记忆合并失败";
    setStatus(`记忆合并失败：${message}`);
    showModal("记忆合并失败", message);
  } finally {
    if (button) button.disabled = false;
  }
}

function renderMemory(activeOutlineId = "") {
  const list = qs("memoryList");
  const slot = getActiveSlot();
  slot.memories = sanitizeMemoryList(slot.memories || []);
  list.innerHTML = "";
  slot.memories.forEach((memory, index) => {
    const node = document.createElement("div");
    node.className = "editor-card memory-card";
    const summaryTitle = memory.title || `记忆 ${index + 1}`;
    const summarySource = memory.content || memory.notes || (memory.tags || []).join(", ") || "点击展开编辑这段记忆";
    const summarySnippet = summarySource.replace(/\s+/g, " ").trim().slice(0, 42);
    node.innerHTML = `
      <details class="editor-fold" open data-collapsed="false">
        <summary class="editor-summary">
          <div class="editor-summary-copy">
            <strong>${escapeHtml(summaryTitle)}</strong>
            <span class="muted compact">${escapeHtml(summarySnippet || "点击展开编辑这段记忆")}</span>
          </div>
          <div class="editor-summary-actions">
            <label class="checkbox-row compact-check"><input data-memory-selected="${index}" type="checkbox" /> 选择</label>
            <button class="ghost-button icon-action toggle-memory" data-toggle-memory="${index}" type="button" aria-label="折叠记忆">折叠</button>
            <button class="ghost-button danger-button icon-action" data-remove-memory="${index}" type="button" aria-label="删除记忆">-</button>
          </div>
        </summary>
        <div class="editor-body memory-card-body">
          <label>标题</label>
          <input data-memory-title="${index}" value="${escapeAttr(memory.title || "")}" />
          <label>正文（建议写成记忆片段）</label>
          <textarea data-memory-content="${index}" rows="5">${escapeHtml(memory.content || "")}</textarea>
          <label>标签（逗号分隔）</label>
          <input data-memory-tags="${index}" value="${escapeAttr((memory.tags || []).join(", "))}" />
          <label>备注</label>
          <textarea data-memory-notes="${index}" rows="3">${escapeHtml(memory.notes || "")}</textarea>
          <input data-memory-id="${index}" type="hidden" value="${escapeAttr(memory.id || "")}" />
        </div>
      </details>
    `;
    list.appendChild(node);
    setMemoryCollapsed(node.querySelector("details"), false);
  });
  applyMemorySearch();
  renderMergedMemoryList();
  renderMemoryOutlineTable(activeOutlineId);
  updateMemoryStats();
}

function normalizeWorldbookSearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function getWorldbookSearchText(card) {
  return [
    card.querySelector(".worldbook-title")?.value || "",
    card.querySelector(".worldbook-group")?.value || "",
    card.querySelector("[data-worldbook-entry-type]")?.value || "",
    card.querySelector("[data-worldbook-insertion-position]")?.value || "",
    card.querySelector("[data-worldbook-injection-role]")?.value || "",
    card.querySelector(".worldbook-primary")?.value || "",
    card.querySelector(".worldbook-secondary")?.value || "",
    card.querySelector(".worldbook-content")?.value || "",
    card.querySelector(".worldbook-notes")?.value || "",
  ].join("\n").toLowerCase();
}

function setWorldbookCollapsed(card, collapsed) {
  const body = card.querySelector(".worldbook-card-body");
  const toggleBtn = card.querySelector(".toggle-worldbook");
  card.dataset.collapsed = collapsed ? "true" : "false";
  card.open = !collapsed;
  if (body) body.style.display = collapsed ? "none" : "";
  if (toggleBtn) toggleBtn.textContent = collapsed ? "展开" : "折叠";
}

function applyWorldbookSearch() {
  const keyword = normalizeWorldbookSearchText(qs("worldbookSearch")?.value || "");
  const cards = [...qs("worldbookList").querySelectorAll(".worldbook-card")];
  let visibleCount = 0;
  for (const card of cards) {
    const matched = !keyword || getWorldbookSearchText(card).includes(keyword);
    card.style.display = matched ? "" : "none";
    if (matched) visibleCount += 1;
  }
  if (keyword) {
    setStatus(`搜索完成：找到${visibleCount} 条匹配词条。`);
  }
}

function updateSelectedWorldbookCount() {
  const selected = qs("worldbookList")?.querySelectorAll("[data-worldbook-selected]:checked").length || 0;
  const target = qs("selectedWorldbookCount");
  if (target) target.textContent = `已选择 ${selected} 条`;
}

function getSelectedWorldbookIndexes({ visibleOnly = false } = {}) {
  const cards = [...(qs("worldbookList")?.querySelectorAll(".worldbook-card") || [])];
  return cards
    .filter((card) => !visibleOnly || card.style.display !== "none")
    .map((card) => card.querySelector("[data-worldbook-selected]"))
    .filter((input) => input && input.checked)
    .map((input) => Number(input.dataset.worldbookSelected))
    .filter((index) => Number.isFinite(index));
}

function syncWorldbookInjectionUi(scope) {
  const container = scope || qs("worldbookList");
  if (!container) return;
  const cards = container.matches?.(".worldbook-card")
    ? [container]
    : [...container.querySelectorAll(".worldbook-card")];
  cards.forEach((card) => {
    const position = card.querySelector("[data-worldbook-insertion-position]")?.value || "after_char_defs";
    const depth = card.querySelector("[data-worldbook-injection-depth]");
    const role = card.querySelector("[data-worldbook-injection-role]");
    const inChat = position === "in_chat";
    if (depth) depth.disabled = !inChat;
    if (role) role.disabled = !inChat;
  });
}

function createWorldbookNode(entry, index) {
  const node = document.createElement("div");
  node.className = "editor-card worldbook-card";
  const summaryTitle = entry.title || `词条 ${index + 1}`;
  const summarySource = entry.content || entry.primaryTriggers || entry.secondaryTriggers || entry.notes || "点击展开编辑这条世界书";
  const summarySnippet = String(summarySource).replace(/\s+/g, " ").trim().slice(0, 42);
  const entryType = normalizeWorldbookEntryType(entry.entryType, "keyword");
  const groupOperator = normalizeWorldbookGroupOperator(entry.groupOperator, "and");
  const insertionPosition = normalizeWorldbookInsertionPosition(entry.insertionPosition, "after_char_defs");
  const injectionRole = normalizeWorldbookInjectionRole(entry.injectionRole, "system");
  node.innerHTML = `
    <details class="editor-fold" open data-collapsed="false">
      <summary class="editor-summary">
        <div class="editor-summary-copy">
          <strong>${escapeHtml(summaryTitle)}</strong>
          <span class="muted compact">${escapeHtml(summarySnippet || "点击展开编辑这条世界书")}</span>
        </div>
        <div class="editor-summary-actions">
          <label class="checkbox-row compact-check"><input data-worldbook-selected="${index}" type="checkbox" /> 选择</label>
          <button class="ghost-button icon-action toggle-worldbook" data-toggle-worldbook="${index}" type="button" aria-label="折叠词条">折叠</button>
          <button class="ghost-button danger-button icon-action" data-remove-worldbook="${index}" type="button" aria-label="删除词条">−</button>
        </div>
      </summary>
      <div class="editor-body worldbook-card-body">
        <label>标题</label>
        <input class="worldbook-title" data-worldbook-title="${index}" value="${escapeAttr(entry.title || "")}" />
        <label>分组</label>
        <input class="worldbook-group" data-worldbook-group="${index}" value="${escapeAttr(entry.group || "")}" />
        <div class="two-col">
          <div>
            <label>词条类型</label>
            <select data-worldbook-entry-type="${index}">
              <option value="keyword" ${entryType === "keyword" ? "selected" : ""}>关键词触发</option>
              <option value="constant" ${entryType === "constant" ? "selected" : ""}>常驻注入</option>
            </select>
          </div>
          <div>
            <label>主 / 辅触发关系</label>
            <select data-worldbook-group-operator="${index}">
              <option value="and" ${groupOperator === "and" ? "selected" : ""}>同时满足</option>
              <option value="or" ${groupOperator === "or" ? "selected" : ""}>满足其一</option>
            </select>
          </div>
        </div>
        <label>主触发词（逗号分隔）</label>
        <input class="worldbook-primary" data-worldbook-primary="${index}" value="${escapeAttr(entry.primaryTriggers || "")}" />
        <label>辅助触发词（逗号分隔）</label>
        <input class="worldbook-secondary" data-worldbook-secondary="${index}" value="${escapeAttr(entry.secondaryTriggers || "")}" />
        <label>设定文本</label>
        <textarea class="worldbook-content" data-worldbook-content="${index}" rows="5">${escapeHtml(entry.content || "")}</textarea>
        <div class="two-col">
          <div>
            <label>顺序（越小越先）</label>
            <input data-worldbook-order="${index}" type="number" min="0" max="999999" step="1" value="${escapeAttr(entry.order ?? entry.priority ?? 100)}" />
          </div>
          <div>
            <label>主触发逻辑</label>
            <select data-worldbook-mode="${index}">
              <option value="any" ${entry.matchMode === "all" ? "" : "selected"}>任意命中</option>
              <option value="all" ${entry.matchMode === "all" ? "selected" : ""}>全部命中</option>
            </select>
          </div>
        </div>
        <div class="two-col">
          <div>
            <label>辅助触发逻辑</label>
            <select data-worldbook-secondary-mode="${index}">
              <option value="any" ${entry.secondaryMode === "any" ? "selected" : ""}>任意命中</option>
              <option value="all" ${entry.secondaryMode === "all" ? "selected" : ""}>全部命中</option>
            </select>
          </div>
          <div>
            <label>触发概率</label>
            <input data-worldbook-chance="${index}" type="number" min="0" max="100" step="1" value="${escapeAttr(entry.chance ?? 100)}" />
          </div>
        </div>
        <div class="two-col">
          <div>
            <label>黏着轮数</label>
            <input data-worldbook-sticky-turns="${index}" type="number" min="0" max="999" step="1" value="${escapeAttr(entry.stickyTurns ?? 0)}" />
          </div>
          <div>
            <label>冷却轮数</label>
            <input data-worldbook-cooldown-turns="${index}" type="number" min="0" max="999" step="1" value="${escapeAttr(entry.cooldownTurns ?? 0)}" />
          </div>
        </div>
        <div class="two-col">
          <div>
            <label>注入位置</label>
            <select data-worldbook-insertion-position="${index}">
              <option value="before_char_defs" ${insertionPosition === "before_char_defs" ? "selected" : ""}>角色卡前</option>
              <option value="after_char_defs" ${insertionPosition === "after_char_defs" ? "selected" : ""}>角色卡后</option>
              <option value="in_chat" ${insertionPosition === "in_chat" ? "selected" : ""}>聊天中</option>
            </select>
          </div>
          <div>
            <label>聊天深度</label>
            <input data-worldbook-injection-depth="${index}" type="number" min="0" max="3" step="1" value="${escapeAttr(entry.injectionDepth ?? 0)}" />
          </div>
        </div>
        <div class="two-col">
          <div>
            <label>注入角色</label>
            <select data-worldbook-injection-role="${index}">
              <option value="system" ${injectionRole === "system" ? "selected" : ""}>system</option>
              <option value="user" ${injectionRole === "user" ? "selected" : ""}>user</option>
              <option value="assistant" ${injectionRole === "assistant" ? "selected" : ""}>assistant</option>
            </select>
          </div>
          <div>
            <label>注入排序</label>
            <input data-worldbook-injection-order="${index}" type="number" min="0" max="999999" step="1" value="${escapeAttr(entry.injectionOrder ?? entry.order ?? 100)}" />
          </div>
        </div>
        <label class="checkbox-row"><input data-worldbook-enabled="${index}" type="checkbox" ${entry.enabled !== false ? "checked" : ""} /> 启用该词条</label>
        <label class="checkbox-row"><input data-worldbook-case-sensitive="${index}" type="checkbox" ${entry.caseSensitive ? "checked" : ""} /> 区分大小写</label>
        <label class="checkbox-row"><input data-worldbook-wholeword="${index}" type="checkbox" ${entry.wholeWord ? "checked" : ""} /> 完整词匹配</label>
        <label class="checkbox-row"><input data-worldbook-recursive-enabled="${index}" type="checkbox" ${entry.recursiveEnabled !== false ? "checked" : ""} /> 可被递归触发</label>
        <label class="checkbox-row"><input data-worldbook-prevent-recursion="${index}" type="checkbox" ${entry.preventFurtherRecursion ? "checked" : ""} /> 命中后阻止继续递归</label>
        <label>备注</label>
        <textarea class="worldbook-notes" data-worldbook-notes="${index}" rows="3">${escapeHtml(entry.notes || "")}</textarea>
      </div>
    </details>
  `;
  setWorldbookCollapsed(node.querySelector("details"), false);
  return node;
}


function renderWorldbook() {
  const slot = getActiveSlot();
  slot.worldbook = sanitizeWorldbookStore(slot.worldbook);
  const { settings, entries } = slot.worldbook;
  qs("worldbookEnabled").checked = Boolean(settings.enabled);
  qs("worldbookDebugEnabled").checked = Boolean(settings.debugEnabled);
  qs("worldbookMaxEntries").value = String(settings.maxEntries ?? 3);
  qs("worldbookDefaultMatchMode").value = settings.defaultMatchMode || "any";
  qs("worldbookDefaultSecondaryMode").value = settings.defaultSecondaryMode || "all";
  qs("worldbookDefaultEntryType").value = settings.defaultEntryType || "keyword";
  qs("worldbookDefaultGroupOperator").value = settings.defaultGroupOperator || "and";
  qs("worldbookDefaultChance").value = String(settings.defaultChance ?? 100);
  qs("worldbookDefaultStickyTurns").value = String(settings.defaultStickyTurns ?? 0);
  qs("worldbookDefaultCooldownTurns").value = String(settings.defaultCooldownTurns ?? 0);
  qs("worldbookDefaultInsertionPosition").value = settings.defaultInsertionPosition || "after_char_defs";
  qs("worldbookDefaultInjectionDepth").value = String(settings.defaultInjectionDepth ?? 0);
  qs("worldbookDefaultInjectionRole").value = settings.defaultInjectionRole || "system";
  qs("worldbookDefaultInjectionOrder").value = String(settings.defaultInjectionOrder ?? 100);
  qs("worldbookRecursiveScanEnabled").checked = Boolean(settings.recursiveScanEnabled);
  qs("worldbookRecursionMaxDepth").value = String(settings.recursionMaxDepth ?? 2);
  qs("worldbookCaseSensitive").checked = Boolean(settings.caseSensitive);
  qs("worldbookWholeWord").checked = Boolean(settings.wholeWord);

  const list = qs("worldbookList");
  list.innerHTML = "";
  entries.forEach((entry, index) => list.appendChild(createWorldbookNode(entry, index)));
  applyWorldbookSearch();
  syncWorldbookInjectionUi(list);
  updateSelectedWorldbookCount();
}

function normalizeWorkshopSearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function getWorkshopSearchText(card) {
  return [
    card.querySelector(".workshop-rule-name")?.value || "",
    card.querySelector(".workshop-rule-popup-title")?.value || "",
    card.querySelector(".workshop-rule-trigger-mode")?.value || "",
    card.querySelector(".workshop-rule-trigger")?.value || "",
    card.querySelector(".workshop-rule-trigger-temp-min")?.value || "",
    card.querySelector(".workshop-rule-trigger-temp-max")?.value || "",
    card.querySelector(".workshop-rule-action")?.value || "",
    card.querySelector(".workshop-rule-note")?.value || "",
    card.querySelector(".workshop-rule-url")?.value || "",
    card.querySelector(".workshop-rule-image-url")?.value || "",
  ]
    .join("\n")
    .toLowerCase();
}

function getWorkshopStageLabel(stage) {
  const mapping = {
    LOAD: "加载时",
    ANY: "任意阶段",
    A: "A 阶段",
    B: "B 阶段",
    C: "C 阶段",
  };
  return mapping[stage] || stage || "A 阶段";
}

function getWorkshopActionLabel(actionType) {
  return actionType === "image" ? "弹出图片" : "播放音乐";
}

function setWorkshopRuleCollapsed(card, collapsed) {
  const body = card.querySelector(".workshop-rule-body");
  const toggleBtn = card.querySelector(".toggle-workshop-rule");
  card.dataset.collapsed = collapsed ? "true" : "false";
  card.open = !collapsed;
  if (body) body.style.display = collapsed ? "none" : "";
  if (toggleBtn) toggleBtn.textContent = collapsed ? "展开" : "折叠";
}

function applyWorkshopRuleSearch() {
  const keyword = normalizeWorkshopSearchText(qs("workshopRuleSearch")?.value || "");
  const cards = [...qs("workshopRuleList").querySelectorAll(".workshop-rule-card")];
  let visibleCount = 0;
  cards.forEach((card) => {
    const matched = !keyword || getWorkshopSearchText(card).includes(keyword);
    card.style.display = matched ? "" : "none";
    if (matched) visibleCount += 1;
  });
  if (keyword) {
    setStatus(`创意工坊搜索完成：找到 ${visibleCount} 条匹配规则。`);
  }
}

function openFileInputPicker(input) {
  if (!input) return false;
  try {
    if (typeof input.showPicker === "function") {
      input.showPicker();
      return true;
    }
  } catch {
    // Fallback below.
  }
  try {
    input.click();
    return true;
  } catch {
    return false;
  }
}

function getWorkshopRuleIndex(card) {
  return Number(card?.dataset?.workshopIndex || 0);
}

function readWorkshopRuleSharedFields(card) {
  let triggerTempMin = normalizeWorkshopTempValue(card.querySelector(".workshop-rule-trigger-temp-min")?.value, 0);
  let triggerTempMax = normalizeWorkshopTempValue(card.querySelector(".workshop-rule-trigger-temp-max")?.value, triggerTempMin);
  if (triggerTempMax < triggerTempMin) {
    [triggerTempMin, triggerTempMax] = [triggerTempMax, triggerTempMin];
  }
  return {
    id: String(card.querySelector(".workshop-rule-id")?.value || "").trim(),
    name: String(card.querySelector(".workshop-rule-name")?.value || "").trim(),
    enabled: card.querySelector(".workshop-rule-enabled")?.checked !== false,
    triggerMode: normalizeWorkshopTriggerMode(card.querySelector(".workshop-rule-trigger-mode")?.value || "stage"),
    triggerStage: normalizeWorkshopStage(card.querySelector(".workshop-rule-trigger")?.value || "A"),
    triggerTempMin,
    triggerTempMax,
    actionType: normalizeWorkshopActionType(card.querySelector(".workshop-rule-action")?.value),
    note: String(card.querySelector(".workshop-rule-note")?.value || "").trim(),
  };
}

function setWorkshopTriggerPanelState(panel, active) {
  if (!panel) return;
  panel.hidden = !active;
}

function buildWorkshopMusicActionFields(item, index) {
  const musicPresetOptions = MUSIC_PRESETS.map((preset) => {
    const selected = preset.id === (item.musicPreset || "off") ? "selected" : "";
    return `<option value="${preset.id}" ${selected}>${escapeHtml(preset.label)}</option>`;
  }).join("");
  return `
    <div class="workshop-action-panel" data-action-type="music">
      <label>音乐预设</label>
      <select class="workshop-rule-preset" data-workshop-rule-preset="${index}">
        ${musicPresetOptions}
      </select>
      <label>音乐 URL</label>
      <input class="workshop-rule-url" data-workshop-rule-url="${index}" value="${escapeAttr(item.musicUrl || "")}" placeholder="优先使用这里，留空则用音乐预设" />
      <div class="button-row compact-buttons">
        <button class="ghost-button fake-file-button workshop-file-button" data-workshop-file-type="music" type="button">上传音乐</button>
        <input class="workshop-rule-music-file file-input-proxy" data-workshop-rule-music-file="${index}" type="file" accept="audio/*" />
      </div>
      <div class="two-col">
        <label class="checkbox-row"><input class="workshop-rule-autoplay" data-workshop-rule-autoplay="${index}" type="checkbox" ${item.autoplay !== false ? "checked" : ""} /> 自动播放</label>
        <label class="checkbox-row"><input class="workshop-rule-loop" data-workshop-rule-loop="${index}" type="checkbox" ${item.loop !== false ? "checked" : ""} /> 循环播放</label>
      </div>
      <label>音量</label>
      <input class="workshop-rule-volume" data-workshop-rule-volume="${index}" type="range" min="0" max="1" step="0.01" value="${escapeAttr(item.volume ?? 0.85)}" />
      <div class="inline-value">当前音量：${Number(item.volume ?? 0.85).toFixed(2)}</div>
    </div>
  `;
}

function buildWorkshopImageActionFields(item, index) {
  return `
    <div class="workshop-action-panel" data-action-type="image">
      <label>弹窗标题</label>
      <input class="workshop-rule-popup-title" data-workshop-rule-popup-title="${index}" value="${escapeAttr(item.popupTitle || "")}" placeholder="图片弹窗的标题，留空则用规则标题" />
      <label>图片 URL</label>
      <input class="workshop-rule-image-url" data-workshop-rule-image-url="${index}" value="${escapeAttr(item.imageUrl || "")}" placeholder="可以填写远程图片地址或 data URL" />
      <div class="button-row compact-buttons">
        <button class="ghost-button fake-file-button workshop-file-button" data-workshop-file-type="image" type="button">上传图片</button>
        <input class="workshop-rule-image-file file-input-proxy" data-workshop-rule-image-file="${index}" type="file" accept="image/*" />
      </div>
      <label>图片说明</label>
      <input class="workshop-rule-image-alt" data-workshop-rule-image-alt="${index}" value="${escapeAttr(item.imageAlt || "")}" placeholder="图片弹窗里的说明文字" />
      <div class="workshop-image-preview-wrap">
        <img class="workshop-rule-image-preview" loading="lazy" decoding="async" src="${escapeAttr(item.imageUrl || "")}" alt="${escapeAttr(item.imageAlt || item.name || "创意工坊图片")}" ${item.imageUrl ? "" : "hidden"} />
      </div>
    </div>
  `;
}

function readWorkshopRuleFromCard(card) {
  const shared = readWorkshopRuleSharedFields(card);
  const index = getWorkshopRuleIndex(card);
  if (shared.actionType === "image") {
    return {
      ...shared,
      popupTitle: String(card.querySelector(".workshop-rule-popup-title")?.value || "").trim(),
      musicPreset: "off",
      musicUrl: "",
      autoplay: true,
      loop: true,
      volume: 0.85,
      imageUrl: String(card.querySelector(".workshop-rule-image-url")?.value || "").trim(),
      imageAlt: String(card.querySelector(".workshop-rule-image-alt")?.value || "").trim(),
      note: String(card.querySelector(".workshop-rule-note")?.value || "").trim(),
      index,
    };
  }
  return {
    ...shared,
    popupTitle: "",
    musicPreset: normalizeMusicPresetId(card.querySelector(".workshop-rule-preset")?.value || "off"),
    musicUrl: String(card.querySelector(".workshop-rule-url")?.value || "").trim(),
    autoplay: card.querySelector(".workshop-rule-autoplay")?.checked !== false,
    loop: card.querySelector(".workshop-rule-loop")?.checked !== false,
    volume: Math.min(Math.max(Number(card.querySelector(".workshop-rule-volume")?.value ?? 0.85) || 0.85, 0), 1),
    imageUrl: "",
    imageAlt: "",
    note: String(card.querySelector(".workshop-rule-note")?.value || "").trim(),
    index,
  };
}

function updateWorkshopRuleTriggerUI(card) {
  if (!card) return;
  const triggerMode = normalizeWorkshopTriggerMode(card.querySelector(".workshop-rule-trigger-mode")?.value || "stage");
  const stagePanel = card.querySelector(".workshop-trigger-panel[data-trigger-mode='stage']");
  const tempPanel = card.querySelector(".workshop-trigger-panel[data-trigger-mode='temp']");
  const triggerLabel = card.querySelector(".workshop-rule-trigger-label");
  setWorkshopTriggerPanelState(stagePanel, triggerMode === "stage");
  setWorkshopTriggerPanelState(tempPanel, triggerMode === "temp");
  if (triggerLabel) {
    triggerLabel.textContent = getWorkshopTriggerLabel(readWorkshopRuleSharedFields(card), {
      temp: getActiveSlot()?.temp ?? 0,
      stage: card.querySelector(".workshop-rule-trigger")?.value || "A",
    });
  }
}

function updateWorkshopRuleActionUI(card) {
  if (!card) return;
  const actionType = normalizeWorkshopActionType(card.querySelector(".workshop-rule-action")?.value);
  updateWorkshopRuleTriggerUI(card);
  const summaryAction = card.querySelector(".workshop-rule-action-label");
  const summarySnippet = card.querySelector(".workshop-rule-summary-text");
  const panel = card.querySelector(".workshop-action-panel");
  if (summaryAction) summaryAction.textContent = getWorkshopActionLabel(actionType);
  if (summarySnippet) {
    const snippet = actionType === "image"
      ? (card.querySelector(".workshop-rule-image-url")?.value || card.querySelector(".workshop-rule-note")?.value || "点击展开编辑这条创意工坊规则")
      : (card.querySelector(".workshop-rule-url")?.value || card.querySelector(".workshop-rule-note")?.value || "点击展开编辑这条创意工坊规则");
    summarySnippet.textContent = String(snippet).replace(/\s+/g, " ").trim().slice(0, 48) || "点击展开编辑这条创意工坊规则";
  }
  if (panel && panel.dataset.actionType !== actionType) {
    const base = readWorkshopRuleFromCard(card);
    panel.outerHTML = actionType === "image"
      ? buildWorkshopImageActionFields({
          ...base,
          popupTitle: base.popupTitle || "",
          imageUrl: "",
          imageAlt: "",
          note: base.note || "",
        }, getWorkshopRuleIndex(card))
      : buildWorkshopMusicActionFields({
          ...base,
          musicPreset: base.musicPreset || "off",
          musicUrl: "",
          autoplay: true,
          loop: true,
          volume: 0.85,
          note: base.note || "",
        }, getWorkshopRuleIndex(card));
  }
  const preview = card.querySelector(".workshop-rule-image-preview");
  const imageUrl = card.querySelector(".workshop-rule-image-url")?.value || "";
  if (preview) {
    preview.src = imageUrl || "";
    preview.hidden = !imageUrl;
  }
}

function createWorkshopRuleNode(item, index) {
  const node = document.createElement("div");
  node.className = "editor-card workshop-rule-card";
  node.dataset.workshopIndex = String(index);
  const summaryTitle = item.name || `规则 ${index + 1}`;
  const triggerMode = normalizeWorkshopTriggerMode(item.triggerMode);
  const triggerTempMin = normalizeWorkshopTempValue(item.triggerTempMin, Math.max(0, Number(getActiveSlot()?.temp ?? 0) || 0));
  const triggerTempMax = normalizeWorkshopTempValue(item.triggerTempMax, triggerTempMin);
  const isCoreStage = String(item.id || "").startsWith("workshop_stage_") && triggerMode === "stage" && ["A", "B", "C"].includes(item.triggerStage);
  const summarySource =
    item.actionType === "image"
      ? (item.imageUrl || item.note || "点击展开编辑这条创意工坊规则")
      : (item.musicUrl || item.musicPreset || item.note || "点击展开编辑这条创意工坊规则");
  const summarySnippet = String(summarySource).replace(/\s+/g, " ").trim().slice(0, 48);
  node.innerHTML = `
    <details class="editor-fold" open data-collapsed="false">
      <summary class="editor-summary">
        <div class="editor-summary-copy">
          <strong>${escapeHtml(summaryTitle)}</strong>
          <span class="muted compact">
            <span class="workshop-rule-trigger-label">${escapeHtml(getWorkshopTriggerLabel(item, { temp: getActiveSlot()?.temp ?? 0, stage: item.triggerStage }))}</span>
            ·
            <span class="workshop-rule-action-label">${escapeHtml(getWorkshopActionLabel(item.actionType))}</span>
            ·
            <span class="workshop-rule-summary-text">${escapeHtml(summarySnippet || "点击展开编辑这条创意工坊规则")}</span>
          </span>
        </div>
        <div class="editor-summary-actions">
          <button class="ghost-button icon-action toggle-workshop-rule" data-toggle-workshop-rule="${index}" type="button" aria-label="折叠规则">折叠</button>
          ${isCoreStage ? `<span class="preset-pill">固定阶段</span>` : `<button class="ghost-button danger-button icon-action" data-remove-workshop-rule="${index}" type="button" aria-label="删除规则">−</button>`}
        </div>
      </summary>
      <div class="editor-body workshop-rule-body">
        <input class="workshop-rule-id" data-workshop-rule-id="${index}" type="hidden" value="${escapeAttr(item.id || "")}" />
        <label>标题</label>
        <input class="workshop-rule-name" data-workshop-rule-name="${index}" value="${escapeAttr(item.name || "")}" />
        <label class="checkbox-row"><input class="workshop-rule-enabled" data-workshop-rule-enabled="${index}" type="checkbox" ${item.enabled !== false ? "checked" : ""} /> 启用规则</label>
        <div class="two-col">
          <div>
            <label>触发方式</label>
            <select class="workshop-rule-trigger-mode" data-workshop-rule-trigger-mode="${index}" ${isCoreStage ? "disabled" : ""}>
              <option value="stage" ${triggerMode === "stage" ? "selected" : ""}>阶段触发</option>
              <option value="temp" ${triggerMode === "temp" ? "selected" : ""}>自定义 Temp</option>
            </select>
          </div>
          <div>
            <label>动作</label>
            <select class="workshop-rule-action" data-workshop-rule-action="${index}">
              <option value="music" ${normalizeWorkshopActionType(item.actionType) === "music" ? "selected" : ""}>播放音乐</option>
              <option value="image" ${normalizeWorkshopActionType(item.actionType) === "image" ? "selected" : ""}>弹出图片</option>
            </select>
          </div>
        </div>
        <div class="workshop-trigger-panel" data-trigger-mode="stage">
          <label>触发阶段</label>
          <select class="workshop-rule-trigger" data-workshop-rule-trigger="${index}" ${isCoreStage ? "disabled" : ""}>
            <option value="A" ${item.triggerStage === "A" ? "selected" : ""}>A 阶段</option>
            <option value="B" ${item.triggerStage === "B" ? "selected" : ""}>B 阶段</option>
            <option value="C" ${item.triggerStage === "C" ? "selected" : ""}>C 阶段</option>
          </select>
        </div>
        <div class="workshop-trigger-panel" data-trigger-mode="temp">
          <div class="two-col">
            <div>
              <label>Temp 起点</label>
              <input class="workshop-rule-trigger-temp-min" data-workshop-rule-trigger-temp-min="${index}" type="number" min="0" max="9999" step="1" value="${escapeAttr(triggerTempMin)}" />
            </div>
            <div>
              <label>Temp 终点</label>
              <input class="workshop-rule-trigger-temp-max" data-workshop-rule-trigger-temp-max="${index}" type="number" min="0" max="9999" step="1" value="${escapeAttr(triggerTempMax)}" />
            </div>
          </div>
          <p class="muted compact">起点和终点相同表示只在单个 temp 上触发。</p>
        </div>
        <p class="muted compact">当前动作类型只保留一组配置，切换类型会清空另一组字段。</p>
        ${normalizeWorkshopActionType(item.actionType) === "image" ? buildWorkshopImageActionFields(item, index) : buildWorkshopMusicActionFields(item, index)}
        <label>备注</label>
        <textarea class="workshop-rule-note" data-workshop-rule-note="${index}" rows="3">${escapeHtml(item.note || "")}</textarea>
      </div>
    </details>
  `;
  setWorkshopRuleCollapsed(node.querySelector("details"), false);
  updateWorkshopRuleActionUI(node);
  return node;
}

function renderWorkshopRules() {
  const card = normalizeRoleCard(getCurrentCardStore().raw);
  const workshop = sanitizeCreativeWorkshop(card.creativeWorkshop);
  const list = qs("workshopRuleList");
  if (!list) return;
  list.innerHTML = "";
  workshop.items.forEach((item, index) => {
    list.appendChild(createWorkshopRuleNode(item, index));
  });
  applyWorkshopRuleSearch();
}

function normalizePresetSearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function getPresetSearchText(card) {
  return [
    card.querySelector(".preset-block-name")?.value || "",
    card.querySelector(".preset-block-content")?.value || "",
  ]
    .join("\n")
    .toLowerCase();
}

function setPresetBlockCollapsed(card, collapsed) {
  const body = card.querySelector(".preset-block-body");
  const toggleBtn = card.querySelector(".toggle-preset-block");
  card.dataset.collapsed = collapsed ? "true" : "false";
  card.open = !collapsed;
  if (body) body.style.display = collapsed ? "none" : "";
  if (toggleBtn) toggleBtn.textContent = collapsed ? "展开" : "折叠";
}

function applyPresetBlockSearch() {
  const keyword = normalizePresetSearchText(qs("presetBlockSearch")?.value || "");
  const cards = [...qs("presetBlockList").querySelectorAll(".preset-block-card")];
  let visibleCount = 0;
  for (const card of cards) {
    const matched = !keyword || getPresetSearchText(card).includes(keyword);
    card.style.display = matched ? "" : "none";
    if (matched) visibleCount += 1;
  }
  if (keyword) {
    setStatus(`规则块搜索完成：找到 ${visibleCount} 条匹配项。`);
  }
}

function createPresetBlockNode(item, index) {
  const node = document.createElement("div");
  node.className = "editor-card preset-block-card";
  const summaryTitle = item.name || `规则块 ${index + 1}`;
  const summarySource = item.content || "点击展开编辑这条规则块";
  const summarySnippet = String(summarySource).replace(/\s+/g, " ").trim().slice(0, 42);
  node.innerHTML = `
    <details class="editor-fold" open data-collapsed="false">
      <summary class="editor-summary">
        <div class="editor-summary-copy">
          <strong>${escapeHtml(summaryTitle)}</strong>
          <span class="muted compact">${escapeHtml(summarySnippet || "点击展开编辑这条规则块")}</span>
        </div>
        <div class="editor-summary-actions">
          <button class="ghost-button icon-action toggle-preset-block" data-toggle-preset-block="${index}" type="button" aria-label="折叠规则块">折叠</button>
          <button class="ghost-button danger-button icon-action" data-remove-preset-block="${index}" type="button" aria-label="删除规则块">−</button>
        </div>
      </summary>
      <div class="editor-body preset-block-body">
        <input class="preset-block-id" data-preset-block-id="${index}" type="hidden" value="${escapeAttr(item.id || "")}" />
        <label>标题</label>
        <input class="preset-block-name" data-preset-block-name="${index}" value="${escapeAttr(item.name || "")}" />
        <label class="checkbox-row"><input class="preset-block-enabled" data-preset-block-enabled="${index}" type="checkbox" ${item.enabled !== false ? "checked" : ""} /> 启用该规则块</label>
        <label>正文</label>
        <textarea class="preset-block-content" data-preset-block-content="${index}" rows="5">${escapeHtml(item.content || "")}</textarea>
      </div>
    </details>
  `;
  setPresetBlockCollapsed(node.querySelector("details"), false);
  return node;
}

function getEditingPresetStore() {
  const slot = getActiveSlot();
  slot.presetStore = sanitizePresetStore(slot.presetStore);
  return slot.presetStore;
}

function getEditingPreset() {
  const store = getEditingPresetStore();
  return store.presets.find((item) => item.id === editingPresetId) || getActivePresetFromStore(store);
}

function applyPresetToForm(preset) {
  const target = preset || getEditingPreset();
  if (!target) return;
  qs("presetName").value = target.name || "";
  qs("presetEnabled").checked = target.enabled !== false;
  qs("baseSystemPrompt").value = target.base_system_prompt || "";
  document.querySelectorAll(".preset-module").forEach((node) => {
    node.checked = Boolean(target.modules?.[node.dataset.key]);
  });
  const list = qs("presetBlockList");
  list.innerHTML = "";
  (target.extra_prompts || []).forEach((item, index) => {
    list.appendChild(createPresetBlockNode(item, index));
  });
  applyPresetBlockSearch();
}

function renderPresetLibrary() {
  const store = getEditingPresetStore();
  if (!store.presets.some((item) => item.id === editingPresetId)) {
    editingPresetId = store.active_preset_id;
  }
  qs("presetCount").textContent = String(store.presets.length);
  const activePreset = getActivePresetFromStore(store);
  qs("activePresetLabel").textContent = activePreset?.name || "未命名预设";
  qs("activePresetState").textContent = activePreset?.enabled === false ? "停用" : "启用";
  const list = qs("presetItems");
  list.innerHTML = "";
  store.presets.forEach((preset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `preset-item${preset.id === editingPresetId ? " active-editor" : ""}${preset.id === store.active_preset_id ? " current-runtime" : ""}`;
    const modulesEnabled = Object.entries(preset.modules || {})
      .filter(([, value]) => Boolean(value))
      .map(([key]) => PRESET_MODULE_RULES[key]?.label || key);
    button.innerHTML = `
      <div class="preset-item-head">
        <strong>${escapeHtml(preset.name || "未命名预设")}</strong>
        <span class="preset-pill">${preset.id === store.active_preset_id ? "当前" : "编辑中"}</span>
      </div>
      <small>${preset.enabled === false ? "已停用" : "已启用"} · ${modulesEnabled.length ? escapeHtml(modulesEnabled.join(" / ")) : "无激活模块"} · ${preset.extra_prompts?.length || 0} 个规则块</small>
    `;
    button.addEventListener("click", () => {
      syncPresetEditorToStore();
      editingPresetId = preset.id;
      renderPresetLibrary();
      applyPresetToForm(getEditingPreset());
      setStatus(`正在编辑预设：${preset.name || "未命名预设"}。`);
    });
    list.appendChild(button);
  });
}

function collectPresetForm() {
  const store = getEditingPresetStore();
  const current = getEditingPreset();
  return {
    id: current?.id || editingPresetId || `preset_${Date.now().toString(36)}`,
    name: String(qs("presetName").value || "").trim().slice(0, 64) || "默认预设",
    enabled: qs("presetEnabled").checked,
    base_system_prompt: String(qs("baseSystemPrompt").value || "").trim().slice(0, 16000),
    modules: Object.fromEntries(
      [...document.querySelectorAll(".preset-module")].map((node) => [node.dataset.key, node.checked])
    ),
    extra_prompts: [...qs("presetBlockList").querySelectorAll(".preset-block-card")].map((card, index) => ({
      id: String(card.querySelector(".preset-block-id")?.value || "").trim() || `preset-block-${Date.now()}-${index}`,
      name: String(card.querySelector(".preset-block-name")?.value || "").trim() || `规则块 ${index + 1}`,
      enabled: card.querySelector(".preset-block-enabled")?.checked !== false,
      content: String(card.querySelector(".preset-block-content")?.value || "").trim().slice(0, 12000),
    })),
  };
}

function syncPresetEditorToStore() {
  const slot = getActiveSlot();
  const store = getEditingPresetStore();
  const current = collectPresetForm();
  const index = store.presets.findIndex((item) => item.id === current.id);
  const sanitized = sanitizeSinglePreset(current, { fallbackName: current.name, fallbackId: current.id });
  if (index === -1) {
    store.presets.push(sanitized);
  } else {
    store.presets[index] = sanitized;
  }
  store.active_preset_id = store.presets.some((item) => item.id === store.active_preset_id) ? store.active_preset_id : sanitized.id;
  slot.presetStore = sanitizePresetStore(store);
  saveState();
}

function renderPreset() {
  const slot = getActiveSlot();
  slot.presetStore = sanitizePresetStore(slot.presetStore);
  if (!slot.presetStore.presets.some((item) => item.id === editingPresetId)) {
    editingPresetId = slot.presetStore.active_preset_id;
  }
  renderPresetLibrary();
  applyPresetToForm(getEditingPreset());
}

function savePresetFromForm() {
  syncPresetEditorToStore();
  renderPresetLibrary();
}

function createNewPreset() {
  syncPresetEditorToStore();
  const name = window.prompt("请输入新预设名称：", "新预设");
  if (name === null) return;
  const store = createPresetInStore(getEditingPresetStore(), name);
  const created = store.presets[store.presets.length - 1];
  getActiveSlot().presetStore = sanitizePresetStore(store);
  editingPresetId = created.id;
  saveState();
  renderPresetLibrary();
  applyPresetToForm(created);
  setStatus("已创建新预设。");
}

function duplicateCurrentPreset() {
  syncPresetEditorToStore();
  const store = duplicatePresetInStore(getEditingPresetStore(), editingPresetId);
  const duplicated = store.presets[store.presets.length - 1];
  getActiveSlot().presetStore = sanitizePresetStore(store);
  editingPresetId = duplicated.id;
  saveState();
  renderPresetLibrary();
  applyPresetToForm(duplicated);
  setStatus("已复制当前预设。");
}

function activateCurrentPreset() {
  syncPresetEditorToStore();
  const store = activatePresetInStore(getEditingPresetStore(), editingPresetId);
  getActiveSlot().presetStore = sanitizePresetStore(store);
  saveState();
  renderPresetLibrary();
  applyPresetToForm(getEditingPreset());
  setStatus("已设为当前运行预设。");
}

function deleteCurrentPreset() {
  const current = getEditingPreset();
  if (!current) return;
  if (!window.confirm(`确定删除预设「${current.name || "未命名预设"}」吗？`)) return;
  const store = deletePresetFromStore(getEditingPresetStore(), current.id);
  getActiveSlot().presetStore = sanitizePresetStore(store);
  editingPresetId = getActivePresetFromStore(store).id;
  saveState();
  renderPresetLibrary();
  applyPresetToForm(getEditingPreset());
  setStatus("预设已删除。");
}

function importPresetStoreFromText(rawText) {
  const text = String(rawText || "");
  const parsed = extractJsonObject(text) || JSON.parse(text);
  const store = sanitizePresetStore(parsed);
  const slot = getActiveSlot();
  slot.presetStore = store;
  editingPresetId = store.active_preset_id;
  saveState();
  renderPresetLibrary();
  applyPresetToForm(getEditingPreset());
}

async function exportCurrentPresetStore() {
  const store = sanitizePresetStore(getEditingPresetStore());
  try {
    await saveTextWithPicker(buildNamedJsonFileName("预设"), JSON.stringify(store, null, 2), "application/json");
    setStatus("预设库已导出。");
  } catch (error) {
    setStatus("预设导出失败");
    showModal("导出失败", error instanceof Error ? error.message : "预设导出失败");
  }
}

function saveSettingsFromForm() {
  const presetId = qs("presetSelect").value;
  const preset = MODEL_PRESETS.find((item) => item.id === presetId) || MODEL_PRESETS[0];
  const currentUrl = qs("apiBaseUrl").value.trim();
  state.settings = {
    ...state.settings,
    modelPreset: presetId,
    apiBaseUrl: presetId !== "custom" && (!currentUrl || currentUrl === state.settings.apiBaseUrl) ? preset.url : currentUrl,
    apiKey: qs("apiKey").value.trim(),
    model: qs("modelName").value.trim(),
    temperature: Number(qs("temperature").value || 0.85),
    timeoutSec: Number(qs("timeoutSec").value || 90),
    historyLimit: Number(qs("historyLimit").value || 20),
    maxTokens: Math.max(0, Number(qs("maxTokens").value || 0)),
    theme: qs("themeSelect").value,
    uiOpacity: Number(qs("uiOpacity").value || 0.88),
    backgroundOverlay: Number(qs("backgroundOverlay").value || 0.36),
    backgroundImageUrl: qs("backgroundImageUrl").value.trim(),
    musicPreset: qs("musicPresetSelect").value,
    musicUrl: qs("musicUrlInput").value.trim(),
    embeddingBaseUrl: qs("embeddingBaseUrl").value.trim(),
    embeddingApiKey: qs("embeddingApiKey").value.trim(),
    embeddingModel: qs("embeddingModel").value.trim(),
    embeddingFields: [...document.querySelectorAll(".embedding-field:checked")].map((el) => el.value),
    retrievalTopK: Number(qs("retrievalTopK").value || 4),
    rerankEnabled: qs("rerankEnabled").checked,
    rerankBaseUrl: qs("rerankBaseUrl").value.trim(),
    rerankApiKey: qs("rerankApiKey").value.trim(),
    rerankModel: qs("rerankModel").value.trim(),
    rerankTopN: Number(qs("rerankTopN").value || 3),
  };
  qs("apiBaseUrl").value = state.settings.apiBaseUrl;
  qs("uiOpacityValue").textContent = state.settings.uiOpacity.toFixed(2);
  qs("backgroundOverlayValue").textContent = state.settings.backgroundOverlay.toFixed(2);
  saveState();
  renderGlobalChrome();
}

function saveUserProfileFromForm() {
  const slot = getActiveSlot();
  slot.userProfile = {
    ...createDefaultUserProfile(),
    ...(slot.userProfile || {}),
    displayName: String(qs("userDisplayName")?.value || "").trim() || "我",
    nickname: String(qs("userNickname")?.value || "").trim(),
    profileText: String(qs("userProfileText")?.value || "").trim(),
    notes: String(qs("userNotes")?.value || "").trim(),
    avatarUrl: String(qs("userAvatarUrl")?.value || "").trim(),
    roleAvatarUrl: String(qs("userRoleAvatarUrl")?.value || "").trim(),
  };
  saveState();
  if (qs("userAvatarPreview")) {
    const preview = qs("userAvatarPreview");
    preview.hidden = !slot.userProfile.avatarUrl;
    if (slot.userProfile.avatarUrl) preview.src = slot.userProfile.avatarUrl;
  }
  if (qs("userRoleAvatarPreview")) {
    const preview = qs("userRoleAvatarPreview");
    preview.hidden = !slot.userProfile.roleAvatarUrl;
    if (slot.userProfile.roleAvatarUrl) preview.src = slot.userProfile.roleAvatarUrl;
  }
  if (state.activeRoute === "chat") renderChat();
}

function saveAndRefreshSettings() {
  saveSettingsFromForm();
  renderAll();
  setStatus("模型配置已保存并刷新。");
}

function buildCardPayloadFromForm() {
  const card = {
    name: qs("cardName").value.trim(),
    tags: sanitizeTags(qs("cardTags").value),
    description: qs("cardDescription").value.trim(),
    personality: qs("cardPersonality").value.trim(),
    scenario: qs("cardScenario").value.trim(),
    first_mes: qs("cardFirstMes").value.trim(),
    mes_example: qs("cardMesExample").value.trim(),
    creator_notes: qs("cardCreatorNotes").value.trim(),
    plotStages: {},
    personas: {},
  };

  qs("plotStageList").querySelectorAll("[data-stage-key]").forEach((node) => {
    const key = node.dataset.stageKey;
    card.plotStages[key] = {
      description: node.querySelector(`[data-stage-desc="${key}"]`)?.value.trim() || "",
      rules: node.querySelector(`[data-stage-rules="${key}"]`)?.value.trim() || "",
    };
  });

  qs("personaCardGrid").querySelectorAll("[data-persona-key]").forEach((node) => {
    const key = node.dataset.personaKey;
    card.personas[key] = {
      name: node.querySelector(`[data-persona-name="${key}"]`)?.value.trim() || "",
      description: node.querySelector(`[data-persona-desc="${key}"]`)?.value.trim() || "",
      personality: node.querySelector(`[data-persona-personality="${key}"]`)?.value.trim() || "",
      scenario: node.querySelector(`[data-persona-scenario="${key}"]`)?.value.trim() || "",
      creator_notes: node.querySelector(`[data-persona-notes="${key}"]`)?.value.trim() || "",
    };
  });

  card.creativeWorkshop = {
    enabled: qs("workshopEnabled")?.checked !== false,
    items: [],
  };
  qs("workshopRuleList").querySelectorAll(".workshop-rule-card").forEach((cardNode, index) => {
    const item = readWorkshopRuleFromCard(cardNode);
    card.creativeWorkshop.items.push({
      id: item.id || `workshop-item-${Date.now()}-${index}`,
      name: item.name,
      enabled: item.enabled,
      triggerMode: item.triggerMode,
      triggerStage: item.triggerStage,
      triggerTempMin: item.triggerTempMin,
      triggerTempMax: item.triggerTempMax,
      actionType: item.actionType,
      popupTitle: item.popupTitle || "",
      musicPreset: item.musicPreset || "off",
      musicUrl: item.musicUrl || "",
      autoplay: item.autoplay !== false,
      loop: item.loop !== false,
      volume: Number(item.volume || 0.85),
      imageUrl: item.imageUrl || "",
      imageAlt: item.imageAlt || "",
      note: item.note || "",
    });
  });

  return normalizeRoleCard(card);
}

function updateCardFromForm() {
  state.currentCard.sourceName = safeFileName(qs("cardSourceName").value.trim() || "role_card.json", "role_card.json");
  state.currentCard.raw = buildCardPayloadFromForm();
  state.persona = derivePersonaFromRoleCard(state.currentCard.raw);
  saveState();
  renderGlobalChrome();
  if (state.activeRoute === "chat") renderChat();
}

function updateWorldbookSettingsFromForm() {
  const worldbook = getActiveSlot().worldbook;
  worldbook.settings = normalizeWorldbookSettings({
    ...(worldbook.settings || {}),
    enabled: qs("worldbookEnabled").checked,
    debugEnabled: qs("worldbookDebugEnabled").checked,
    maxEntries: Number(qs("worldbookMaxEntries").value || 3),
    defaultMatchMode: qs("worldbookDefaultMatchMode").value,
    defaultSecondaryMode: qs("worldbookDefaultSecondaryMode").value,
    defaultEntryType: qs("worldbookDefaultEntryType").value,
    defaultGroupOperator: qs("worldbookDefaultGroupOperator").value,
    defaultChance: Number(qs("worldbookDefaultChance").value || 100),
    defaultStickyTurns: Number(qs("worldbookDefaultStickyTurns").value || 0),
    defaultCooldownTurns: Number(qs("worldbookDefaultCooldownTurns").value || 0),
    defaultInsertionPosition: qs("worldbookDefaultInsertionPosition").value,
    defaultInjectionDepth: Number(qs("worldbookDefaultInjectionDepth").value || 0),
    defaultInjectionRole: qs("worldbookDefaultInjectionRole").value,
    defaultInjectionOrder: Number(qs("worldbookDefaultInjectionOrder").value || 100),
    recursiveScanEnabled: qs("worldbookRecursiveScanEnabled").checked,
    recursionMaxDepth: Number(qs("worldbookRecursionMaxDepth").value || 2),
    caseSensitive: qs("worldbookCaseSensitive").checked,
    wholeWord: qs("worldbookWholeWord").checked,
  });
  saveState();
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
}

async function importBackgroundImage(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    state.settings.backgroundImageUrl = await fileToDataUrl(file);
    saveState();
    renderConfig();
    renderGlobalChrome();
    setStatus("背景已更新");
  } catch {
    setStatus("背景图片读取失败");
  } finally {
    event.target.value = "";
  }
}

async function importAvatarImage(event, fieldName) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const dataUrl = await fileToDataUrl(file);
    const slot = getActiveSlot();
    slot.userProfile = {
      ...createDefaultUserProfile(),
      ...(slot.userProfile || {}),
      [fieldName]: dataUrl,
    };
    saveState();
    renderConfig();
    if (state.activeRoute === "chat") renderChat();
    setStatus(fieldName === "avatarUrl" ? "用户头像已更新" : "角色头像已更新");
  } catch {
    setStatus("头像图片读取失败");
  } finally {
    event.target.value = "";
  }
}

async function importAvatarImageFromNative(fieldName) {
  try {
    const dataUrl = await requestNativeImagePick();
    const slot = getActiveSlot();
    slot.userProfile = {
      ...createDefaultUserProfile(),
      ...(slot.userProfile || {}),
      [fieldName]: dataUrl,
    };
    saveState();
    renderConfig();
    if (state.activeRoute === "chat") renderChat();
    setStatus(fieldName === "avatarUrl" ? "用户头像已更新" : "角色头像已更新");
  } catch (error) {
    const message = error instanceof Error ? error.message : "头像图片读取失败";
    setStatus(message);
  }
}

function pickAvatarFromUi(fieldName) {
  const targetField = fieldName === "roleAvatarUrl" ? "roleAvatarUrl" : "avatarUrl";
  if (window.XuqiNative && typeof window.XuqiNative.pickImageAsync === "function") {
    setStatus(targetField === "avatarUrl" ? "正在打开用户头像选择器" : "正在打开角色头像选择器");
    void importAvatarImageFromNative(targetField);
    return false;
  }
  const fileInput = targetField === "avatarUrl" ? qs("userAvatarFile") : qs("userRoleAvatarFile");
  setStatus(targetField === "avatarUrl" ? "请选择用户头像图片" : "请选择角色头像图片");
  openFileInputPicker(fileInput);
  return false;
}

async function importState(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = extractJsonObject(text) || JSON.parse(text);
    const runtimeSource = extractRuntimeBackupSource(parsed);
    if (!runtimeSource) throw new Error("运行态备份里没有可识别的运行数据");
    state = mergeState({
      activeRoute: state.activeRoute,
      settings: {
        ...state.settings,
        ...((parsed?.settings && typeof parsed.settings === "object") ? parsed.settings : {}),
      },
      runtime: runtimeSource,
      currentCard: state.currentCard,
    });
    saveState();
    renderAll();
    setStatus("已导入运行态备份");
    showModal("导入成功", "手机本地的全局运行态和设置已经替换为导入文件中的内容，当前人设卡保持不变。");
  } catch {
    setStatus("运行态备份导入失败");
    showModal("导入失败", "文件内容无法识别，请确认它是由本应用导出的运行态备份 JSON，或者至少包含可识别的运行态字段。");
  } finally {
    event.target.value = "";
  }
}

async function importRoleCard(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const json = extractJsonObject(text) || JSON.parse(text);
    state.currentCard.sourceName = safeFileName(file.name, "role_card.json");
    state.currentCard.raw = normalizeRoleCard(json);
    state.persona = derivePersonaFromRoleCard(state.currentCard.raw);
    saveState();
    syncCreativeWorkshopRuntime("load");
    renderGlobalChrome();
    renderCard();
    renderChat();
    setStatus("角色卡已导入");
    showModal("导入成功", "角色卡已经导入并应用到当前运行态，现有记忆、世界书和预设保持不变。");
  } catch {
    setStatus("角色卡导入失败");
    showModal("导入失败", "角色卡不是有效的 JSON 或内容结构不正确。");
  } finally {
    event.target.value = "";
  }
}

function applyCardTemplate(factory, name) {
  state.currentCard.raw = normalizeRoleCard(factory());
  state.currentCard.sourceName = `${safeFileName(name, "role_card")}.json`;
  state.persona = derivePersonaFromRoleCard(state.currentCard.raw);
  saveState();
  syncCreativeWorkshopRuntime("load");
  renderGlobalChrome();
  renderCard();
  renderChat();
  setStatus(`${name} 已应用`);
}

function updateMusicFromSettings() {
  const player = qs("bgmPlayer");
  const settings = state.settings;
  const preset = MUSIC_PRESETS.find((item) => item.id === settings.musicPreset);
  const nextUrl = settings.musicUrl || preset?.url || "";
  if (!nextUrl) {
    player.pause();
    player.removeAttribute("src");
    player.load();
    return;
  }
  if (player.src !== nextUrl) {
    player.src = nextUrl;
  }
}

function playMusic() {
  updateMusicFromSettings();
  const player = qs("bgmPlayer");
  if (!player.src) {
    showModal("没有音乐来源", "请先选择音乐预设，或者填写自定义音乐 URL。");
    return;
  }
  player.play().catch(() => {
    showModal("播放失败", "当前音乐资源无法播放，可能是链接失效或网络不可用。");
  });
}

function pauseMusic() {
  qs("bgmPlayer").pause();
}

function stopMusic() {
  const player = qs("bgmPlayer");
  player.pause();
  player.currentTime = 0;
}

function bindDynamicEditors() {
  qs("memoryList").querySelectorAll("[data-memory-title]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const slot = getActiveSlot();
      slot.memories[Number(event.target.dataset.memoryTitle)].title = event.target.value;
      cleanupDeletedMemories(slot);
      saveState();
    });
  });
  qs("memoryList").querySelectorAll("[data-memory-selected]").forEach((input) => {
    input.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    input.addEventListener("change", updateMemoryStats);
  });
  qs("memoryList").querySelectorAll("[data-memory-content]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const slot = getActiveSlot();
      slot.memories[Number(event.target.dataset.memoryContent)].content = event.target.value;
      cleanupDeletedMemories(slot);
      saveState();
    });
  });
  qs("memoryList").querySelectorAll("[data-memory-tags]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const slot = getActiveSlot();
      slot.memories[Number(event.target.dataset.memoryTags)].tags = sanitizeTags(event.target.value);
      cleanupDeletedMemories(slot);
      saveState();
    });
  });
  qs("memoryList").querySelectorAll("[data-memory-notes]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const slot = getActiveSlot();
      slot.memories[Number(event.target.dataset.memoryNotes)].notes = event.target.value;
      cleanupDeletedMemories(slot);
      saveState();
    });
  });
  qs("memoryList").querySelectorAll("[data-toggle-memory]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const card = event.currentTarget.closest("details");
      if (!card) return;
      const collapsed = card.dataset.collapsed === "true";
      setMemoryCollapsed(card, !collapsed);
    });
  });

  qs("memoryList").querySelectorAll("[data-remove-memory]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!confirmDangerAction("确定删除这条记忆吗？删除后会立即影响后续聊天与总结。")) return;
      const slot = getActiveSlot();
      const removed = slot.memories.splice(Number(event.target.dataset.removeMemory), 1)[0];
      recordDeletedMemory(slot, removed);
      saveState();
      renderMemory();
      bindDynamicEditors();
      setStatus("记忆已删除并立即生效。");
    });
  });

  qs("worldbookList").querySelectorAll("[data-worldbook-title]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookTitle)].title = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-selected]").forEach((input) => {
    input.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    input.addEventListener("change", updateSelectedWorldbookCount);
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-group]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookGroup)].group = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-entry-type]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookEntryType)].entryType =
        normalizeWorldbookEntryType(event.target.value, "keyword");
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-group-operator]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookGroupOperator)].groupOperator =
        normalizeWorldbookGroupOperator(event.target.value, "and");
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-primary]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookPrimary)].primaryTriggers = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-secondary]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookSecondary)].secondaryTriggers = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-content]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookContent)].content = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-order]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const entry = getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookOrder)];
      entry.order = clampInteger(event.target.value, 0, 999999, 100);
      entry.priority = entry.order;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-priority]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const entry = getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookPriority)];
      entry.order = clampInteger(event.target.value, 0, 999999, 100);
      entry.priority = entry.order;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-mode]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookMode)].matchMode = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-secondary-mode]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookSecondaryMode)].secondaryMode = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-chance]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookChance)].chance =
        clampInteger(event.target.value, 0, 100, 100);
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-sticky-turns]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookStickyTurns)].stickyTurns =
        clampInteger(event.target.value, 0, 999, 0);
      saveState();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-cooldown-turns]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookCooldownTurns)].cooldownTurns =
        clampInteger(event.target.value, 0, 999, 0);
      saveState();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-insertion-position]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookInsertionPosition)].insertionPosition =
        normalizeWorldbookInsertionPosition(event.target.value, "after_char_defs");
      syncWorldbookInjectionUi(event.target.closest(".worldbook-card") || qs("worldbookList"));
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-injection-depth]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookInjectionDepth)].injectionDepth =
        clampInteger(event.target.value, 0, 3, 0);
      saveState();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-injection-role]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookInjectionRole)].injectionRole =
        normalizeWorldbookInjectionRole(event.target.value, "system");
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-injection-order]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookInjectionOrder)].injectionOrder =
        clampInteger(event.target.value, 0, 999999, 100);
      saveState();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-enabled]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookEnabled)].enabled = event.target.checked;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-case-sensitive]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookCaseSensitive)].caseSensitive = event.target.checked;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-wholeword]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookWholeword)].wholeWord = event.target.checked;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-recursive-enabled]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookRecursiveEnabled)].recursiveEnabled = event.target.checked;
      saveState();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-prevent-recursion]").forEach((input) => {
    input.addEventListener("change", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookPreventRecursion)].preventFurtherRecursion = event.target.checked;
      saveState();
    });
  });
  qs("worldbookList").querySelectorAll("[data-worldbook-notes]").forEach((input) => {
    input.addEventListener("input", (event) => {
      getActiveSlot().worldbook.entries[Number(event.target.dataset.worldbookNotes)].notes = event.target.value;
      saveState();
      applyWorldbookSearch();
    });
  });
  qs("worldbookList").querySelectorAll("[data-toggle-worldbook]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const card = event.currentTarget.closest("details");
      if (!card) return;
      const collapsed = card.dataset.collapsed === "true";
      setWorldbookCollapsed(card, !collapsed);
    });
  });
  qs("worldbookList").querySelectorAll("[data-remove-worldbook]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!confirmDangerAction("确定删除这条世界书词条吗？")) return;
      getActiveSlot().worldbook.entries.splice(Number(event.target.dataset.removeWorldbook), 1);
      saveState();
      renderWorldbook();
      bindDynamicEditors();
    });
  });

  const plotStageList = qs("plotStageList");
  if (!plotStageList.dataset.bound) {
    plotStageList.addEventListener("input", (event) => {
      if (event.target.matches("textarea")) updateCardFromForm();
    });
    plotStageList.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-stage]");
      if (!removeButton) return;
      const key = removeButton.dataset.removeStage;
      if (!key) return;
      if (!confirmDangerAction(`确定删除阶段 ${key} 吗？`)) return;
      delete getCurrentCardStore().raw.plotStages[key];
      state.persona = derivePersonaFromRoleCard(getCurrentCardStore().raw);
      saveState();
      renderCard();
      bindDynamicEditors();
    });
    plotStageList.dataset.bound = "true";
  }

  const personaCardGrid = qs("personaCardGrid");
  if (!personaCardGrid.dataset.bound) {
    personaCardGrid.addEventListener("input", (event) => {
      if (event.target.matches("input, textarea")) updateCardFromForm();
    });
    personaCardGrid.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-persona]");
      if (!removeButton) return;
      const key = removeButton.dataset.removePersona;
      if (!key) return;
      if (!confirmDangerAction("确定删除这名角色吗？")) return;
      delete getCurrentCardStore().raw.personas[key];
      state.persona = derivePersonaFromRoleCard(getCurrentCardStore().raw);
      saveState();
      renderCard();
      bindDynamicEditors();
    });
    personaCardGrid.dataset.bound = "true";
  }

  const presetBlockList = qs("presetBlockList");
  if (presetBlockList && !presetBlockList.dataset.bound) {
    presetBlockList.addEventListener("input", (event) => {
      if (!event.target.matches("input, textarea")) return;
      const nameInput = event.target.closest(".preset-block-card")?.querySelector(".preset-block-name");
      const summary = event.target.closest(".preset-block-card")?.querySelector(".editor-summary strong");
      if (summary && nameInput) {
        summary.textContent = nameInput.value.trim() || "规则块";
      }
      syncPresetEditorToStore();
    });
    presetBlockList.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-preset-block]");
      if (removeButton) {
        if (!confirmDangerAction("确定删除这条规则块吗？")) return;
        const card = removeButton.closest(".preset-block-card");
        if (card) card.remove();
        syncPresetEditorToStore();
        renderPresetLibrary();
        applyPresetToForm(getEditingPreset());
        setStatus("规则块已删除。");
        return;
      }
      const toggleButton = event.target.closest("[data-toggle-preset-block]");
      if (!toggleButton) return;
      const card = toggleButton.closest(".preset-block-card");
      if (!card) return;
      const details = card.querySelector("details");
      if (!details) return;
      const collapsed = details.dataset.collapsed === "true";
      setPresetBlockCollapsed(details, !collapsed);
    });
    presetBlockList.dataset.bound = "true";
  }

  const workshopRuleList = qs("workshopRuleList");
  if (workshopRuleList && !workshopRuleList.dataset.bound) {
    workshopRuleList.addEventListener("input", (event) => {
      if (!event.target.matches("input, textarea, select")) return;
      const card = event.target.closest(".workshop-rule-card");
      const nameField = card?.querySelector(".workshop-rule-name");
      const summary = card?.querySelector(".editor-summary strong");
      if (event.target.matches(".workshop-rule-volume")) {
        const valueBox = card?.querySelector(".inline-value");
        if (valueBox) valueBox.textContent = `当前音量：${Number(event.target.value || 0.85).toFixed(2)}`;
      }
      if (summary && nameField) {
        summary.textContent = nameField.value.trim() || "规则";
      }
      updateWorkshopRuleActionUI(card);
      updateCardFromForm();
      applyWorkshopRuleSearch();
    });
    workshopRuleList.addEventListener("change", (event) => {
      if (!event.target.matches("input, select, textarea")) return;
      const card = event.target.closest(".workshop-rule-card");
      if (event.target.matches(".workshop-rule-action")) {
        updateWorkshopRuleActionUI(card);
        setStatus(event.target.value === "image" ? "已切换为图片动作，音乐配置已清空。" : "已切换为音乐动作，图片配置已清空。");
      }
      if (event.target.matches(".workshop-rule-music-file")) {
        const file = event.target.files?.[0];
        if (file && card) {
          void fileToDataUrl(file)
            .then((dataUrl) => {
              const musicUrlField = card.querySelector(".workshop-rule-url");
              const actionField = card.querySelector(".workshop-rule-action");
              if (musicUrlField) {
                musicUrlField.value = dataUrl;
              }
              if (actionField) {
                actionField.value = "music";
              }
              if (musicUrlField || actionField) {
                updateWorkshopRuleActionUI(card);
                updateCardFromForm();
                applyWorkshopRuleSearch();
                setStatus("创意工坊音乐已导入。");
              }
            })
            .catch(() => {
              setStatus("创意工坊音乐读取失败");
            })
            .finally(() => {
              event.target.value = "";
            });
          return;
        }
      }
      if (event.target.matches(".workshop-rule-image-file")) {
        const file = event.target.files?.[0];
        if (file && card) {
          void fileToDataUrl(file)
            .then((dataUrl) => {
              const imageUrlField = card.querySelector(".workshop-rule-image-url");
              const actionField = card.querySelector(".workshop-rule-action");
              if (imageUrlField) {
                imageUrlField.value = dataUrl;
              }
              if (actionField) {
                actionField.value = "image";
              }
              if (imageUrlField || actionField) {
                updateWorkshopRuleActionUI(card);
                updateCardFromForm();
                applyWorkshopRuleSearch();
                setStatus("创意工坊图片已导入。");
              }
            })
            .catch(() => {
              setStatus("创意工坊图片读取失败");
            })
            .finally(() => {
              event.target.value = "";
            });
          return;
        }
      }
      updateCardFromForm();
      applyWorkshopRuleSearch();
    });
    workshopRuleList.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-workshop-rule]");
      if (removeButton) {
        if (!confirmDangerAction("确定删除这条创意工坊规则吗？")) return;
        const card = removeButton.closest(".workshop-rule-card");
        if (card) card.remove();
        updateCardFromForm();
        renderWorkshopSettings();
        bindDynamicEditors();
        setStatus("创意工坊规则已删除。");
        return;
      }
      const toggleButton = event.target.closest("[data-toggle-workshop-rule]");
      if (!toggleButton) return;
      const card = toggleButton.closest(".workshop-rule-card");
      const details = card?.querySelector("details");
      if (!details) return;
      const collapsed = details.dataset.collapsed === "true";
      setWorkshopRuleCollapsed(details, !collapsed);
    });
    workshopRuleList.dataset.bound = "true";
  }
}

function bindGlobalEvents() {
  document.querySelectorAll("[data-nav]").forEach((button) => {
    if (["openWorkshopButton", "openWorkshopButtonCard", "openWorkshopButtonCard2"].includes(button.id)) return;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      navigate(button.dataset.nav);
    });
  });

  if (qs("openDrawerButton")) qs("openDrawerButton").addEventListener("click", openDrawer);
  if (qs("closeDrawerButton")) qs("closeDrawerButton").addEventListener("click", closeDrawer);
  if (qs("drawerBackdrop")) {
    qs("drawerBackdrop").addEventListener("click", (event) => {
      if (event.target === qs("drawerBackdrop")) closeDrawer();
    });
  }

  qs("themeToggleButton").addEventListener("click", () => {
    state.settings.theme = state.settings.theme === "light" ? "dark" : "light";
    saveState();
    renderAll();
  });

  qs("exportRuntimeButton").addEventListener("click", exportState);
  qs("closeModalButton").addEventListener("click", hideModal);
  qs("confirmModalButton").addEventListener("click", hideModal);
  qs("modalBackdrop").addEventListener("click", (event) => {
    if (event.target === qs("modalBackdrop")) hideModal();
  });
  qs("closeWorkshopModalButton").addEventListener("click", hideWorkshopImagePopup);
  qs("confirmWorkshopModalButton").addEventListener("click", hideWorkshopImagePopup);
  qs("workshopModalBackdrop").addEventListener("click", (event) => {
    if (event.target === qs("workshopModalBackdrop")) hideWorkshopImagePopup();
  });

  if (qs("refreshChatRouteButton")) {
    qs("refreshChatRouteButton").addEventListener("click", renderChat);
  }
  if (qs("previewPromptButton")) {
    qs("previewPromptButton").addEventListener("click", showPromptPreview);
  }
  qs("sendButton").addEventListener("click", () => void sendMessage());
  qs("messageInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  });
  qs("endConversationButton").addEventListener("click", () => void endConversation());
  qs("exportChatButton").addEventListener("click", exportChatHistory);

  qs("testConnectionButton").addEventListener("click", async () => {
    if (!state.settings.apiBaseUrl || !state.settings.model) {
      showModal("缺少配置", "请先填写 API URL 和模型名。");
      return;
    }
    setStatus("正在测试连接...");
    try {
      const reply = await callModelAsync([{ role: "user", content: "请只回复：连接成功" }], {
        temperature: 0.1,
        timeoutSec: 30,
      });
      setStatus("连接成功");
      showModal("连接成功", `模型回复：\n${reply}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      setStatus("连接失败");
      showModal("连接失败", message);
    }
  });

  if (qs("presetName")) qs("presetName").addEventListener("input", savePresetFromForm);
  if (qs("presetEnabled")) qs("presetEnabled").addEventListener("change", savePresetFromForm);
  if (qs("baseSystemPrompt")) qs("baseSystemPrompt").addEventListener("input", savePresetFromForm);
  if (qs("presetBlockSearch")) qs("presetBlockSearch").addEventListener("input", applyPresetBlockSearch);
  if (qs("addPresetBlockButton")) {
    qs("addPresetBlockButton").addEventListener("click", () => {
      syncPresetEditorToStore();
      const slot = getActiveSlot();
      const store = getEditingPresetStore();
      const current = store.presets.find((item) => item.id === editingPresetId) || getActivePresetFromStore(store);
      if (!current) return;
      current.extra_prompts = [...(current.extra_prompts || []), {
        id: `preset-block-${Date.now().toString(36)}`,
        name: "新规则块",
        enabled: true,
        content: "",
      }];
      slot.presetStore = sanitizePresetStore(store);
      saveState();
      renderPresetLibrary();
      applyPresetToForm(getEditingPreset());
      setStatus("已新增规则块。");
    });
  }
  if (qs("collapseAllPresetBlocks")) {
    qs("collapseAllPresetBlocks").addEventListener("click", () => {
      qs("presetBlockList").querySelectorAll(".preset-block-card details").forEach((card) => setPresetBlockCollapsed(card, true));
      setStatus("已折叠全部规则块。");
    });
  }
  if (qs("expandAllPresetBlocks")) {
    qs("expandAllPresetBlocks").addEventListener("click", () => {
      qs("presetBlockList").querySelectorAll(".preset-block-card details").forEach((card) => setPresetBlockCollapsed(card, false));
      setStatus("已展开全部规则块。");
    });
  }
  if (qs("createPresetButton")) qs("createPresetButton").addEventListener("click", createNewPreset);
  if (qs("duplicatePresetButton")) qs("duplicatePresetButton").addEventListener("click", duplicateCurrentPreset);
  if (qs("activatePresetButton")) qs("activatePresetButton").addEventListener("click", activateCurrentPreset);
  if (qs("deletePresetButton")) qs("deletePresetButton").addEventListener("click", deleteCurrentPreset);
  if (qs("exportPresetButton")) qs("exportPresetButton").addEventListener("click", exportCurrentPresetStore);
  if (qs("importPresetButton")) qs("importPresetButton").addEventListener("click", () => qs("importPresetFile").click());
  if (qs("importPresetFile")) {
    qs("importPresetFile").addEventListener("change", async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        await importPresetStoreFromText(await file.text());
        setStatus("预设已导入。");
      } catch (error) {
        setStatus(`预设导入失败：${error instanceof Error ? error.message : "未知错误"}`);
      } finally {
        event.target.value = "";
      }
    });
  }

  qs("presetSelect").addEventListener("change", () => {
    const preset = MODEL_PRESETS.find((item) => item.id === qs("presetSelect").value);
    if (preset && preset.id !== "custom") {
      qs("apiBaseUrl").value = preset.url;
    }
    saveSettingsFromForm();
  });

  document.querySelectorAll(".preset-module").forEach((node) => {
    node.addEventListener("change", () => {
      if (node.checked) {
        (PRESET_MODULE_MUTEX[node.dataset.key] || []).forEach((otherKey) => {
          const other = document.querySelector(`.preset-module[data-key="${otherKey}"]`);
          if (other) other.checked = false;
        });
      }
      savePresetFromForm();
    });
  });

  [
    "apiBaseUrl",
    "apiKey",
    "modelName",
    "temperature",
    "timeoutSec",
    "historyLimit",
    "maxTokens",
    "themeSelect",
    "uiOpacity",
    "backgroundOverlay",
    "backgroundImageUrl",
    "musicPresetSelect",
    "musicUrlInput",
    "embeddingBaseUrl",
    "embeddingApiKey",
    "embeddingModel",
    "retrievalTopK",
    "rerankEnabled",
    "rerankBaseUrl",
    "rerankApiKey",
    "rerankModel",
    "rerankTopN",
  ].forEach((id) => {
    const node = qs(id);
    const eventName = node.tagName === "SELECT" ? "change" : "input";
    node.addEventListener(eventName, saveSettingsFromForm);
  });

  [
    "userDisplayName",
    "userNickname",
    "userProfileText",
    "userNotes",
    "userAvatarUrl",
    "userRoleAvatarUrl",
  ].forEach((id) => {
    const node = qs(id);
    if (!node) return;
    node.addEventListener("input", saveUserProfileFromForm);
  });

  if (qs("userAvatarFile")) {
    qs("userAvatarFile").addEventListener("change", (event) => void importAvatarImage(event, "avatarUrl"));
  }
  if (qs("userRoleAvatarFile")) {
    qs("userRoleAvatarFile").addEventListener("change", (event) => void importAvatarImage(event, "roleAvatarUrl"));
  }
  if (qs("userAvatarUploadButton") && qs("userAvatarFile")) {
    qs("userAvatarUploadButton").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      pickAvatarFromUi("avatarUrl");
    });
  }
  if (qs("userRoleAvatarUploadButton") && qs("userRoleAvatarFile")) {
    qs("userRoleAvatarUploadButton").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      pickAvatarFromUi("roleAvatarUrl");
    });
  }

  qs("backgroundFileInput").addEventListener("change", (event) => void importBackgroundImage(event));
  qs("clearBackgroundButton").addEventListener("click", () => {
    state.settings.backgroundImageUrl = "";
    saveState();
    renderAll();
    setStatus("背景已清空");
  });

  if (qs("saveRefreshConfigButton")) {
    qs("saveRefreshConfigButton").addEventListener("click", saveAndRefreshSettings);
  }
  const bindWorkshopNavButton = (id) => {
    const node = qs(id);
    if (!node) return;
    node.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      navigate("workshop");
    });
  };
  bindWorkshopNavButton("openWorkshopButton");
  bindWorkshopNavButton("openWorkshopButtonCard");
  bindWorkshopNavButton("openWorkshopButtonCard2");

  [
    "cardSourceName",
    "cardName",
    "cardTags",
    "cardDescription",
    "cardPersonality",
    "cardScenario",
    "cardFirstMes",
    "cardMesExample",
    "cardCreatorNotes",
  ].forEach((id) => {
    qs(id).addEventListener("input", updateCardFromForm);
  });

  qs("addPlotStageButton").addEventListener("click", () => {
    const card = normalizeRoleCard(getCurrentCardStore().raw);
    card.plotStages[getNextStageKey(card.plotStages)] = blankPlotStage();
    getCurrentCardStore().raw = card;
    state.persona = derivePersonaFromRoleCard(card);
    saveState();
    renderCard();
    bindDynamicEditors();
  });

  qs("addPersonaButton").addEventListener("click", () => {
    const card = normalizeRoleCard(getCurrentCardStore().raw);
    card.personas[getNextNumericKey(card.personas)] = blankPersona();
    getCurrentCardStore().raw = card;
    state.persona = derivePersonaFromRoleCard(card);
    saveState();
    renderCard();
    bindDynamicEditors();
  });

  qs("applySingleTemplateButton").addEventListener("click", () => {
    applyCardTemplate(createSingleRoleTemplate, "single_role_template");
  });
  qs("applyMultiTemplateButton").addEventListener("click", () => {
    applyCardTemplate(createMultiRoleTemplate, "multi_role_template");
  });
  qs("cardImportInput").addEventListener("change", (event) => void importRoleCard(event));
  qs("exportCardButton").addEventListener("click", exportCurrentCard);
  if (qs("workshopEnabled")) {
    qs("workshopEnabled").addEventListener("change", updateCardFromForm);
  }
  if (qs("workshopRuleSearch")) {
    qs("workshopRuleSearch").addEventListener("input", applyWorkshopRuleSearch);
  }
  if (qs("addWorkshopRuleButton")) {
    qs("addWorkshopRuleButton").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      addWorkshopRuleToCurrentCard();
    });
  }
  if (qs("collapseAllWorkshopRules")) {
    qs("collapseAllWorkshopRules").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setAllWorkshopRulesCollapsed(true);
    });
  }
  if (qs("expandAllWorkshopRules")) {
    qs("expandAllWorkshopRules").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setAllWorkshopRulesCollapsed(false);
    });
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.(".fake-file-button");
    if (!button) return;
    if (event.target && event.target.tagName === "INPUT") return;
    let input = button.querySelector('input[type="file"]');
    if (!input) {
      input = button.parentElement?.querySelector('input[type="file"]') || null;
    }
    if (!input && button.nextElementSibling?.matches?.('input[type="file"]')) {
      input = button.nextElementSibling;
    }
    if (!input) return;
    event.preventDefault();
    event.stopPropagation();
    openFileInputPicker(input);
  });

  [
    "worldbookEnabled",
    "worldbookDebugEnabled",
    "worldbookMaxEntries",
    "worldbookDefaultMatchMode",
    "worldbookDefaultSecondaryMode",
    "worldbookDefaultEntryType",
    "worldbookDefaultGroupOperator",
    "worldbookDefaultChance",
    "worldbookDefaultStickyTurns",
    "worldbookDefaultCooldownTurns",
    "worldbookDefaultInsertionPosition",
    "worldbookDefaultInjectionDepth",
    "worldbookDefaultInjectionRole",
    "worldbookDefaultInjectionOrder",
    "worldbookRecursiveScanEnabled",
    "worldbookRecursionMaxDepth",
    "worldbookCaseSensitive",
    "worldbookWholeWord",
  ].forEach((id) => {
    const node = qs(id);
    if (!node) return;
    node.addEventListener(node.matches('input[type="number"], input[type="text"]') ? "input" : "change", updateWorldbookSettingsFromForm);
  });
  qs("addWorldbookButton").addEventListener("click", () => {
    const slot = getActiveSlot();
    slot.worldbook = sanitizeWorldbookStore(slot.worldbook);
    slot.worldbook.entries.unshift(createDefaultWorldbookEntry(slot.worldbook.settings));
    saveState();
    renderWorldbook();
    bindDynamicEditors();
  });

  if (qs("worldbookSearch")) {
    qs("worldbookSearch").addEventListener("input", applyWorldbookSearch);
  }
  if (qs("collapseAllWorldbook")) {
    qs("collapseAllWorldbook").addEventListener("click", () => {
      [...qs("worldbookList").querySelectorAll("details")].forEach((card) => setWorldbookCollapsed(card, true));
      setStatus("已折叠当前页面中的全部世界书词条。");
    });
  }
  if (qs("expandAllWorldbook")) {
    qs("expandAllWorldbook").addEventListener("click", () => {
      [...qs("worldbookList").querySelectorAll("details")].forEach((card) => setWorldbookCollapsed(card, false));
      setStatus("已展开当前页面中的全部世界书词条。");
    });
  }
  if (qs("selectAllVisibleWorldbook")) {
    qs("selectAllVisibleWorldbook").addEventListener("click", () => {
      qs("worldbookList").querySelectorAll(".worldbook-card").forEach((card) => {
        if (card.style.display === "none") return;
        const input = card.querySelector("[data-worldbook-selected]");
        if (input) input.checked = true;
      });
      updateSelectedWorldbookCount();
      setStatus("已选择当前可见的世界书词条。");
    });
  }
  if (qs("clearSelectedWorldbook")) {
    qs("clearSelectedWorldbook").addEventListener("click", () => {
      qs("worldbookList").querySelectorAll("[data-worldbook-selected]").forEach((input) => {
        input.checked = false;
      });
      updateSelectedWorldbookCount();
      setStatus("已清空世界书选择。");
    });
  }
  if (qs("bulkEnableSelected")) {
    qs("bulkEnableSelected").addEventListener("click", () => {
      const slot = getActiveSlot();
      const indexes = getSelectedWorldbookIndexes();
      indexes.forEach((index) => {
        if (slot.worldbook.entries[index]) slot.worldbook.entries[index].enabled = true;
      });
      saveState();
      renderWorldbook();
      bindDynamicEditors();
      setStatus(`已启用 ${indexes.length} 条世界书词条。`);
    });
  }
  if (qs("bulkDisableSelected")) {
    qs("bulkDisableSelected").addEventListener("click", () => {
      const slot = getActiveSlot();
      const indexes = getSelectedWorldbookIndexes();
      indexes.forEach((index) => {
        if (slot.worldbook.entries[index]) slot.worldbook.entries[index].enabled = false;
      });
      saveState();
      renderWorldbook();
      bindDynamicEditors();
      setStatus(`已停用 ${indexes.length} 条世界书词条。`);
    });
  }
  if (qs("applyBulkInjection")) {
    qs("applyBulkInjection").addEventListener("click", () => {
      const slot = getActiveSlot();
      const indexes = getSelectedWorldbookIndexes();
      const position = normalizeWorldbookInsertionPosition(qs("bulkInsertionPosition").value, "after_char_defs");
      const depth = clampInteger(qs("bulkInjectionDepth").value, 0, 3, 0);
      const order = clampInteger(qs("bulkInjectionOrder").value, 0, 999999, 100);
      indexes.forEach((index) => {
        const entry = slot.worldbook.entries[index];
        if (!entry) return;
        entry.insertionPosition = position;
        entry.injectionDepth = depth;
        entry.injectionOrder = order;
      });
      saveState();
      renderWorldbook();
      bindDynamicEditors();
      setStatus(`已更新 ${indexes.length} 条词条的注入设置。`);
    });
  }
  if (qs("applyBulkRecursion")) {
    qs("applyBulkRecursion").addEventListener("click", () => {
      const slot = getActiveSlot();
      const indexes = getSelectedWorldbookIndexes();
      const recursiveEnabled = qs("bulkRecursiveEnabled").checked;
      const preventFurtherRecursion = qs("bulkPreventFurtherRecursion").checked;
      indexes.forEach((index) => {
        const entry = slot.worldbook.entries[index];
        if (!entry) return;
        entry.recursiveEnabled = recursiveEnabled;
        entry.preventFurtherRecursion = preventFurtherRecursion;
      });
      saveState();
      renderWorldbook();
      bindDynamicEditors();
      setStatus(`已更新 ${indexes.length} 条词条的递归设置。`);
    });
  }
  if (qs("importWorldbookButton")) {
    qs("importWorldbookButton").addEventListener("click", () => qs("importWorldbookFile").click());
  }
  if (qs("importWorldbookFile")) {
    qs("importWorldbookFile").addEventListener("change", (event) => void importWorldbook(event));
  }
  if (qs("exportWorldbookButton")) {
    qs("exportWorldbookButton").addEventListener("click", exportWorldbook);
  }

  qs("addMemoryButton").addEventListener("click", () => {
    const slot = getActiveSlot();
    slot.memories.unshift(sanitizeMemoryItem({
      id: `memory-manual-${Date.now().toString(36)}`,
      title: "新的记忆片段",
      content: "",
      tags: ["memory-fragment"],
      notes: "",
    }));
    cleanupDeletedMemories(slot);
    saveState();
    renderMemory();
    bindDynamicEditors();
  });

  if (qs("memorySearch")) {
    qs("memorySearch").addEventListener("input", applyMemorySearch);
  }
  if (qs("collapseAllMemories")) {
    qs("collapseAllMemories").addEventListener("click", () => {
      [...qs("memoryList").querySelectorAll("details")].forEach((card) => setMemoryCollapsed(card, true));
      setStatus("已折叠当前页面中的全部记忆。");
    });
  }
  if (qs("expandAllMemories")) {
    qs("expandAllMemories").addEventListener("click", () => {
      [...qs("memoryList").querySelectorAll("details")].forEach((card) => setMemoryCollapsed(card, false));
      setStatus("已展开当前页面中的全部记忆。");
    });
  }
  if (qs("selectVisibleMemoriesButton")) {
    qs("selectVisibleMemoriesButton").addEventListener("click", () => {
      qs("memoryList").querySelectorAll(".memory-card").forEach((card) => {
        if (card.style.display === "none") return;
        const input = card.querySelector("[data-memory-selected]");
        if (input) input.checked = true;
      });
      updateMemoryStats();
      setStatus("已选择当前可见的记忆。");
    });
  }
  if (qs("clearSelectedMemoriesButton")) {
    qs("clearSelectedMemoriesButton").addEventListener("click", () => {
      qs("memoryList").querySelectorAll("[data-memory-selected]").forEach((input) => {
        input.checked = false;
      });
      updateMemoryStats();
      setStatus("已清空记忆选择。");
    });
  }
  if (qs("mergeSelectedMemoriesButton")) {
    qs("mergeSelectedMemoriesButton").addEventListener("click", () => void mergeSelectedMemories());
  }
  if (qs("importMemoryButton")) {
    qs("importMemoryButton").addEventListener("click", () => qs("importMemoryFile").click());
  }
  if (qs("importMemoryFile")) {
    qs("importMemoryFile").addEventListener("change", (event) => void importMemories(event));
  }
  if (qs("exportMemoryButton")) {
    qs("exportMemoryButton").addEventListener("click", exportMemories);
  }
  if (qs("exportMergedMemoryButton")) {
    qs("exportMergedMemoryButton").addEventListener("click", exportMergedMemories);
  }
  if (qs("exportMemoryOutlineButton")) {
    qs("exportMemoryOutlineButton").addEventListener("click", exportMemoryOutline);
  }

  qs("exportStateButton").addEventListener("click", exportState);
  if (qs("exportBundleButton")) {
    qs("exportBundleButton").addEventListener("click", () => void exportCurrentBundle());
  }
  qs("importStateInput").addEventListener("change", (event) => void importState(event));

  qs("playMusicButton").addEventListener("click", playMusic);
  qs("pauseMusicButton").addEventListener("click", pauseMusic);
  qs("stopMusicButton").addEventListener("click", stopMusic);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) flushActiveTypewriter();
  });
}

function renderAll() {
  syncCreativeWorkshopRuntime("sync");
  navigate(state.activeRoute);
}

window.XuqiMobileApp = {
  navigate,
  addWorkshopRule: addWorkshopRuleToCurrentCard,
  collapseWorkshopRules: () => setAllWorkshopRulesCollapsed(true),
  expandWorkshopRules: () => setAllWorkshopRulesCollapsed(false),
  pickAvatar: (fieldName) => pickAvatarFromUi(fieldName),
  onNativeChatResult(payloadJson) {
    try {
      const payload = typeof payloadJson === "string" ? JSON.parse(payloadJson) : payloadJson;
      const requestId = String(payload?.requestId || "");
      const pending = pendingNativeRequests.get(requestId);
      if (!pending) return;
      pendingNativeRequests.delete(requestId);
      if (payload.ok) {
        pending.resolve(String(payload.content || ""));
      } else {
        pending.reject(new Error(payload.error || "模型请求失败"));
      }
    } catch (error) {
      console.error(error);
    }
  },
  onNativeSaveResult(payloadJson) {
    try {
      const payload = typeof payloadJson === "string" ? JSON.parse(payloadJson) : payloadJson;
      const requestId = String(payload?.requestId || "");
      const pending = pendingNativeSaveRequests.get(requestId);
      if (!pending) return;
      pendingNativeSaveRequests.delete(requestId);
      if (payload.ok) {
        pending.resolve(String(payload.uri || ""));
      } else {
        pending.reject(new Error(payload.error || "文件导出失败"));
      }
    } catch (error) {
      console.error(error);
    }
  },
  onNativeImagePickResult(payloadJson) {
    try {
      const payload = typeof payloadJson === "string" ? JSON.parse(payloadJson) : payloadJson;
      const requestId = String(payload?.requestId || "");
      const pending = pendingNativeImagePickRequests.get(requestId);
      if (!pending) return;
      pendingNativeImagePickRequests.delete(requestId);
      if (payload.ok) {
        pending.resolve(String(payload.dataUrl || ""));
      } else {
        pending.reject(new Error(payload.error || "图片选择失败"));
      }
    } catch (error) {
      console.error(error);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => {
  bindGlobalEvents();
  renderAll();
});

window.addEventListener("beforeunload", flushState);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) flushState();
});
