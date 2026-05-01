(() => {
  const FIELD_MAP = {
    "type": "type",
    "类型": "type",
    "id": "id",
    "name": "name",
    "姓名": "name",
    "角色名": "name",
    "人物名": "name",
    "aliases": "aliases",
    "alias": "aliases",
    "别名": "aliases",
    "常用称呼": "aliases",
    "称呼": "aliases",
    "group": "group",
    "分组": "group",
    "alive_status": "alive_status",
    "生存状态": "alive_status",
    "存活状态": "alive_status",
    "hp": "hp",
    "HP": "hp",
    "血量": "hp",
    "生命": "hp",
    "mp": "mp",
    "MP": "mp",
    "魔力": "mp",
    "灵力": "mp",
    "法力": "mp",
    "location": "location",
    "位置": "location",
    "地点": "location",
    "relationship": "relationship",
    "关系": "relationship",
    "effects": "effects",
    "status_effects": "effects",
    "状态": "effects",
    "异常状态": "effects",
    "effects_add": "effects_add",
    "新增状态": "effects_add",
    "effects_remove": "effects_remove",
    "移除状态": "effects_remove",
    "summary": "summary",
    "short_summary": "summary",
    "摘要": "summary",
    "简介": "summary",
    "说明": "summary",
  };

  const EXTRA_KEY_ALIASES = {
    equipment: "装备", equips: "装备", item: "装备", items: "装备", gear: "装备", 装备: "装备", 物品: "装备", 携带物: "装备",
    goal: "当前目标", target: "当前目标", current_goal: "当前目标", currenttarget: "当前目标", objective: "当前目标", 当前目标: "当前目标", 目标: "当前目标",
    mental: "精神状态", mental_status: "精神状态", emotion: "精神状态", mood: "精神状态", 精神: "精神状态", 精神状态: "精神状态", 情绪: "精神状态",
    action: "行动状态", action_status: "行动状态", current_action: "行动状态", 行动: "行动状态", 行动状态: "行动状态", 当前动作: "行动状态",
    leg: "腿部状态", legs: "腿部状态", leg_status: "腿部状态", 腿部: "腿部状态", 腿部状态: "腿部状态",
  };

  function normalizeExtraKey(key) {
    const raw = compact(key).replace(/\s+/g, "");
    if (!raw) return "";
    const lower = raw.toLowerCase().replace(/[\- ]+/g, "_");
    return EXTRA_KEY_ALIASES[raw] || EXTRA_KEY_ALIASES[lower] || raw;
  }

  const SOURCE_DEFS = [
    {
      key: "history",
      label: "最近聊天",
      weight: 80,
      url: "/api/history",
      pickTexts(data) {
        const rows = Array.isArray(data) ? data.slice(-80) : [];
        return rows.map((item, index) => ({
          text: flattenObjectText({ role: item.role, content: item.content || item.text || item.message || "" }),
          source: "最近聊天",
          source_key: "history",
          source_index: index,
        }));
      },
    },
    {
      key: "memory_outline",
      label: "记忆大纲",
      weight: 60,
      url: "/api/memories/outline",
      pickTexts(data) {
        const rows = Array.isArray(data?.items) ? data.items : [];
        return rows.map((item, index) => ({
          text: flattenObjectText(item),
          source: "记忆大纲",
          source_key: "memory_outline",
          source_index: index,
          source_id: item?.id || `memory_outline-${index}`,
          source_title: item?.title || item?.name || `记忆大纲 ${index + 1}`,
        }));
      },
    },
    {
      key: "merged_memories",
      label: "合并记忆",
      weight: 50,
      url: "/api/memories/merged",
      pickTexts(data) {
        const rows = Array.isArray(data?.items) ? data.items : [];
        return rows.map((item, index) => ({
          text: flattenObjectText(item),
          source: "合并记忆",
          source_key: "merged_memories",
          source_index: index,
          source_id: item?.id || `merged_memory-${index}`,
          source_title: item?.title || item?.name || `合并记忆 ${index + 1}`,
        }));
      },
    },
    {
      key: "memories",
      label: "原记忆",
      weight: 40,
      url: "/api/memories",
      pickTexts(data) {
        const rows = Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : [];
        return rows.map((item, index) => ({
          text: flattenObjectText(item),
          source: "原记忆",
          source_key: "memories",
          source_index: index,
          source_id: item?.id || `memory-${index}`,
          source_title: item?.title || `原记忆 ${index + 1}`,
        }));
      },
    },
    {
      key: "worldbook",
      label: "世界书",
      weight: 30,
      url: "/api/worldbook",
      pickTexts(data) {
        const rows = Array.isArray(data?.items) ? data.items : Array.isArray(data?.entries) ? data.entries : [];
        return rows.map((item, index) => ({
          text: [item.title || "", item.group || "", item.comment || "", item.trigger || "", item.secondary_trigger || "", item.content || ""].join("\n"),
          source: "世界书",
          source_key: "worldbook",
          source_index: index,
        }));
      },
    },
    {
      key: "persona",
      label: "角色设定",
      weight: 20,
      url: "/api/persona",
      pickTexts(data) {
        return [{ text: flattenObjectText(data), source: "角色设定", source_key: "persona", source_index: 0 }];
      },
    },
    {
      key: "cards",
      label: "当前角色卡",
      weight: 20,
      url: "/api/cards",
      pickTexts(data) {
        const current = data?.current_card || {};
        const raw = current.raw || current.card || current;
        return [{ text: flattenObjectText(raw), source: "当前角色卡", source_key: "cards", source_index: 0 }];
      },
    },
    {
      key: "preset",
      label: "当前预设",
      weight: 10,
      url: "/api/preset",
      pickTexts(data) {
        const active = data?.active_preset || {};
        return [{ text: flattenObjectText(active), source: "当前预设", source_key: "preset", source_index: 0 }];
      },
    },
  ];

  function flattenObjectText(value, depth = 0) {
    if (value == null || depth > 8) return "";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) return value.map((item) => flattenObjectText(item, depth + 1)).filter(Boolean).join("\n");
    if (typeof value === "object") {
      return Object.entries(value)
        .map(([key, val]) => `${key}：${flattenObjectText(val, depth + 1)}`)
        .filter((line) => line.trim() !== "：")
        .join("\n");
    }
    return "";
  }

  function compact(value) {
    return String(value || "").replace(/\r/g, "\n").trim();
  }

  function normalizeText(text) {
    return compact(text)
      .replace(/[|]/g, "｜")
      .replace(/[：]/g, ":")
      .replace(/[，]/g, ",");
  }

  function splitList(value) {
    if (Array.isArray(value)) {
      return value.map((item) => compact(item)).filter(Boolean).filter((item) => !/^(无|none|null)$/i.test(item));
    }
    const text = compact(value);
    if (!text || text === "无" || text === "none" || text === "None") return [];
    return text
      .replace(/[、/]/g, ",")
      .split(",")
      .map((item) => compact(item))
      .filter(Boolean)
      .filter((item) => !/^(无|none|null)$/i.test(item));
  }

  function normalizeAliases(value) {
    return splitList(value).filter((item) => item && !isPlaceholderText(item));
  }

  function normalizeMentionKey(value) {
    return compact(value)
      .replace(/[\s\u3000]+/g, "")
      .replace(/[“”\"'‘’「」『』（）()\[\]【】]/g, "")
      .replace(/[，。！？、,.!?~～—\-…:：;；]/g, "")
      .toLowerCase();
  }

  function textContainsMention(haystack, needle) {
    const source = compact(haystack);
    const target = compact(needle);
    if (!source || !target) return false;
    const latin = /[A-Za-z0-9]/.test(target);
    if (latin) {
      return source.toLowerCase().includes(target.toLowerCase())
        || normalizeMentionKey(source).includes(normalizeMentionKey(target));
    }
    return source.includes(target) || normalizeMentionKey(source).includes(normalizeMentionKey(target));
  }

  function splitPair(value) {
    const text = compact(value);
    if (!text) return ["", ""];
    const match = text.match(/^([^/]+)\s*\/\s*(.+)$/);
    if (!match) return [text, ""];
    return [compact(match[1]), compact(match[2])];
  }

  function mapFieldName(rawKey) {
    const key = compact(rawKey).replace(/\s+/g, "");
    return FIELD_MAP[key] || FIELD_MAP[key.toLowerCase?.()] || key;
  }

  function parseExtraKey(rawKey) {
    const key = compact(rawKey).replace(/\s+/g, "");
    const match = key.match(/^(?:extra|extras|custom|扩展|自定义)[.．。:：](.+)$/i);
    return match ? normalizeExtraKey(match[1]) : "";
  }

  function parseKeyValueBlock(body) {
    const result = {};
    compact(body).split(/\n+/).forEach((line) => {
      const match = line.match(/^([^:：]+)[:：]\s*([\s\S]*)$/);
      if (!match) return;
      const extraName = parseExtraKey(match[1]);
      if (extraName) {
        result.extra = result.extra || {};
        result.extra[extraName] = compact(match[2]);
        return;
      }
      const key = mapFieldName(match[1]);
      result[key] = compact(match[2]);
    });
    return result;
  }

  function normalizeExtra(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const result = {};
    Object.entries(value).forEach(([key, rawVal]) => {
      const name = normalizeExtraKey(key);
      const text = Array.isArray(rawVal) ? rawVal.map(compact).filter(Boolean).join("、") : compact(rawVal);
      if (name && text && !isPlaceholderText(text)) result[name] = text;
    });
    return result;
  }

  function normalizeCandidateFields(raw, meta = {}) {
    const candidate = {
      kind: meta.kind || raw.kind || "status_panel",
      source: meta.source || raw.source || "未知来源",
      source_key: meta.source_key || raw.source_key || "",
      source_index: meta.source_index ?? raw.source_index ?? 0,
      source_id: compact(meta.source_id || raw.source_id || ""),
      source_title: compact(meta.source_title || raw.source_title || ""),
      weight: Number(meta.weight || raw.weight || 0),
      raw_text: meta.raw_text || raw.raw_text || "",
      id: compact(raw.id),
      name: compact(raw.name),
      aliases: normalizeAliases(raw.aliases || raw.alias || raw["别名"] || []),
      group: compact(raw.group),
      visible: true,
      alive_status: compact(raw.alive_status),
      hp_current: compact(raw.hp_current),
      hp_max: compact(raw.hp_max),
      mp_current: compact(raw.mp_current),
      mp_max: compact(raw.mp_max),
      location: compact(raw.location),
      relationship: compact(raw.relationship),
      status_effects: [],
      effects_add: [],
      effects_remove: [],
      short_summary: compact(raw.short_summary || raw.summary),
      extra: normalizeExtra(raw.extra || raw.extras || raw.custom || {}),
      confidence: meta.confidence || "中",
    };

    if ((!candidate.hp_current && !candidate.hp_max) && raw.hp) {
      [candidate.hp_current, candidate.hp_max] = splitPair(raw.hp);
    }
    if ((!candidate.mp_current && !candidate.mp_max) && raw.mp) {
      [candidate.mp_current, candidate.mp_max] = splitPair(raw.mp);
    }

    candidate.status_effects = Array.isArray(raw.status_effects)
      ? raw.status_effects.map(compact).filter(Boolean)
      : splitList(raw.status_effects || raw.effects);
    candidate.effects_add = Array.isArray(raw.effects_add) ? raw.effects_add.map(compact).filter(Boolean) : splitList(raw.effects_add);
    candidate.effects_remove = Array.isArray(raw.effects_remove) ? raw.effects_remove.map(compact).filter(Boolean) : splitList(raw.effects_remove);

    if (!candidate.id && candidate.name) {
      candidate.id = toSlug(candidate.name);
    }
    return candidate;
  }

  function toSlug(value) {
    const ascii = compact(value)
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return ascii || `char-${Math.random().toString(16).slice(2, 10)}`;
  }

  function isPlaceholderText(value) {
    const text = compact(value);
    if (!text) return false;
    return /角色姓名|角色名|人物名|角色英文|拼音id|当前值|上限|未知则写|用逗号|没有写|一句话|状态1|状态2|示例|例如|可为空|xxx|XXX/.test(text);
  }

  function isInvalidCandidateName(name) {
    const text = compact(name);
    if (!text) return true;
    const lower = text.toLowerCase();
    if ([
      "name",
      "id",
      "type",
      "group",
      "alive_status",
      "hp",
      "mp",
      "location",
      "relationship",
      "effects",
      "status_effects",
      "effects_add",
      "effects_remove",
      "summary",
      "short_summary",
    ].includes(lower)) return true;
    return /角色姓名|角色名|人物名|字段|格式|模板|示例|当前值|上限|未知则写|状态栏更新块/.test(text);
  }

  function isTemplateCandidate(candidate) {
    if (!candidate || isInvalidCandidateName(candidate.name)) return true;

    const valuesToCheck = [
      candidate.id,
      candidate.name,
      candidate.group,
      candidate.alive_status,
      candidate.hp_current,
      candidate.hp_max,
      candidate.mp_current,
      candidate.mp_max,
      candidate.location,
      candidate.relationship,
      candidate.short_summary,
      ...(candidate.status_effects || []),
      ...(candidate.effects_add || []),
      ...(candidate.effects_remove || []),
      ...Object.keys(candidate.extra || {}),
      ...Object.values(candidate.extra || {}),
    ];

    // 预设里经常会放“格式模板”，这类块只用于教模型，不应该变成状态候选。
    if (valuesToCheck.some(isPlaceholderText)) return true;

    // hp/mp 如果被解析成了“当前值/上限”之类，也直接丢弃。
    const resourceText = [candidate.hp_current, candidate.hp_max, candidate.mp_current, candidate.mp_max].join("/");
    if (/当前值|上限|未知/.test(resourceText)) {
      return true;
    }

    return false;
  }

  function hasUsefulFields(candidate) {
    if (isTemplateCandidate(candidate)) return false;
    return Boolean(
      candidate.name && (
        candidate.alive_status || candidate.hp_current || candidate.hp_max || candidate.mp_current || candidate.mp_max ||
        candidate.location || candidate.relationship || candidate.status_effects.length ||
        candidate.effects_add.length || candidate.effects_remove.length || candidate.short_summary || Object.keys(candidate.extra || {}).length
      )
    );
  }

  function isStatusMarkerLine(line) {
    return /^(?:status_panel|status_panel_update)\s*$/i.test(compact(line));
  }

  function markerKind(line, fallbackKind = "status_panel_update") {
    const text = compact(line).toLowerCase();
    if (text === "status_panel" || text === "status_panel_update") return text;
    return fallbackKind;
  }

  function splitStatusBody(kind, body, rawPrefix = "") {
    const lines = compact(body).split(/\n/);
    const segments = [];
    let currentKind = kind;
    let current = [];

    for (const line of lines) {
      if (isStatusMarkerLine(line)) {
        if (current.join("\n").trim()) {
          segments.push({ kind: currentKind, body: current.join("\n").trim() });
        }
        currentKind = markerKind(line, kind);
        current = [];
        continue;
      }
      current.push(line);
    }

    if (current.join("\n").trim()) {
      segments.push({ kind: currentKind, body: current.join("\n").trim() });
    }

    return segments.map((segment) => ({
      ...segment,
      raw: rawPrefix || `status_segment:${segment.kind}\n${segment.body}`,
    }));
  }

  function extractFencedStatusBlocks(text) {
    const blocks = [];
    const normalized = compact(text);
    const regex = /```\s*(status_panel|status_panel_update)\s*\n([\s\S]*?)```/gi;
    let match;
    while ((match = regex.exec(normalized)) !== null) {
      const kind = match[1].toLowerCase();
      const body = match[2].trim();
      const segments = splitStatusBody(kind, body, match[0]);
      segments.forEach((segment) => blocks.push({ ...segment, raw: segment.raw || match[0] }));
    }
    return blocks;
  }

  function extractNakedStatusBlocks(text) {
    const blocks = [];
    const normalized = compact(text);
    const lines = normalized.split(/\n/);
    let collecting = false;
    let currentKind = "status_panel_update";
    let current = [];

    function flush() {
      const body = current.join("\n").trim();
      if (body) {
        blocks.push({ kind: currentKind, body, raw: `${currentKind}\n${body}` });
      }
      current = [];
    }

    for (const line of lines) {
      if (isStatusMarkerLine(line)) {
        if (collecting) flush();
        collecting = true;
        currentKind = markerKind(line, "status_panel_update");
        continue;
      }

      if (!collecting) continue;

      if (!line.trim()) {
        current.push(line);
        continue;
      }

      // 裸露格式只收 key: value 行，遇到普通正文就结束，避免误吞聊天正文。
      if (!/^([^:：]+)[:：]\s*([\s\S]*)$/.test(line)) {
        flush();
        collecting = false;
        currentKind = "status_panel_update";
        continue;
      }
      current.push(line);
    }
    if (collecting) flush();
    return blocks;
  }

  function extractStatusBlocks(text, options = {}) {
    const sourceKey = options.source_key || options.sourceKey || "";
    const blocks = extractFencedStatusBlocks(text);

    // 聊天模型有时会漏掉第二、第三个代码块围栏，只输出裸露的 status_panel_update 段。
    // 为避免预设模板误扫，裸露段默认只在聊天来源启用。
    if (sourceKey === "history" || options.allowNaked === true) {
      const nakedText = String(text || "").replace(/```\s*(?:status_panel|status_panel_update)\s*\n[\s\S]*?```/gi, "");
      blocks.push(...extractNakedStatusBlocks(nakedText));
    }

    return blocks;
  }

  function applyFragment(candidate, fragment) {
    const text = compact(fragment).replace(/[：]/g, ":");
    if (!text) return;

    if (/^(存活|死亡|已死|重伤|轻伤|昏迷|失踪|未知|濒死)$/.test(text)) {
      candidate.alive_status = text;
      return;
    }

    let match = text.match(/^(?:HP|血量|生命)\s*:?\s*([?\d]+)\s*\/\s*([?\d]+)/i);
    if (match) {
      candidate.hp_current = match[1];
      candidate.hp_max = match[2];
      return;
    }

    match = text.match(/^(?:MP|魔力|灵力|法力)\s*:?\s*([?\d]+)\s*\/\s*([?\d]+)/i);
    if (match) {
      candidate.mp_current = match[1];
      candidate.mp_max = match[2];
      return;
    }

    match = text.match(/^(?:位置|地点|当前位于|位于|在)\s*:?\s*(.+)$/);
    if (match) {
      candidate.location = cleanTail(match[1]);
      return;
    }

    match = text.match(/^(?:关系|身份关系)\s*:?\s*(.+)$/);
    if (match) {
      candidate.relationship = cleanTail(match[1]);
      return;
    }

    match = text.match(/^(?:状态|异常状态|负面状态|增益状态)\s*:?\s*(.+)$/);
    if (match) {
      candidate.status_effects = splitList(match[1]);
      return;
    }

    match = text.match(/^(?:摘要|简介|说明)\s*:?\s*(.+)$/);
    if (match) {
      candidate.short_summary = cleanTail(match[1]);
    }
  }

  function cleanTail(value) {
    return compact(value).replace(/[。；;,，]+$/g, "").trim();
  }

  function extractPipeRows(text, meta) {
    const candidates = [];
    normalizeText(text).split(/\n+/).forEach((line) => {
      const row = compact(line);
      if (!row.includes("｜")) return;
      const parts = row.split("｜").map(compact).filter(Boolean);
      if (parts.length < 2) return;
      const candidate = normalizeCandidateFields({ name: parts[0] }, { ...meta, kind: "loose", raw_text: row, confidence: "低" });
      parts.slice(1).forEach((part) => applyFragment(candidate, part));
      if (hasUsefulFields(candidate)) candidates.push(candidate);
    });
    return candidates;
  }

  function extractLooseBlocks(text, meta) {
    const normalized = normalizeText(text);
    const name = matchOne(normalized, /(?:姓名|角色名|人物名|角色)\s*:\s*([^\n,。｜]+)/);
    if (!name) return [];

    const candidate = normalizeCandidateFields({ name }, { ...meta, kind: "loose", raw_text: normalized.slice(0, 600), confidence: "低" });
    const alive = matchOne(normalized, /(?:生存状态|存活状态)\s*:\s*(存活|死亡|已死|重伤|轻伤|昏迷|失踪|未知|濒死)/);
    if (alive) candidate.alive_status = alive;

    const hp = normalized.match(/(?:HP|血量|生命)\s*:\s*([?\d]+)\s*\/\s*([?\d]+)/i);
    if (hp) {
      candidate.hp_current = hp[1];
      candidate.hp_max = hp[2];
    }
    const mp = normalized.match(/(?:MP|魔力|灵力|法力)\s*:\s*([?\d]+)\s*\/\s*([?\d]+)/i);
    if (mp) {
      candidate.mp_current = mp[1];
      candidate.mp_max = mp[2];
    }

    const location = matchOne(normalized, /(?:位置|地点|当前位于|位于)\s*:\s*([^\n。]+)/);
    if (location) candidate.location = cleanTail(location);
    const relation = matchOne(normalized, /(?:关系|身份关系)\s*:\s*([^\n。]+)/);
    if (relation) candidate.relationship = cleanTail(relation);
    const effects = matchOne(normalized, /(?:异常状态|负面状态|增益状态|状态)\s*:\s*([^\n。]+)/);
    if (effects) candidate.status_effects = splitList(effects);
    const summary = matchOne(normalized, /(?:摘要|简介|说明)\s*:\s*([^\n]+)/);
    if (summary) candidate.short_summary = cleanTail(summary);

    return hasUsefulFields(candidate) ? [candidate] : [];
  }

  function extractSentenceRows(text, meta) {
    const rows = normalizeText(text).split(/\n+/).map(compact).filter(Boolean);
    const candidates = [];
    for (const row of rows) {
      const match = row.match(/^([\u4e00-\u9fa5A-Za-z0-9_·\-]{2,30})\s*:\s*(.+)$/);
      if (!match) continue;
      const name = compact(match[1]);
      const body = compact(match[2]);
      if (!/(HP|血量|生命|MP|魔力|灵力|法力|存活|死亡|重伤|昏迷|失踪|位置|状态)/i.test(body)) continue;
      const candidate = normalizeCandidateFields({ name }, { ...meta, kind: "loose", raw_text: row, confidence: "低" });
      body.split(/[,，;；]/).forEach((part) => applyFragment(candidate, part));
      if (hasUsefulFields(candidate)) candidates.push(candidate);
    }
    return candidates;
  }

  function cleanMemoryProseText(text) {
    const raw = normalizeText(text);
    if (!raw) return "";
    const titleMatch = raw.match(/(?:^|\n|\s)title\s*:\s*([\s\S]*?)(?=(?:\n|\s)content\s*:|$)/i);
    const contentMatch = raw.match(/(?:^|\n|\s)content\s*:\s*([\s\S]*)/i);
    const parts = [];
    if (titleMatch?.[1]) parts.push(cleanTail(titleMatch[1]));
    if (contentMatch?.[1]) parts.push(cleanTail(contentMatch[1]));
    const cleaned = parts.length ? parts.join("\n") : raw;
    return cleaned
      .replace(/(?:^|\n)id\s*:\s*[^\n]+/gi, "")
      .replace(/(?:^|\n)created_at\s*:\s*[^\n]+/gi, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function characterMatchTokens(character) {
    const tokens = [];
    const seen = new Set();
    const add = (value, type = "name") => {
      const text = compact(value);
      if (!text) return;
      if (isInvalidCandidateName(text) || isPlaceholderText(text)) return;
      if (text.length < 2 && !/[A-Za-z0-9]/.test(text)) return;
      const key = `${type}:${normalizeMentionKey(text)}`;
      if (seen.has(key)) return;
      seen.add(key);
      tokens.push({ text, type, key: normalizeMentionKey(text), character });
    };
    add(character.name, "name");
    normalizeAliases(character.aliases || character.alias || []).forEach((alias) => add(alias, "alias"));
    const id = compact(character.id);
    if (id && !/^char-[a-f0-9]{6,}$/i.test(id)) add(id, "id");
    return tokens;
  }

  function findExistingCharacterMention(text, characters = []) {
    const normalized = normalizeText(text);
    if (!normalized || !Array.isArray(characters) || !characters.length) return null;
    const tokens = characters.flatMap(characterMatchTokens).sort((a, b) => b.text.length - a.text.length);
    const normalizedKey = normalizeMentionKey(normalized);
    for (const token of tokens) {
      if (textContainsMention(normalized, token.text) || (token.key && normalizedKey.includes(token.key))) {
        return { character: token.character, matched: token.text, match_type: token.type };
      }
    }
    return null;
  }

  function extractMemoryProseCandidates(text, meta) {
    const sourceKey = meta?.source_key || meta?.sourceKey || "";
    if (!["memories", "merged_memories", "memory_outline"].includes(sourceKey)) return [];
    const normalized = cleanMemoryProseText(text);
    if (!normalized || normalized.length < 6) return [];
    const notesMatch = normalized.match(/(?:^|\n|\s)notes\s*:\s*([\s\S]*?)(?=(?:\n|\s)(?:title|content|tags|id)\s*:|$)/i);
    const noteText = notesMatch?.[1] ? cleanTail(notesMatch[1]) : "";
    const scanText = noteText ? `${noteText}\n${normalized}` : normalized;

    // 原记忆区是自然语言：只能绑定已有角色或 aliases，不能自动新建角色。
    const mention = findExistingCharacterMention(normalized, meta?.existingCharacters || []);
    if (!mention?.character) return [];
    const existing = mention.character;
    const name = compact(existing.name) || compact(mention.matched);

    const candidate = normalizeCandidateFields({ id: existing.id || "", name, aliases: existing.aliases || [] }, {
      ...meta,
      kind: "loose_memory",
      raw_text: normalized.slice(0, 1200),
      confidence: "低",
    });
    candidate.matched_alias = mention.match_type === "alias" ? mention.matched : "";
    candidate.matched_name = mention.matched || "";

    let match = scanText.match(/(?:当前所在位置|所在位置|当前位置|地点|位置)\s*[:：]?\s*([^,，。；\n]{1,38})/);
    if (match?.[1]) candidate.location = cleanTail(match[1]);

    if (!candidate.location) match = scanText.match(new RegExp(`${escapeRegExp(mention.matched)}\\s*(?:在|位于|当前位于|地点在)\\s*([^,，。；\\n]{1,28})`, "i"));
    if (match?.[1] && !candidate.location) {
      let location = cleanTail(match[1])
        .replace(/(?:等待|等候|坐在|站在|坐着|站着|拿|取|研究|开始|正在|并|和|,|，|。).*$/g, "")
        .trim();
      if (location && location.length <= 18) candidate.location = location;
    }

    if (!candidate.location) {
      match = scanText.match(new RegExp(`${escapeRegExp(mention.matched)}[^,，。；\\n]{0,16}(?:走到|走进|进入|来到|移动到|转移到|抵达|到达)\\s*([^,，。；\\n]{1,28})`, "i"));
      if (match?.[1]) {
        candidate.location = cleanTail(match[1]).replace(/(?:等待|等候|坐在|站在|拿|取|开始|正在|并|和|,|，|。).*$/g, "").trim();
      }
    }

    match = scanText.match(/(?:地点|位置)\s*[:：]?\s*([^,，。；\n]{1,28})/);
    if (match?.[1] && !candidate.location) candidate.location = cleanTail(match[1]);

    match = scanText.match(/(?:HP|hp|血量|生命值?)\s*[:：]?\s*([0-9]+)\s*\/\s*([0-9]+)/i);
    if (match) {
      candidate.hp_current = match[1];
      candidate.hp_max = match[2];
    } else {
      match = scanText.match(/(?:HP|hp|血量|生命值?)(?:和|与|及)?(?:MP|mp|魔力|灵力|法力)?[^,，。；\n]{0,12}(?:恢复至|恢复到|变为|变成|降到|下降到|减少到|消耗至|为|=|：|:)\s*([0-9]{1,4})(?:\s*\/\s*([0-9]{1,4}))?/i);
      if (match) {
        candidate.hp_current = match[1];
        candidate.hp_max = match[2] || candidate.hp_max || match[1];
      }
    }

    match = scanText.match(/(?:MP|mp|魔力|灵力|法力)\s*[:：]?\s*([0-9]+)\s*\/\s*([0-9]+)/i);
    if (match) {
      candidate.mp_current = match[1];
      candidate.mp_max = match[2];
    } else {
      match = scanText.match(/(?:HP|hp|血量|生命值?)?[^,，。；\n]{0,8}(?:MP|mp|魔力|灵力|法力)[^,，。；\n]{0,12}(?:恢复至|恢复到|变为|变成|降到|下降到|减少到|消耗至|为|=|：|:)\s*([0-9]{1,4})(?:\s*\/\s*([0-9]{1,4}))?/i);
      if (match) {
        candidate.mp_current = match[1];
        candidate.mp_max = match[2] || candidate.mp_max || "100";
      }
    }

    match = scanText.match(/(?:装备|携带物|持有物|配备)(?:有|为|是|[:：])?\s*([^,，。；\n]{1,40})/);
    if (!match) match = scanText.match(/(?:抱着|拿着|手里拿着)\s*([^,，。；\n]{1,28})/);
    if (match?.[1]) {
      candidate.extra = candidate.extra || {};
      candidate.extra["装备"] = cleanTail(match[1]).replace(/[。；；]+$/g, "");
    }

    match = scanText.match(/(?:当前目标|目标|后续)\s*[:：]?\s*([^,，。；\n]{1,42})/);
    if (match?.[1]) {
      candidate.extra = candidate.extra || {};
      candidate.extra["当前目标"] = cleanTail(match[1]);
    }

    match = scanText.match(/(?:情绪|精神状态|心情)\s*[:：]?\s*([^,，。；\n]{1,24})/);
    if (match?.[1]) {
      candidate.extra = candidate.extra || {};
      candidate.extra["精神状态"] = cleanTail(match[1]);
    } else if (/情绪(?:愉快|稳定|低落|紧张|平静|开心|放松)/.test(normalized)) {
      const mood = matchOne(normalized, /情绪(愉快|稳定|低落|紧张|平静|开心|放松)/);
      if (mood) {
        candidate.extra = candidate.extra || {};
        candidate.extra["精神状态"] = mood;
      }
    }

    if (/身体状态良好|身体良好|状态良好/.test(normalized)) candidate.status_effects = ["无明显异常"];
    if (/等待用户|等用户/.test(normalized)) {
      candidate.extra = candidate.extra || {};
      if (!candidate.extra["当前目标"]) candidate.extra["当前目标"] = "等待用户指示";
    }
    if (!candidate.short_summary) candidate.short_summary = normalized.slice(0, 120).replace(/\n+/g, " ");

    return hasUsefulFields(candidate) ? [candidate] : [];
  }

  function escapeRegExp(value) {
    return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function matchOne(text, regex) {
    const match = text.match(regex);
    return match ? cleanTail(match[1]) : "";
  }

  function extractCandidatesFromText(text, meta) {
    const candidates = [];
    const blocks = extractStatusBlocks(text, meta);
    for (const block of blocks) {
      const parsed = parseKeyValueBlock(block.body);
      const candidate = normalizeCandidateFields(parsed, {
        ...meta,
        kind: block.kind,
        raw_text: block.raw,
        confidence: "高",
      });
      if (hasUsefulFields(candidate)) candidates.push(candidate);
    }

    // 结构化块仍是最高可信来源。原记忆 / 合并记忆 / 记忆大纲允许低置信自然语言候选，
    // 但只作为后台扫描候选展示，用户确认后才会应用，避免普通记忆摘要直接覆盖当前状态。
    candidates.push(...extractMemoryProseCandidates(text, meta));
    return candidates.filter((candidate) => !isTemplateCandidate(candidate));
  }

  function scoreCandidate(candidate) {
    let score = Number(candidate.weight || 0);
    if (candidate.kind === "status_panel_update") score += 100;
    if (candidate.kind === "status_panel") score += 50;
    if (candidate.confidence === "高") score += 30;
    if (candidate.source_key === "history") score += Number(candidate.source_index || 0) / 100;
    return score;
  }

  function candidateMergeKey(item) {
    const baseId = compact(item.id || item.name || "");
    if (!baseId) return "";
    // 原记忆 / 合并记忆 / 记忆大纲的自然语言候选必须按来源单独保留。
    // 不能只按角色合并，否则同一个角色的多条记忆会被旧记忆吞掉。
    if (item.kind === "loose_memory") {
      const sourceKey = compact(item.source_key || "memory");
      const sourceId = compact(item.source_id || "") || String(item.source_index ?? "0");
      return `${sourceKey}:${sourceId}:${baseId}`;
    }
    return baseId;
  }

  function makeCandidateShell(item) {
    return {
      id: item.id || toSlug(item.name),
      name: item.name,
      aliases: Array.isArray(item.aliases) ? [...item.aliases] : [],
      group: item.group || "自动提取",
      visible: true,
      alive_status: "",
      hp_current: "",
      hp_max: "",
      mp_current: "",
      mp_max: "",
      location: "",
      relationship: "",
      status_effects: [],
      effects_add: [],
      effects_remove: [],
      short_summary: "",
      extra: {},
      kind: item.kind,
      source: item.source,
      source_key: item.source_key,
      source_id: item.source_id || "",
      source_index: item.source_index ?? 0,
      source_title: item.source_title || "",
      raw_text: item.raw_text || "",
      confidence: item.confidence,
      sources: [],
      matched_alias: item.matched_alias || "",
      matched_name: item.matched_name || "",
    };
  }

  function mergeCandidateInto(target, item) {
    if (!target.matched_alias && item.matched_alias) target.matched_alias = item.matched_alias;
    if (!target.matched_name && item.matched_name) target.matched_name = item.matched_name;
    if (!target.source_title && item.source_title) target.source_title = item.source_title;
    if (!target.source_id && item.source_id) target.source_id = item.source_id;
    if (!target.raw_text && item.raw_text) target.raw_text = item.raw_text;
    for (const field of ["name", "group", "alive_status", "hp_current", "hp_max", "mp_current", "mp_max", "location", "relationship", "short_summary"]) {
      if (!target[field] && item[field]) target[field] = item[field];
    }
    if (Array.isArray(item.aliases) && item.aliases.length) {
      const aliasSet = new Set(target.aliases || []);
      item.aliases.forEach((alias) => { if (alias) aliasSet.add(alias); });
      target.aliases = Array.from(aliasSet);
    }
    if (!target.status_effects.length && item.status_effects?.length) target.status_effects = item.status_effects;
    if (!target.effects_add.length && item.effects_add?.length) target.effects_add = item.effects_add;
    if (!target.effects_remove.length && item.effects_remove?.length) target.effects_remove = item.effects_remove;
    if (item.extra && Object.keys(item.extra).length) target.extra = { ...(target.extra || {}), ...item.extra };
    if (item.kind === "status_panel_update") target.kind = item.kind;
    if (item.confidence === "高") target.confidence = "高";
    target.sources.push({
      source: item.source,
      source_key: item.source_key,
      source_id: item.source_id || "",
      source_index: item.source_index ?? 0,
      source_title: item.source_title || "",
      kind: item.kind,
      raw_text: item.raw_text,
      score: scoreCandidate(item),
      matched_alias: item.matched_alias || "",
      matched_name: item.matched_name || "",
    });
  }

  function mergeCandidates(candidates) {
    const byKey = new Map();
    const sorted = [...candidates].sort((a, b) => scoreCandidate(b) - scoreCandidate(a));

    for (const item of sorted) {
      const key = candidateMergeKey(item);
      if (!key) continue;
      if (!byKey.has(key)) byKey.set(key, makeCandidateShell(item));
      mergeCandidateInto(byKey.get(key), item);
    }

    return Array.from(byKey.values()).sort((a, b) => {
      const aScore = Math.max(...a.sources.map((item) => item.score || 0));
      const bScore = Math.max(...b.sources.map((item) => item.score || 0));
      if (bScore !== aScore) return bScore - aScore;
      return Number(b.source_index || 0) - Number(a.source_index || 0);
    });
  }

  async function scanStatusPanelSources(options = {}) {
    const enabledSources = new Set(options.enabledSources || SOURCE_DEFS.map((item) => item.key));
    const existingCharacters = Array.isArray(options.characters) ? options.characters : [];
    const allCandidates = [];
    const sourceResults = [];

    for (const source of SOURCE_DEFS) {
      if (!enabledSources.has(source.key)) continue;
      try {
        const response = await fetch(source.url, { cache: "no-store" });
        if (!response.ok) {
          sourceResults.push({ key: source.key, label: source.label, ok: false, count: 0 });
          continue;
        }
        const data = await response.json();
        const textItems = source.pickTexts(data);
        let count = 0;
        for (const item of textItems) {
          const candidates = extractCandidatesFromText(item.text, {
            source: item.source || source.label,
            source_key: item.source_key || source.key,
            source_index: item.source_index || 0,
            source_id: item.source_id || "",
            source_title: item.source_title || "",
            weight: source.weight,
            existingCharacters,
          });
          count += candidates.length;
          allCandidates.push(...candidates);
        }
        sourceResults.push({ key: source.key, label: source.label, ok: true, count });
      } catch (error) {
        sourceResults.push({ key: source.key, label: source.label, ok: false, count: 0, error: String(error) });
      }
    }

    return {
      candidates: mergeCandidates(allCandidates),
      sourceResults,
      debug: {
        existingCharacters: existingCharacters.map((item) => ({
          id: item?.id || "",
          name: item?.name || "",
          aliases: normalizeAliases(item?.aliases || item?.alias || []),
        })),
      },
    };
  }

  window.XuqiStatusPanelExtractor = {
    scan: scanStatusPanelSources,
    extractStatusBlocks,
    parseKeyValueBlock,
    normalizeCandidateFields,
    SOURCE_DEFS,
  };
})();
