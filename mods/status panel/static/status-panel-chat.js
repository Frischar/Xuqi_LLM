(() => {
  const API_STATE = "/mods/status-panel/app/api/state";
  const API_HISTORY = "/api/history";
  const API_SCHEMA = "/mods/status-panel/app/api/field-schema";
  const API_APPLY_UPDATE = "/mods/status-panel/app/api/apply-update";
  const API_RESOLVE_PENDING = "/mods/status-panel/app/api/pending-updates/resolve";
  const PANEL_ID = "xuqi-status-panel-mod";
  const SCAN_ATTR = "data-xsp-status-scan";
  const OPEN_KEY = "xuqi.statusPanel.open";
  const POS_KEY = "xuqi.statusPanel.position";
  const UNREAD_MAX = 99;

  let lastState = null;
  let fieldSchema = {
    table_columns: [
      { key: "name", label: "角色名" },
      { key: "alive_status", label: "存活状态" },
      { key: "hp", label: "HP" },
      { key: "mp", label: "MP" },
      { key: "location", label: "地点" },
      { key: "status_effects", label: "身体状态" },
    ],
    detail_fields: [
      { key: "group", label: "分组" },
      { key: "relationship", label: "关系" },
      { key: "short_summary", label: "摘要" },
      { key: "updated_at", label: "更新时间" },
      { key: "extra.*", label: "扩展资料" },
    ],
  };
  let scanTimer = null;
  let applying = false;
  const seenUpdateIds = new Set();
  const debugLog = [];
  const naturalCandidates = [];
  let unreadCount = 0;
  let editingCandidateId = "";
  let editingCandidateStartedAt = 0;

  function pushDebug(type, title, detail = "", raw = "") {
    debugLog.unshift({
      type,
      title: String(title || ""),
      detail: String(detail || ""),
      raw: String(raw || ""),
      time: new Date().toLocaleTimeString(),
    });
    if (debugLog.length > 12) debugLog.length = 12;
  }

  function debugSummary() {
    const caught = debugLog.filter((item) => item.type === "caught").length;
    const applied = debugLog.filter((item) => item.type === "applied" || item.type === "partial" || item.type === "pending" || item.type === "noop").length;
    const guarded = debugLog.filter((item) => item.type === "guarded").length;
    const errors = debugLog.filter((item) => item.type === "error").length;
    return { caught, applied, guarded, errors };
  }

  function isPanelCurrentlyOpen() {
    return getStoredOpen();
  }

  function bumpUnread(count = 1) {
    if (isPanelCurrentlyOpen()) return;
    unreadCount = Math.min(UNREAD_MAX, unreadCount + Math.max(1, Number(count) || 1));
  }

  function clearUnread() {
    unreadCount = 0;
  }

  function unreadLabel() {
    if (!unreadCount) return "";
    return unreadCount > 9 ? "9+" : String(unreadCount);
  }

  function esc(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function compact(value) {
    return String(value || "").replace(/\r/g, "\n").trim();
  }

  function splitList(value) {
    if (Array.isArray(value)) return value.map((item) => compact(item)).filter(Boolean).filter((item) => !["无", "没有"].includes(item));
    return String(value || "")
      .replace(/[、/]/g, ",")
      .replace(/[，]/g, ",")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .filter((item) => !["无", "没有"].includes(item));
  }

  function displayValue(value, fallback = "未记录") {
    const text = compact(value);
    if (!text || ["?", "？", "?/ ?", "?/?", "？/？", "未知", "未提取"].includes(text)) return fallback;
    return text;
  }

  function hpValue(item) {
    if (!item.hp_current && !item.hp_max) return "未记录";
    const current = displayValue(item.hp_current, "?");
    const max = displayValue(item.hp_max, "?");
    if (current === "?" && max === "?") return "未记录";
    return `${current}/${max}`;
  }

  function mpValue(item) {
    if (!item.mp_current && !item.mp_max) return "未记录";
    const current = displayValue(item.mp_current, "?");
    const max = displayValue(item.mp_max, "?");
    if (current === "?" && max === "?") return "未记录";
    return `${current}/${max}`;
  }

  function hpBrief(item) {
    const hp = hpValue(item);
    return hp === "未记录" ? "" : ` ${hp}`;
  }

  function effectText(item) {
    const effects = splitList(item.status_effects);
    return effects.length ? effects.join("、") : "无异常";
  }

  function effectChips(item) {
    const effects = splitList(item.status_effects);
    if (!effects.length) return `<span class="xsp-effect-chip is-empty">无异常</span>`;
    return effects.map((effect) => `<span class="xsp-effect-chip">${esc(effect)}</span>`).join("");
  }

  function compactLine(characters) {
    return characters.slice(0, 2).map((item) => {
      const name = item.name || "未命名";
      return `${name}${hpBrief(item)}`;
    }).join(" · ");
  }

  function countAbnormal(characters) {
    return characters.filter((item) => splitList(item.status_effects).length > 0).length;
  }

  function modeText(mode) {
    if (mode === "all") return "全自动";
    if (mode === "off") return "手动确认";
    return "安全自动";
  }

  function sourceLabelForKind(kind) {
    if (kind === "natural_candidate") return "自然语言候选";
    if (kind === "status_panel_update") return "状态块";
    return kind || "状态更新";
  }

  const FIELD_LABELS = {
    location: "地点", relationship: "关系", short_summary: "摘要", last_event: "最近变化",
    alive_status: "生存状态", hp_current: "HP当前", hp_max: "HP上限",
    mp_current: "MP当前", mp_max: "MP上限", status_effects: "身体状态", extra: "扩展字段",
  };

  function aliasesOf(item) {
    return splitList(Array.isArray(item?.aliases) ? item.aliases.join(",") : item?.aliases || "");
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
    if (latin) return source.toLowerCase().includes(target.toLowerCase()) || normalizeMentionKey(source).includes(normalizeMentionKey(target));
    return source.includes(target) || normalizeMentionKey(source).includes(normalizeMentionKey(target));
  }

  function findCharacterMentionInText(text, characters) {
    const list = Array.isArray(characters) ? characters : [];
    const tokens = [];
    list.forEach((item) => {
      const add = (value, type) => {
        const token = compact(value);
        if (!token) return;
        if (token.length < 2 && !/[A-Za-z0-9]/.test(token)) return;
        tokens.push({ token, type, character: item });
      };
      add(item.name, "name");
      aliasesOf(item).forEach((alias) => add(alias, "alias"));
      const id = compact(item.id);
      if (id && !/^char-[a-f0-9]{6,}$/i.test(id)) add(id, "id");
    });
    tokens.sort((a, b) => b.token.length - a.token.length);
    for (const entry of tokens) {
      if (textContainsMention(text, entry.token)) return entry;
    }
    return null;
  }

  function findCurrentCharacter(update) {
    const list = Array.isArray(lastState?.characters) ? lastState.characters : [];
    const id = compact(update?.id);
    const name = compact(update?.name);
    return list.find((item) => id && compact(item.id) === id)
      || list.find((item) => name && normalizeMentionKey(compact(item.name)) === normalizeMentionKey(name))
      || list.find((item) => name && aliasesOf(item).some((alias) => normalizeMentionKey(alias) === normalizeMentionKey(name)))
      || null;
  }

  function readableUpdateDetail(update, result = null, beforeChar = null) {
    const lines = [];
    const label = sourceLabelForKind(update?.kind);
    if (label) lines.push(`来源：${label}`);
    if (result?.status) lines.push(`结果：${result.status}`);
    const applied = Array.isArray(result?.applied_fields) ? result.applied_fields : [];
    const pending = Array.isArray(result?.pending_fields) ? result.pending_fields : [];
    if (applied.length) lines.push(`已应用：${applied.map((key) => FIELD_LABELS[key] || key).join("、")}`);
    if (pending.length) lines.push(`待确认：${pending.map((key) => FIELD_LABELS[key] || key).join("、")}`);
    if (result?.reason) lines.push(`说明：${result.reason}`);
    const before = beforeChar || findCurrentCharacter(update) || {};
    function addChange(fieldLabel, oldValue, newValue) {
      const next = displayValue(newValue, "");
      if (!next) return;
      const prev = displayValue(oldValue, "未记录");
      lines.push(prev === next ? `${fieldLabel}：${next}` : `${fieldLabel}：${prev} → ${next}`);
    }
    addChange("地点", before.location, update.location);
    addChange("关系", before.relationship, update.relationship);
    addChange("生存状态", before.alive_status, update.alive_status);
    if (update.hp_current || update.hp_max) addChange("HP", hpValue(before), `${update.hp_current || "?"}/${update.hp_max || "?"}`);
    if (update.mp_current || update.mp_max) addChange("MP", mpValue(before), `${update.mp_current || "?"}/${update.mp_max || "?"}`);
    const add = splitList(update.effects_add).join("、");
    const remove = splitList(update.effects_remove).join("、");
    if (add) lines.push(`新增状态：${add}`);
    if (remove) lines.push(`移除状态：${remove}`);
    if (update.effects_clear) lines.push("身体状态：清空 / 无异常");
    if (update.status_effects && splitList(update.status_effects).length) lines.push(`身体状态覆盖：${splitList(update.status_effects).join("、")}`);
    if (update.extra && typeof update.extra === "object") {
      Object.entries(update.extra).forEach(([key, value]) => {
        if (compact(value)) addChange(`扩展.${key}`, before?.extra ? extraValue(before, key) : "", value);
      });
    }
    if (update.last_event || update.summary || update.short_summary) lines.push(`说明：${update.last_event || update.summary || update.short_summary}`);
    return lines.filter(Boolean).join("\n");
  }
  function safeId(item, index) {
    return esc(item.id || item.name || `xsp-char-${index}`);
  }

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

  function extraValue(item, key) {
    const extra = item.extra || item.extras || item.custom || {};
    if (!extra || typeof extra !== "object") return "";
    const wanted = normalizeExtraKey(key);
    if (Object.prototype.hasOwnProperty.call(extra, key)) return compact(extra[key]);
    if (Object.prototype.hasOwnProperty.call(extra, wanted)) return compact(extra[wanted]);
    for (const [extraKey, value] of Object.entries(extra)) {
      if (normalizeExtraKey(extraKey) === wanted) return compact(value);
    }
    return "";
  }

  function valueForKey(item, key) {
    if (key === "hp") return hpValue(item);
    if (key === "mp") return mpValue(item);
    if (key === "status_effects" || key === "effects") return effectText(item);
    if (key && key.startsWith("extra.")) return displayValue(extraValue(item, key.slice(6)), "未记录");
    return displayValue(item[key], "未记录");
  }

  function isExtraColumnKey(key) {
    return key && key.startsWith("extra.");
  }

  function detailBlock(item) {
    const details = [];
    const hideTableExtrasInDetail = lastState?.settings?.hide_table_extras_in_detail === true;
    const shownExtra = hideTableExtrasInDetail
      ? new Set((fieldSchema.table_columns || [])
        .filter((col) => isExtraColumnKey(col.key))
        .map((col) => normalizeExtraKey(col.key.slice(6))))
      : new Set();

    for (const field of fieldSchema.detail_fields || []) {
      const key = field.key;
      const label = field.label || key;
      if (key === "extra.*") {
        const extra = item.extra || item.extras || item.custom || {};
        if (extra && typeof extra === "object" && !Array.isArray(extra)) {
          Object.entries(extra).forEach(([extraKey, value]) => {
            if (!shownExtra.has(normalizeExtraKey(extraKey)) && compact(value)) details.push([extraKey, value]);
          });
        }
        continue;
      }
      const value = valueForKey(item, key);
      if (value && value !== "未记录") details.push([label, value]);
    }

    if (!details.length) return `<span class="xsp-muted">暂无更多资料。</span>`;
    return details.map(([key, value]) => `
      <div class="xsp-detail-item">
        <span>${esc(key)}</span>
        <strong>${esc(value)}</strong>
      </div>
    `).join("");
  }

  function characterRows(item, index, columns) {
    const id = safeId(item, index);
    const cells = columns.map((column, colIndex) => {
      const key = column.key;
      const value = valueForKey(item, key);
      if (colIndex === 0 || key === "name") {
        return `<td class="xsp-col-name"><button type="button" class="xsp-row-name">${esc(value || item.name || "未命名角色")}</button></td>`;
      }
      if (key === "status_effects" || key === "effects") {
        return `<td class="xsp-effect-cell">${effectChips(item)}</td>`;
      }
      return `<td title="${esc(value)}">${esc(value)}</td>`;
    }).join("");
    return `
      <tr class="xsp-status-row" data-xsp-detail-target="${id}" title="点击查看详情">
        ${cells}
      </tr>
      <tr class="xsp-detail-row" data-xsp-detail-row="${id}">
        <td colspan="${columns.length}">
          <div class="xsp-detail-grid">${detailBlock(item)}</div>
        </td>
      </tr>
    `;
  }

  function pendingRow(item) {
    const update = item.update || {};
    const add = splitList(update.effects_add).join("、");
    const remove = splitList(update.effects_remove).join("、");
    const bits = [
      update.location ? `位置：${update.location}` : "",
      update.alive_status ? `生存：${update.alive_status}` : "",
      update.hp_current || update.hp_max ? `HP：${update.hp_current || "?"}/${update.hp_max || "?"}` : "",
      update.mp_current || update.mp_max ? `MP：${update.mp_current || "?"}/${update.mp_max || "?"}` : "",
      add ? `新增：${add}` : "",
      remove ? `移除：${remove}` : "",
    ].filter(Boolean);
    return `
      <div class="xsp-pending-row" data-update-id="${esc(item.update_id)}">
        <div>
          <strong>${esc(update.name || "未命名角色")}</strong>
          <span>${esc(bits.join(" · ") || update.short_summary || "待确认更新")}</span>
        </div>
        <div class="xsp-pending-actions">
          <button type="button" data-xsp-pending-action="apply">应用</button>
          <button type="button" data-xsp-pending-action="ignore">忽略</button>
        </div>
      </div>
    `;
  }



  function candidateSummary(candidate) {
    const update = candidate.update || {};
    const bits = [];
    if (update.location) bits.push(`地点：${update.location}`);
    if (update.alive_status) bits.push(`生存：${update.alive_status}`);
    if (update.hp_current || update.hp_max) bits.push(`HP：${update.hp_current || "?"}/${update.hp_max || "?"}`);
    if (update.mp_current || update.mp_max) bits.push(`MP：${update.mp_current || "?"}/${update.mp_max || "?"}`);
    const add = splitList(update.effects_add).join("、");
    const remove = splitList(update.effects_remove).join("、");
    if (add) bits.push(`新增：${add}`);
    if (remove) bits.push(`移除：${remove}`);
    if (update.effects_clear) bits.push("清空身体状态");
    const extra = update.extra && typeof update.extra === "object" ? Object.entries(update.extra) : [];
    extra.forEach(([key, value]) => {
      if (compact(value)) bits.push(`${key}：${value}`);
    });
    if (update.short_summary && !bits.length) bits.push(update.short_summary);
    return bits.join(" · ") || "可能状态变化";
  }

  function markCandidateEditing(candidateId) {
    editingCandidateId = String(candidateId || "");
    editingCandidateStartedAt = Date.now();
    naturalCandidates.forEach((candidate) => {
      candidate.editing = !!editingCandidateId && candidate.id === editingCandidateId;
    });
  }

  function clearCandidateEditing(candidateId = "") {
    if (!candidateId || String(candidateId) === editingCandidateId) {
      editingCandidateId = "";
      editingCandidateStartedAt = 0;
    }
    naturalCandidates.forEach((candidate) => {
      if (!candidateId || candidate.id === candidateId) candidate.editing = false;
    });
  }

  function safeRenderPanel(data, options = {}) {
    if (!data) return;
    if (!options.force && hasEditingCandidate()) return;
    renderPanel(data);
  }

  function candidateEditForm(candidate) {
    const update = candidate.update || {};
    const extra = update.extra && typeof update.extra === "object" ? update.extra : {};
    const extraRows = Object.entries(extra).map(([key, value]) => `
      <label class="xsp-candidate-edit-field">
        <span>扩展.${esc(key)}</span>
        <input data-xsp-candidate-extra="${esc(key)}" value="${esc(value)}" />
      </label>
    `).join("");
    return `
      <div class="xsp-candidate-edit-box">
        <label class="xsp-candidate-edit-field">
          <span>地点</span>
          <input data-xsp-candidate-field="location" value="${esc(update.location || "")}" placeholder="例如：走廊 / 资料室" />
        </label>
        <label class="xsp-candidate-edit-field">
          <span>新增状态</span>
          <input data-xsp-candidate-field="effects_add" value="${esc(splitList(update.effects_add).join("、"))}" placeholder="例如：轻微紧张" />
        </label>
        <label class="xsp-candidate-edit-field">
          <span>移除状态</span>
          <input data-xsp-candidate-field="effects_remove" value="${esc(splitList(update.effects_remove).join("、"))}" placeholder="例如：紧张" />
        </label>
        <label class="xsp-candidate-edit-field">
          <span>最近变化</span>
          <textarea data-xsp-candidate-field="last_event" rows="2" placeholder="一句话说明这次变化">${esc(update.last_event || update.summary || "")}</textarea>
        </label>
        ${extraRows}
      </div>
    `;
  }

  function saveCandidateEdits(candidateId, rowEl) {
    const candidate = naturalCandidates.find((item) => item.id === candidateId);
    if (!candidate || !rowEl) return false;
    const update = candidate.update || {};
    rowEl.querySelectorAll("[data-xsp-candidate-field]").forEach((input) => {
      const key = input.dataset.xspCandidateField;
      const value = compact(input.value || "");
      if (key === "effects_add" || key === "effects_remove") {
        update[key] = splitList(value);
      } else if (key === "last_event") {
        update.last_event = value;
        update.summary = value;
      } else {
        update[key] = value;
      }
    });
    rowEl.querySelectorAll("[data-xsp-candidate-extra]").forEach((input) => {
      const key = normalizeExtraKey(input.dataset.xspCandidateExtra || "");
      if (!key) return;
      update.extra = update.extra && typeof update.extra === "object" ? update.extra : {};
      const value = compact(input.value || "");
      if (value) update.extra[key] = value;
      else delete update.extra[key];
    });
    candidate.update = update;
    candidate.reason = candidate.reason || "已由用户手动编辑候选字段";
    return true;
  }
  function candidateRow(candidate) {
    const reason = candidate.reason ? `<span class="xsp-candidate-reason">理由：${esc(candidate.reason)}</span>` : "";
    const confidence = candidate.confidence ? `<span class="xsp-candidate-confidence">${esc(candidate.confidence)}</span>` : "";
    const sourceLabel = `<span class="xsp-candidate-source">来源：${esc(sourceLabelForKind(candidate.update?.kind || "natural_candidate"))}</span>`;
    const editing = candidate.editing === true;
    const editBox = editing ? candidateEditForm(candidate) : "";
    const actions = editing ? `
          <button type="button" data-xsp-candidate-action="save">保存</button>
          <button type="button" data-xsp-candidate-action="apply">应用</button>
          <button type="button" data-xsp-candidate-action="cancel">取消</button>
        ` : `
          <button type="button" data-xsp-candidate-action="edit">编辑</button>
          <button type="button" data-xsp-candidate-action="apply">应用</button>
          <button type="button" data-xsp-candidate-action="ignore">忽略</button>
        `;
    return `
      <div class="xsp-candidate-row ${editing ? "is-editing" : ""}" data-candidate-id="${esc(candidate.id)}">
        <div class="xsp-candidate-main">
          <div class="xsp-candidate-head">
            <strong>${esc(candidate.update?.name || "未命名角色")}</strong>
            ${confidence}
          </div>
          <span>${esc(candidateSummary(candidate))}</span>
          ${sourceLabel}
          ${reason}
          ${editBox}
        </div>
        <div class="xsp-candidate-actions">
          ${actions}
        </div>
      </div>
    `;
  }
  function renderCandidateBox() {
    if (!naturalCandidates.length) return "";
    return `
      <div class="xsp-candidate-box">
        <div class="xsp-candidate-title">可能状态变化 <span>${naturalCandidates.length} 条</span></div>
        ${naturalCandidates.map(candidateRow).join("")}
      </div>
    `;
  }

  function getStoredOpen() {
    try {
      return localStorage.getItem(OPEN_KEY) === "true";
    } catch {
      return false;
    }
  }

  function setStoredOpen(value) {
    try {
      localStorage.setItem(OPEN_KEY, value ? "true" : "false");
    } catch {
      // ignore
    }
  }

  function getStoredPosition() {
    try {
      const raw = JSON.parse(localStorage.getItem(POS_KEY) || "null");
      if (!raw || typeof raw !== "object") return null;
      const left = Number(raw.left);
      const top = Number(raw.top);
      if (!Number.isFinite(left) || !Number.isFinite(top)) return null;
      return { left, top };
    } catch {
      return null;
    }
  }

  function setStoredPosition(position) {
    try {
      localStorage.setItem(POS_KEY, JSON.stringify(position));
    } catch {
      // ignore
    }
  }

  function clampPosition(left, top, panel) {
    const margin = 8;
    const rect = panel.getBoundingClientRect();
    const width = rect.width || 260;
    const height = rect.height || 48;
    return {
      left: Math.max(margin, Math.min(left, window.innerWidth - width - margin)),
      top: Math.max(margin, Math.min(top, window.innerHeight - height - margin)),
    };
  }

  function applyStoredPosition(panel) {
    const pos = getStoredPosition();
    if (!pos) return;
    const clamped = clampPosition(pos.left, pos.top, panel);
    panel.style.left = `${clamped.left}px`;
    panel.style.top = `${clamped.top}px`;
    panel.style.right = "auto";
    panel.style.bottom = "auto";
    panel.style.transform = "none";
  }

  function attachDrag(panel, handle) {
    let startX = 0;
    let startY = 0;
    let startLeft = 0;
    let startTop = 0;
    let dragging = false;
    let pointerId = null;

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      pointerId = event.pointerId;
      const rect = panel.getBoundingClientRect();
      startX = event.clientX;
      startY = event.clientY;
      startLeft = rect.left;
      startTop = rect.top;
      dragging = false;
      handle.setPointerCapture?.(event.pointerId);
    });

    handle.addEventListener("pointermove", (event) => {
      if (pointerId !== event.pointerId) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (!dragging && Math.hypot(dx, dy) < 5) return;
      dragging = true;
      panel.classList.add("is-dragging");
      const next = clampPosition(startLeft + dx, startTop + dy, panel);
      panel.style.left = `${next.left}px`;
      panel.style.top = `${next.top}px`;
      panel.style.right = "auto";
      panel.style.bottom = "auto";
      panel.style.transform = "none";
      event.preventDefault();
    });

    function finish(event) {
      if (pointerId !== event.pointerId) return;
      handle.releasePointerCapture?.(event.pointerId);
      pointerId = null;
      panel.classList.remove("is-dragging");
      if (dragging) {
        const rect = panel.getBoundingClientRect();
        setStoredPosition({ left: rect.left, top: rect.top });
        panel.dataset.justDragged = "true";
        window.setTimeout(() => {
          delete panel.dataset.justDragged;
        }, 180);
      }
      dragging = false;
    }

    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  }

  function renderPanel(data) {
    const settings = data.settings || {};
    const characters = Array.isArray(data.characters) ? data.characters : [];
    const pendingUpdates = Array.isArray(data.pending_updates) ? data.pending_updates : [];
    const oldPanel = document.getElementById(PANEL_ID);
    if (oldPanel) oldPanel.remove();

    if (settings.enabled === false || settings.chat_panel_enabled === false) return;

    const maxVisible = Math.max(1, Math.min(50, Number(settings.max_visible || 8)));
    const visibleCharacters = characters.filter((item) => item.visible !== false).slice(0, maxVisible);
    // v1.7.4-persist：即使当前没有角色，也保留聊天页状态栏入口。
    // 这样重启后如果状态还未初始化，用户也能看到“暂无角色状态”并进入后台扫描/新增。

    const isOpen = getStoredOpen();
    if (isOpen && unreadCount) clearUnread();
    const abnormalCount = countAbnormal(visibleCharacters);
    const panel = document.createElement("section");
    panel.id = PANEL_ID;
    panel.className = `xsp-chat-panel xsp-floating-widget ${settings.compact === false ? "" : "is-compact"} ${isOpen ? "is-open" : ""}`;
    const pendingBadge = pendingUpdates.length ? `<span class="xsp-chat-pending-badge">${pendingUpdates.length} 待确认</span>` : "";
    const abnormalBadge = abnormalCount ? `<span class="xsp-chat-mini-badge">${abnormalCount} 状态</span>` : "";
    const brief = visibleCharacters.length ? compactLine(visibleCharacters) : "暂无角色";
    const unread = unreadLabel();
    const unreadBadge = unread ? `<span class="xsp-floating-badge" aria-label="${unread} 条新状态提醒">${unread}</span>` : "";
    const toggleContent = isOpen ? `
        <span class="xsp-drag-dot" aria-hidden="true">⋮⋮</span>
        <span class="xsp-chat-title">${esc(settings.title || "角色状态")}</span>
        <span class="xsp-chat-brief">${esc(brief)}</span>
        ${abnormalBadge}
        ${pendingBadge}
        <span class="xsp-chat-count">${visibleCharacters.length} 人</span>
        <span class="xsp-chat-caret" aria-hidden="true">收起</span>
      ` : `
        <span class="xsp-ball-glyph" aria-hidden="true">状</span>
        ${unreadBadge}
        <span class="xsp-ball-sr">${esc(settings.title || "角色状态")}</span>
      `;
    const columns = Array.isArray(fieldSchema.table_columns) && fieldSchema.table_columns.length ? fieldSchema.table_columns : [
      { key: "name", label: "角色名" },
      { key: "alive_status", label: "存活状态" },
      { key: "hp", label: "HP" },
      { key: "mp", label: "MP" },
      { key: "location", label: "地点" },
      { key: "status_effects", label: "身体状态" },
    ];

    panel.innerHTML = `
      <button class="xsp-chat-toggle ${isOpen ? "is-panel-toggle" : "is-ball-toggle"}" type="button" aria-expanded="${isOpen ? "true" : "false"}" title="点击展开 / 收起，按住可拖动位置">
        ${toggleContent}
      </button>
      <div class="xsp-chat-body">
        <div class="xsp-chat-mode-line">聊天状态块：${settings.hide_update_blocks === false ? "原样显示" : "纯隐藏"} · 自动更新：${esc(modeText(settings.auto_apply_mode || "safe"))}</div>
        ${settings.show_update_debug_blocks === true ? renderDebugBox() : ""}
        ${renderCandidateBox()}
        ${pendingUpdates.length && settings.show_pending_in_chat !== false ? `
          <div class="xsp-pending-box">
            <div class="xsp-pending-title">待确认状态更新</div>
            ${pendingUpdates.map(pendingRow).join("")}
          </div>
        ` : ""}
        ${visibleCharacters.length ? `
          <div class="xsp-table-wrap" role="region" aria-label="角色状态表">
            <table class="xsp-status-table">
              <thead>
                <tr>
                  ${columns.map((column) => `<th>${esc(column.label || column.key)}</th>`).join("")}
                </tr>
              </thead>
              <tbody>
                ${visibleCharacters.map((item, index) => characterRows(item, index, columns)).join("")}
              </tbody>
            </table>
          </div>
        ` : `<div class="xsp-empty-mini">暂无可显示角色。</div>`}
        <div class="xsp-chat-footer">
          <span>点击角色行可展开完整资料。</span>
          <a href="/mods/status-panel" target="_blank" rel="noopener noreferrer">管理 / 扫描状态</a>
        </div>
      </div>
    `;

    const toggle = panel.querySelector(".xsp-chat-toggle");
    toggle.addEventListener("click", () => {
      if (panel.dataset.justDragged === "true") return;
      const open = !panel.classList.contains("is-open");
      setStoredOpen(open);
      if (open) clearUnread();
      if (lastState) safeRenderPanel(lastState, { force: true });
      else window.setTimeout(() => applyStoredPosition(panel), 0);
    });

    panel.querySelectorAll(".xsp-status-row").forEach((rowEl) => {
      rowEl.addEventListener("click", () => {
        const target = rowEl.dataset.xspDetailTarget;
        if (!target) return;
        const detail = panel.querySelector(`[data-xsp-detail-row="${CSS.escape(target)}"]`);
        rowEl.classList.toggle("is-expanded");
        detail?.classList.toggle("is-open");
      });
    });

    panel.querySelectorAll("[data-xsp-pending-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const rowEl = button.closest(".xsp-pending-row");
        const updateId = rowEl?.dataset?.updateId;
        if (!updateId) return;
        button.disabled = true;
        await resolvePending(updateId, button.dataset.xspPendingAction);
      });
    });

    panel.querySelectorAll(".xsp-candidate-row input, .xsp-candidate-row textarea").forEach((input) => {
      input.addEventListener("click", (event) => event.stopPropagation());
      input.addEventListener("pointerdown", (event) => event.stopPropagation());
      input.addEventListener("keydown", (event) => event.stopPropagation());
      input.addEventListener("focus", () => {
        const rowEl = input.closest(".xsp-candidate-row");
        const candidateId = rowEl?.dataset?.candidateId;
        if (candidateId) markCandidateEditing(candidateId);
      });
      input.addEventListener("input", () => {
        editingCandidateStartedAt = Date.now();
        const rowEl = input.closest(".xsp-candidate-row");
        const candidateId = rowEl?.dataset?.candidateId;
        if (candidateId) saveCandidateEdits(candidateId, rowEl);
      });
    });

    panel.querySelectorAll("[data-xsp-candidate-action]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const rowEl = button.closest(".xsp-candidate-row");
        const candidateId = rowEl?.dataset?.candidateId;
        if (!candidateId) return;
        const action = button.dataset.xspCandidateAction;
        if (!["edit", "save", "cancel"].includes(action)) button.disabled = true;
        if (action === "edit") {
          markCandidateEditing(candidateId);
          safeRenderPanel(lastState, { force: true });
        } else if (action === "save") {
          saveCandidateEdits(candidateId, rowEl);
          clearCandidateEditing(candidateId);
          safeRenderPanel(lastState, { force: true });
        } else if (action === "cancel") {
          clearCandidateEditing(candidateId);
          safeRenderPanel(lastState, { force: true });
        } else if (action === "apply") {
          if (rowEl.classList.contains("is-editing")) saveCandidateEdits(candidateId, rowEl);
          clearCandidateEditing(candidateId);
          await applyNaturalCandidate(candidateId);
        } else {
          clearCandidateEditing(candidateId);
          ignoreNaturalCandidate(candidateId);
        }
      });
    });

    document.body.appendChild(panel);
    applyStoredPosition(panel);
    attachDrag(panel, toggle);
  }

  async function loadFieldSchema() {
    try {
      const response = await fetch(API_SCHEMA, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      if (data.schema) fieldSchema = data.schema;
    } catch {
      // 使用内置默认表头。
    }
  }

  function hasEditingCandidate() {
    return Boolean(editingCandidateId) || naturalCandidates.some((candidate) => candidate && candidate.editing === true);
  }

  async function loadPanel() {
    try {
      const response = await fetch(API_STATE, { cache: "no-store" });
      if (!response.ok) return null;
      const data = await response.json();
      lastState = data;
      safeRenderPanel(data);
      return data;
    } catch {
      return null;
    }
  }

  function parseStatusBlockBody(body) {
    const raw = {};
    body.split(/\n+/).forEach((line) => {
      const match = line.match(/^([^:：]+)[:：]\s*(.*)$/);
      if (!match) return;
      raw[match[1].trim()] = match[2].trim();
    });
    return raw;
  }

  const FIELD_MAP = {
    type: "type", 类型: "type",
    id: "id",
    name: "name", 姓名: "name", 角色名: "name",
    group: "group", 分组: "group",
    alive_status: "alive_status", 生存状态: "alive_status",
    hp: "hp", HP: "hp", 血量: "hp", 生命: "hp",
    mp: "mp", MP: "mp", 魔力: "mp", 灵力: "mp", 法力: "mp",
    location: "location", 位置: "location", 地点: "location",
    relationship: "relationship", 关系: "relationship",
    effects: "effects", status_effects: "effects", 状态: "effects", 异常状态: "effects",
    effects_add: "effects_add", 新增状态: "effects_add",
    effects_remove: "effects_remove", 移除状态: "effects_remove",
    effects_clear: "effects_clear", clear_effects: "effects_clear", 清空状态: "effects_clear", 清除状态: "effects_clear", 状态清空: "effects_clear",
    summary: "summary", short_summary: "summary", 摘要: "summary", 说明: "summary",
  };

  function normalizeBlock(raw, kind, rawText, source) {
    const result = { kind, raw_text: rawText, source, extra: {} };
    Object.entries(raw).forEach(([key, value]) => {
      const rawKey = key.trim();
      const extraMatch = rawKey.replace(/\s+/g, "").match(/^(?:extra|extras|custom|扩展|自定义)[.．。:：](.+)$/i);
      if (extraMatch) {
        const extraKey = normalizeExtraKey(extraMatch[1]);
        if (extraKey && compact(value)) result.extra[extraKey] = compact(value);
        return;
      }
      const mapped = FIELD_MAP[rawKey] || FIELD_MAP[rawKey.toLowerCase?.()] || rawKey;
      result[mapped] = compact(value);
    });
    if (!Object.keys(result.extra).length) delete result.extra;
    if (result.hp) {
      const parts = result.hp.split("/");
      result.hp_current = compact(parts[0]);
      result.hp_max = compact(parts[1]);
    }
    if (result.mp) {
      const parts = result.mp.split("/");
      result.mp_current = compact(parts[0]);
      result.mp_max = compact(parts[1]);
    }
    if (result.effects) result.status_effects = splitList(result.effects);
    if (result.effects_add) result.effects_add = splitList(result.effects_add);
    if (result.effects_remove) result.effects_remove = splitList(result.effects_remove);
    if (result.effects_clear) result.effects_clear = /^(true|1|yes|y|是|清空|清除|全部清空)$/i.test(compact(result.effects_clear));
    if (result.summary) result.last_event = result.summary;
    result.update_id = result.update_id || makeHash([result.name, result.id, result.raw_text].join("\n"));
    return result;
  }

  function makeHash(text) {
    // 简单稳定 hash，避免依赖 async crypto.subtle。
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < text.length; i += 1) {
      const ch = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    const value = 4294967296 * (2097151 & h2) + (h1 >>> 0);
    return `xsp-${value.toString(16)}`;
  }

  function isStatusUpdateMarkerLine(line) {
    return /^status_panel_update\s*$/i.test(compact(line));
  }

  function splitUpdateBody(body, rawPrefix = "") {
    const lines = String(body || "").replace(/\r/g, "\n").split(/\n/);
    const segments = [];
    let current = [];

    for (const line of lines) {
      if (isStatusUpdateMarkerLine(line)) {
        if (current.join("\n").trim()) {
          segments.push(current.join("\n").trim());
        }
        current = [];
        continue;
      }
      current.push(line);
    }

    if (current.join("\n").trim()) segments.push(current.join("\n").trim());

    return segments.map((bodyText) => ({
      body: bodyText,
      raw: rawPrefix || `status_panel_update\n${bodyText}`,
    }));
  }

  function extractFencedUpdateBlocks(text) {
    const blocks = [];
    const regex = /```\s*(status_panel_update)\s*\n([\s\S]*?)```/gi;
    let match;
    while ((match = regex.exec(String(text || ""))) !== null) {
      const rawText = match[0];
      const segments = splitUpdateBody(match[2], rawText);
      segments.forEach((segment) => blocks.push(segment));
    }
    return blocks;
  }

  function extractNakedUpdateBlocks(text) {
    const blocks = [];
    const lines = String(text || "").replace(/\r/g, "\n").split(/\n/);
    let collecting = false;
    let current = [];

    function flush() {
      const body = current.join("\n").trim();
      if (body) blocks.push({ body, raw: `status_panel_update\n${body}` });
      current = [];
    }

    for (const line of lines) {
      if (isStatusUpdateMarkerLine(line)) {
        if (collecting) flush();
        collecting = true;
        continue;
      }

      if (!collecting) continue;

      if (!line.trim()) {
        current.push(line);
        continue;
      }

      if (!/^([^:：]+)[:：]\s*([\s\S]*)$/.test(line)) {
        flush();
        collecting = false;
        continue;
      }
      current.push(line);
    }
    if (collecting) flush();
    return blocks;
  }

  function extractUpdateBlocks(text, source) {
    const blocks = [];
    const fencedBlocks = extractFencedUpdateBlocks(text);
    const nakedText = String(text || "").replace(/```\s*status_panel_update\s*\n[\s\S]*?```/gi, "");
    const rawBlocks = [...fencedBlocks, ...extractNakedUpdateBlocks(nakedText)];
    rawBlocks.forEach((block) => {
      const raw = parseStatusBlockBody(block.body);
      const candidate = normalizeBlock(raw, "status_panel_update", block.raw, source);
      if (candidate.name && hasUsefulUpdate(candidate)) blocks.push(candidate);
    });
    return blocks;
  }

  function hasUsefulUpdate(candidate) {
    return Boolean(
      candidate.location || candidate.relationship || candidate.alive_status ||
      candidate.hp_current || candidate.hp_max || candidate.mp_current || candidate.mp_max ||
      splitList(candidate.status_effects).length || splitList(candidate.effects_add).length ||
      splitList(candidate.effects_remove).length || candidate.effects_clear || candidate.short_summary || (candidate.extra && Object.keys(candidate.extra).length)
    );
  }

  function removeStatusBlocksFromText(text) {
    let cleaned = String(text || "")
      .replace(/```\s*status_panel_update\s*\n[\s\S]*?```/gi, "");

    // 兼容模型漏写围栏时的裸露 status_panel_update 段。
    const lines = cleaned.replace(/\r/g, "\n").split(/\n/);
    const kept = [];
    let skipping = false;
    for (const line of lines) {
      if (isStatusUpdateMarkerLine(line)) {
        skipping = true;
        continue;
      }
      if (skipping) {
        if (!line.trim()) continue;
        if (/^([^:：]+)[:：]\s*([\s\S]*)$/.test(line)) continue;
        skipping = false;
      }
      kept.push(line);
    }

    return kept.join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function getBubbleBody(bubble) {
    return bubble.querySelector(".bubble-body") || bubble;
  }

  function sourceForBubble(bubble, index) {
    const message = bubble.closest(".message");
    const role = message?.classList?.contains("assistant") ? "assistant" : "chat";
    const meta = message?.querySelector(".message-meta")?.textContent?.trim() || "";
    return `聊天:${role}:${meta}:${index}`;
  }

  function hasStatusUpdateText(text) {
    return /(?:```\s*status_panel_update|^|\n)\s*status_panel_update\s*(?:\n|$)/i.test(String(text || ""));
  }

  function getScannableText(container) {
    if (!container) return "";
    const clone = container.cloneNode(true);
    clone.querySelectorAll?.(".xsp-update-debug-block").forEach((node) => node.remove());
    return clone.textContent || "";
  }

  function renderDebugBox() {
    const summary = debugSummary();
    const rows = debugLog.length ? debugLog.map((item) => `
      <details class="xsp-panel-debug-item ${esc(item.type)}">
        <summary><span>${esc(item.time)}</span><strong>${esc(item.title)}</strong></summary>
        ${item.detail ? `<p>${esc(item.detail)}</p>` : ""}
        ${item.raw ? `<pre>${esc(item.raw)}</pre>` : ""}
      </details>
    `).join("") : `<p class="xsp-muted">还没有捕获到状态块。</p>`;

    return `
      <div class="xsp-panel-debug-box">
        <div class="xsp-panel-debug-head">
          <strong>状态块调试</strong>
          <span>捕获 ${summary.caught} · 应用 ${summary.applied} · 拦截 ${summary.guarded} · 错误 ${summary.errors}</span>
        </div>
        <div class="xsp-panel-debug-list">${rows}</div>
      </div>
    `;
  }

  function shouldConcealStatusBlocks() {
    const settings = lastState?.settings || {};
    return settings.hide_update_blocks !== false;
  }

  function cleanTextContainer(container, source) {
    const text = getScannableText(container);
    if (!hasStatusUpdateText(text)) return [];

    const updates = extractUpdateBlocks(text, source)
      .filter((update) => update.update_id && !seenUpdateIds.has(update.update_id));

    updates.forEach((update) => {
      seenUpdateIds.add(update.update_id);
      pushDebug("caught", `捕获 ${update.name || update.id || "未命名角色"}`, update.source || source, update.raw_text || "");
    });

    if (shouldConcealStatusBlocks()) {
      const cleaned = removeStatusBlocksFromText(text);
      if (cleaned !== text) {
        container.textContent = cleaned;
      }
    }

    return updates;
  }

  function getBubbleBody(bubble) {
    return bubble.querySelector?.(".bubble-body") || bubble;
  }

  function sourceForBubble(bubble, index) {
    const message = bubble.closest?.(".message") || bubble;
    const role = message?.classList?.contains("assistant") ? "assistant" : "chat";
    const meta = message?.querySelector?.(".message-meta")?.textContent?.trim() || "";
    return `聊天:${role}:${meta}:${index}`;
  }

  function isIgnoredStatusNode(node) {
    if (!node || node.nodeType !== 1) return true;
    if (node.closest?.(`#${PANEL_ID}`)) return true;
    if (node.closest?.("textarea, input, select, option, script, style, nav, .topbar, .topnav, .xsp-admin-page")) return true;
    return false;
  }

  function messageContainers() {
    const seen = new Set();
    const nodes = [];
    const selectors = [
      "#messages .message.assistant .bubble",
      "#messages .message.system .bubble",
      "#messages .bubble",
      "#messages .message.assistant",
      "#messages .message.system",
      ".message.assistant .bubble",
      ".message.system .bubble",
      ".message.assistant",
      ".message.system",
      ".assistant-message",
      ".bot-message",
      ".ai-message",
      "[data-role='assistant']",
      "[data-message-role='assistant']",
      ".bubble",
    ];

    function addNode(node) {
      if (!node || seen.has(node) || isIgnoredStatusNode(node)) return;
      if (node.closest?.(".message.user, .user-message, [data-role='user'], [data-message-role='user']")) return;
      seen.add(node);
      nodes.push(node);
    }

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach(addNode);
    });

    // 兜底：有些主题会把消息渲染成普通 div/pre/code，不带 bubble/message 类。
    document.querySelectorAll("main div, main article, main section, main pre, main code, body div, body article, body section, body pre, body code").forEach((node) => {
      if (isIgnoredStatusNode(node) || seen.has(node)) return;
      const text = node.textContent || "";
      if (!hasStatusUpdateText(text)) return;
      if (text.length > 50000) return;
      const childHasStatus = Array.from(node.children || []).some((child) => hasStatusUpdateText(child.textContent || ""));
      const className = String(node.className || "");
      const looksLikeMessage = /message|bubble|chat|markdown|content|assistant|bot|ai|response/i.test(className);
      if (!childHasStatus || looksLikeMessage) addNode(node);
    });

    return nodes;
  }

  function cleanBubble(bubble) {
    const index = messageContainers().indexOf(bubble);
    const containers = Array.from(bubble.querySelectorAll?.(".bubble-body, .bubble-think-content") || []);
    if (!containers.length) containers.push(getBubbleBody(bubble));

    const updates = [];
    containers.forEach((container, sectionIndex) => {
      updates.push(...cleanTextContainer(container, `${sourceForBubble(bubble, index)}:${sectionIndex}`));
    });

    if (!updates.length && hasStatusUpdateText(bubble.textContent || "")) {
      updates.push(...cleanTextContainer(getBubbleBody(bubble), sourceForBubble(bubble, index)));
    }

    if (updates.length) {
      if (shouldBlockBecauseNoChange(bubble)) {
        updates.forEach((update) => {
          update.no_change_guard = true;
          update.guard_reason = "最近用户消息明确表示没有状态变化，本轮自动更新已拦截。";
        });
      }
      bubble.setAttribute(SCAN_ATTR, "done");
    }
    return updates;
  }

  const NO_CHANGE_PATTERNS = [
    /没有(?:移动|换位置|离开|出门|受伤|状态变化|改变状态|任何变化|明显变化)/,
    /没有任何人(?:受伤|改变状态|移动)/,
    /没有人(?:受伤|移动|改变状态)/,
    /停在原地/,
    /原地(?:停留|闲聊|聊天)/,
    /只是(?:聊了几句|简单聊|闲聊)/,
    /不(?:移动|改变状态|更新状态)/,
  ];

  function isNoChangeText(text) {
    const value = compact(text);
    if (!value) return false;
    return NO_CHANGE_PATTERNS.some((regex) => regex.test(value));
  }

  function nearestUserTextForBubble(bubble) {
    const message = bubble?.closest?.(".message") || bubble;
    const candidates = Array.from(document.querySelectorAll(".message.user, .user-message, [data-role='user'], [data-message-role='user']"));
    if (!candidates.length) return "";

    const messageTop = message?.getBoundingClientRect?.().top ?? Number.POSITIVE_INFINITY;
    let best = null;
    let bestTop = Number.NEGATIVE_INFINITY;

    candidates.forEach((node) => {
      if (node.closest?.(`#${PANEL_ID}`)) return;
      const top = node.getBoundingClientRect?.().top ?? Number.NEGATIVE_INFINITY;
      if (top <= messageTop && top >= bestTop) {
        best = node;
        bestTop = top;
      }
    });

    if (best) return best.textContent || "";
    return candidates[candidates.length - 1]?.textContent || "";
  }

  function shouldBlockBecauseNoChange(bubble) {
    return isNoChangeText(nearestUserTextForBubble(bubble));
  }

  async function applyDetectedUpdate(update) {
    if (!update || !update.update_id || applying) {
      window.setTimeout(() => applyDetectedUpdate(update), 300);
      return;
    }
    applying = true;
    const beforeChar = findCurrentCharacter(update);
    try {
      const mode = lastState?.settings?.auto_apply_mode || "safe";
      const response = await fetch(API_APPLY_UPDATE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ update, mode }),
      });
      if (response.ok) {
        const data = await response.json();
        const result = data.result || {};
        const status = result.status || "ok";
        const detail = readableUpdateDetail(update, result, beforeChar);
        pushDebug(status, `${sourceLabelForKind(update.kind)}提交 ${update.name || update.id || "未命名角色"}：${status}`, detail || result.reason || "", update.raw_text || "");
        bumpUnread(1);
        lastState = data;
        safeRenderPanel(data);
      } else {
        pushDebug("error", `提交失败 ${response.status}`, await response.text());
        bumpUnread(1);
      }
    } catch (error) {
      pushDebug("error", "提交异常", error?.message || String(error), update.raw_text || "");
      bumpUnread(1);
    } finally {
      applying = false;
    }
  }

  function historyMessagesFromPayload(data) {
    const source = Array.isArray(data) ? data
      : Array.isArray(data?.history) ? data.history
      : Array.isArray(data?.messages) ? data.messages
      : Array.isArray(data?.items) ? data.items
      : Array.isArray(data?.data) ? data.data
      : [];

    return source.map((item, index) => {
      if (typeof item === "string") return { role: "assistant", text: item, index };
      const role = String(item?.role || item?.sender || item?.type || item?.author || "").toLowerCase();
      const text = item?.content ?? item?.message ?? item?.text ?? item?.body ?? item?.value ?? "";
      return { role, text: String(text || ""), index };
    }).filter((item) => item.text);
  }

  function lastUserTextFromMessages(messages, assistantIndex) {
    for (let i = assistantIndex - 1; i >= 0; i -= 1) {
      const role = messages[i].role;
      if (role.includes("user") || role === "human") return messages[i].text;
    }
    return "";
  }

  async function scanHistoryForUpdates() {
    try {
      const response = await fetch(API_HISTORY, { cache: "no-store" });
      if (!response.ok) return [];
      const payload = await response.json();
      const messages = historyMessagesFromPayload(payload).slice(-20);
      const updates = [];

      messages.forEach((message, index) => {
        const role = message.role;
        const isAssistant = !role || role.includes("assistant") || role.includes("ai") || role.includes("bot") || role === "system";
        if (!isAssistant || !hasStatusUpdateText(message.text)) return;
        const source = `历史:${index}`;
        const found = extractUpdateBlocks(message.text, source)
          .filter((update) => update.update_id && !seenUpdateIds.has(update.update_id));
        const userText = lastUserTextFromMessages(messages, index);
        const guarded = isNoChangeText(userText);
        found.forEach((update) => {
          seenUpdateIds.add(update.update_id);
          if (guarded) {
            update.no_change_guard = true;
            update.guard_reason = "最近用户消息明确表示没有状态变化，本轮自动更新已拦截。";
          }
          pushDebug("caught", `历史状态块捕获 ${update.name || update.id || "未命名角色"}`, readableUpdateDetail(update, null, findCurrentCharacter(update)) || (update.source || source), update.raw_text || "");
        });
        updates.push(...found);
      });
      return updates;
    } catch (error) {
      pushDebug("error", "历史扫描失败", error?.message || String(error));
      return [];
    }
  }

  async function scanChatForUpdates() {
    if (!lastState) await loadPanel();

    const updates = [];
    updates.push(...await scanHistoryForUpdates());

    const bubbles = messageContainers();
    bubbles.forEach((bubble) => {
      updates.push(...cleanBubble(bubble));
    });

    for (const update of updates) {
      await applyDetectedUpdate(update);
    }

    if (lastState?.settings?.show_update_debug_blocks === true) {
      renderPanel(lastState);
    }
  }

  function scheduleScan() {
    window.clearTimeout(scanTimer);
    scanTimer = window.setTimeout(scanChatForUpdates, 250);
  }

  async function resolvePending(updateId, action) {
    try {
      const response = await fetch(API_RESOLVE_PENDING, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ update_id: updateId, action }),
      });
      if (response.ok) {
        const data = await response.json();
        lastState = data;
        safeRenderPanel(data);
      }
    } catch {
      // 不影响聊天页。
    }
  }



  function stripForCandidate(text) {
    return removeStatusBlocksFromText(String(text || ""));
  }

  function escapeRegex(value) {
    return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  const PROTECTED_LOCATION_TERMS = [
    "资料室门口", "资料室门边", "资料室桌边", "资料室里面", "资料室里", "资料室内", "资料室外",
    "休息室门口", "休息室门边", "休息室桌边", "休息室里面", "休息室里", "休息室内", "休息室外",
    "咖啡馆门口", "咖啡馆门边", "咖啡馆里面", "咖啡馆里", "咖啡馆内", "咖啡馆外",
    "学校操场上", "学校操场", "操场上", "餐厅门口", "食堂门口", "教室门口",
    "走廊里", "走廊内", "走廊", "门口", "门边", "窗边", "桌边", "旁边",
    "资料室", "休息室", "咖啡馆", "餐厅", "食堂", "厨房", "客厅", "房间", "大厅", "玄关", "教室", "操场"
  ];

  function protectKnownLocation(sourceText, candidate) {
    const source = compact(sourceText);
    const raw = compact(candidate);
    if (!raw) return "";
    const sortedTerms = PROTECTED_LOCATION_TERMS.slice().sort((left, right) => right.length - left.length);
    for (const term of sortedTerms) {
      if (source.includes(term) && (raw === term || term.includes(raw) || raw.includes(term))) return term;
    }
    if (raw === "廊" && source.includes("走廊")) return "走廊";
    return raw;
  }

  function meaningfulLocation(value, sourceText = "") {
    let text = compact(value);
    text = protectKnownLocation(sourceText || value, text);
    text = text.replace(/^(?:到|至|往|向|进入|来到|走到|走进|走入|走向|移动到|移到|回到|到达|到了|转移到|带到|带去|带往)/, "");
    text = protectKnownLocation(sourceText || value, text);
    text = text.replace(/[，。；、,.!?！？].*$/, "").trim();
    text = text.replace(/^(?:了|在|的|旁边|身边)/, "").trim();
    if (!text || text.length > 24) return "";
    if (text.length < 2 && !PROTECTED_LOCATION_TERMS.includes(text)) return "";
    if (/没有|状态|异常|受伤|移动|改变|平稳|放松|紧张|开心|情绪|心情|身体|良好|正常/.test(text)) return "";
    return text;
  }

  function findLocationCandidate(text) {
    const value = compact(text);
    const compoundPatterns = [
      /([\u4e00-\u9fffA-Za-z0-9]{1,12}(?:资料室|休息室|咖啡馆|餐厅|食堂|教室|房间|大厅|玄关|厨房|客厅|走廊|操场)(?:门口|门边|桌边|旁边|附近|里面|里|内|外|上)?)/,
      /([\u4e00-\u9fffA-Za-z0-9]{1,12}(?:门口|门边|桌边|窗边|旁边))/,
    ];
    for (const pattern of compoundPatterns) {
      const match = value.match(pattern);
      const loc = meaningfulLocation(match?.[1] || "", value);
      if (loc) return loc;
    }
    const patterns = [
      /从[^，。；\n]{1,24}?(?:移动到|移到|来到|进入|走到|走进|走入|走向|回到|到达|到了|转移到)([^，。；\n]{1,24})/,
      /(?:移动到|移到|来到|进入|走到|走进|走入|走向|回到|到达|到了|转移到)([^，。；\n]{1,24})/,
      /(?:带到|带去|带往)([^，。；\n]{1,24})/,
      /(?:停在|坐到|留在|待在)([^，。；\n]{1,24})/,
    ];
    for (const pattern of patterns) {
      const match = value.match(pattern);
      const loc = meaningfulLocation(match?.[1] || "", value);
      if (loc) return loc;
    }
    return "";
  }

  function naturalReasonText({ location, hpmp, effectParts, extra }) {
    const reasons = [];
    if (location) reasons.push(`检测到地点变化：${location}`);
    if (hpmp?.hp_current || hpmp?.hp_max) reasons.push("检测到 HP 数值变化");
    if (hpmp?.mp_current || hpmp?.mp_max) reasons.push("检测到 MP 数值变化");
    const add = splitList(effectParts?.effects_add).join("、");
    const remove = splitList(effectParts?.effects_remove).join("、");
    if (add) reasons.push(`检测到新增状态：${add}`);
    if (remove) reasons.push(`检测到移除状态：${remove}`);
    if (effectParts?.effects_clear) reasons.push("检测到恢复正常 / 无异常描述");
    const extraKeys = extra && typeof extra === "object" ? Object.keys(extra) : [];
    if (extraKeys.length) reasons.push(`检测到扩展字段：${extraKeys.join("、")}`);
    return reasons.join("；") || "检测到可能状态变化";
  }
  function findHpMpCandidates(text) {
    const value = compact(text);
    const result = {};
    const hp = value.match(/(?:HP|hp|血量|生命值?)\s*(?:变为|变成|变到|降到|降至|=|：|:)?\s*([0-9]+\s*\/\s*[0-9]+)/i);
    if (hp) {
      const parts = hp[1].replace(/\s+/g, "").split("/");
      result.hp_current = parts[0] || "";
      result.hp_max = parts[1] || "";
    }
    const mp = value.match(/(?:MP|mp|魔力|灵力|法力)\s*(?:变为|变成|变到|降到|降至|=|：|:)?\s*([0-9]+\s*\/\s*[0-9]+)/i);
    if (mp) {
      const parts = mp[1].replace(/\s+/g, "").split("/");
      result.mp_current = parts[0] || "";
      result.mp_max = parts[1] || "";
    }
    return result;
  }

  function findEffectCandidates(text) {
    const value = compact(text);
    const effectsAdd = [];
    const effectsRemove = [];
    let effectsClear = false;
    function add(effect) { if (effect && !effectsAdd.includes(effect)) effectsAdd.push(effect); }
    function remove(effect) { if (effect && !effectsRemove.includes(effect)) effectsRemove.push(effect); }
    if (/不再紧张|不紧张了|放松下来|慢慢放松|逐渐放松/.test(value)) remove("紧张");
    if (/解除(?:警戒|警惕|戒备)|不再(?:警戒|警惕|戒备)/.test(value)) remove("警戒");
    if (/恢复正常|状态正常|状态没有异常|没有异常|无异常/.test(value)) effectsClear = true;
    if (/轻微紧张|稍微紧张|有点紧张|略显紧张/.test(value)) add("轻微紧张");
    else if (/紧张/.test(value) && !/不再紧张|不紧张/.test(value)) add("紧张");
    if (/警戒|警惕|戒备/.test(value) && !/解除(?:警戒|警惕|戒备)|不再(?:警戒|警惕|戒备)/.test(value)) add("警戒");
    if (/疲惫|疲劳|很累|劳累/.test(value)) add("疲惫");
    if (/腿[^，。；\n]{0,8}擦伤|擦伤[^，。；\n]{0,8}腿/.test(value)) add("腿部擦伤");
    else if (/擦伤/.test(value)) add("轻微擦伤");
    else if (/受伤/.test(value)) add("受伤");
    if (/昏迷/.test(value)) add("昏迷");
    return { effects_add: effectsAdd, effects_remove: effectsRemove, effects_clear: effectsClear };
  }

  function findExtraCandidates(text) {
    const value = compact(text);
    const extra = {};
    const patterns = [
      ["精神状态", /精神状态\s*(?:变成|变为|是|为|：|:)\s*([^，。；\n]{1,32})/],
      ["行动状态", /行动状态\s*(?:变成|变为|是|为|：|:)\s*([^，。；\n]{1,32})/],
      ["当前目标", /(?:当前目标|目标)\s*(?:变成|变为|是|为|：|:)\s*([^，。；\n]{1,32})/],
      ["腿部状态", /腿部状态\s*(?:变成|变为|是|为|：|:)\s*([^，。；\n]{1,32})/],
      ["装备", /(?:装备|携带物)\s*(?:变成|变为|是|为|：|:)\s*([^，。；\n]{1,32})/],
    ];
    patterns.forEach(([key, pattern]) => {
      const match = value.match(pattern);
      if (match?.[1]) extra[key] = compact(match[1]);
    });
    if (!extra["装备"]) {
      const equipment = [];
      const explicitEquipment = /(?:装备|携带物|当前装备|获得|拿起|取出|更换|换成|收起|放下|装备上|配备)/.test(value);
      if (explicitEquipment && /平板/.test(value)) equipment.push("平板电脑");
      if (explicitEquipment && /画笔/.test(value)) equipment.push("画笔");
      if (explicitEquipment && /笔记本/.test(value)) equipment.push("笔记本");
      if (equipment.length) extra["装备"] = equipment.join("、");
    }
    if (!extra["腿部状态"] && /腿部?[^，。；\n]{0,10}(?:正常|无异常)/.test(value)) extra["腿部状态"] = "正常";
    return extra;
  }

  function targetCharactersForText(text) {
    const characters = Array.isArray(lastState?.characters) ? lastState.characters.filter((item) => item.visible !== false) : [];
    if (!characters.length) return [];
    const value = compact(text);
    const matched = [];
    const seen = new Set();
    const mention = findCharacterMentionInText(value, characters);
    if (mention?.character) {
      matched.push(mention.character);
      seen.add(String(mention.character.id || mention.character.name || ""));
    }
    characters.forEach((item) => {
      const name = compact(item.name);
      const aliases = aliasesOf(item);
      const hit = (name && textContainsMention(value, name)) || aliases.some((alias) => textContainsMention(value, alias));
      const key = String(item.id || item.name || "");
      if (hit && !seen.has(key)) {
        matched.push(item);
        seen.add(key);
      }
    });
    if (matched.length) return matched;
    return characters.length === 1 ? [characters[0]] : [];
  }

  function naturalCandidateHasFields(update) {
    return Boolean(compact(update.location) || compact(update.alive_status) || compact(update.hp_current) || compact(update.hp_max) || compact(update.mp_current) || compact(update.mp_max) || splitList(update.effects_add).length || splitList(update.effects_remove).length || update.effects_clear || (update.extra && Object.keys(update.extra).length));
  }

  function extractNaturalCandidates(rawText, context = {}) {
    const userText = compact(context.userText || "");
    const assistantText = stripForCandidate(rawText);
    const combined = [userText, assistantText].filter(Boolean).join("\n");
    if (!combined) return [];
    if (isNoChangeText(userText) || isNoChangeText(combined)) {
      pushDebug("guarded", "自然语言候选已跳过", "本轮明确表示没有状态变化。", userText || combined);
      return [];
    }
    const targets = targetCharactersForText(combined);
    if (!targets.length) return [];
    const location = findLocationCandidate(combined);
    const hpmp = findHpMpCandidates(combined);
    const effectParts = findEffectCandidates(combined);
    const extra = findExtraCandidates(combined);
    const candidates = [];
    targets.forEach((char) => {
      const update = { kind: "natural_candidate", source: "自然语言候选", id: char.id || "", name: char.name || "未命名角色", raw_text: combined, location, ...hpmp, effects_add: effectParts.effects_add, effects_remove: effectParts.effects_remove, effects_clear: effectParts.effects_clear, extra };
      update.update_id = makeHash(["natural", update.id, update.name, combined, JSON.stringify(update.extra || {})].join("\n"));
      if (!naturalCandidateHasFields(update)) return;
      candidates.push({ id: update.update_id, update, confidence: "候选", reason: naturalReasonText({ location, hpmp, effectParts, extra }), created_at: new Date().toLocaleTimeString() });
    });
    return candidates;
  }

  function addNaturalCandidates(candidates) {
    let changed = false;
    candidates.forEach((candidate) => {
      if (!candidate?.id) return;
      if (naturalCandidates.some((item) => item.id === candidate.id)) return;
      naturalCandidates.unshift(candidate);
      changed = true;
      pushDebug("candidate", `自然语言候选 ${candidate.update?.name || "未命名角色"}`, candidateSummary(candidate), candidate.update?.raw_text || "");
    });
    if (naturalCandidates.length > 20) naturalCandidates.length = 20;
    if (changed) bumpUnread(candidates.length);
    if (changed && lastState) safeRenderPanel(lastState);
  }

  async function applyNaturalCandidate(candidateId) {
    const index = naturalCandidates.findIndex((item) => item.id === candidateId);
    if (index < 0) return;
    const candidate = naturalCandidates[index];
    try {
      const response = await fetch(API_APPLY_UPDATE, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ update: candidate.update, mode: "all" }) });
      if (response.ok) {
        const data = await response.json();
        naturalCandidates.splice(index, 1);
        const result = data.result || {};
        const detail = readableUpdateDetail(candidate.update, result, null) || candidateSummary(candidate);
        lastState = data;
        pushDebug("applied", `应用自然语言候选 ${candidate.update?.name || "未命名角色"}`, detail, candidate.update?.raw_text || "");
        safeRenderPanel(data, { force: true });
      } else {
        pushDebug("error", `候选应用失败 ${response.status}`, await response.text());
        safeRenderPanel(lastState);
      }
    } catch (error) {
      pushDebug("error", "候选应用异常", error?.message || String(error));
      safeRenderPanel(lastState);
    }
  }

  function ignoreNaturalCandidate(candidateId) {
    const index = naturalCandidates.findIndex((item) => item.id === candidateId);
    if (index < 0) return;
    const [candidate] = naturalCandidates.splice(index, 1);
    pushDebug("noop", `忽略自然语言候选 ${candidate.update?.name || "未命名角色"}`, candidateSummary(candidate));
    if (lastState) safeRenderPanel(lastState, { force: true });
  }

  function sanitizeAssistantText(rawText) {
    const settings = lastState?.settings || {};
    if (settings.hide_update_blocks === false) return String(rawText || "");
    return removeStatusBlocksFromText(rawText);
  }

  function cleanupExistingAssistantBubbles() {
    document.querySelectorAll(".message.assistant .bubble, .message.system .bubble").forEach((bubble) => {
      if (!bubble) return;
      const before = bubble.textContent || "";
      if (!/status_panel_update|状态栏更新|状态更新/i.test(before)) return;
      const after = sanitizeAssistantText(before);
      if (after !== before) bubble.textContent = after;
    });
  }

  function processAssistantText(rawText, context = {}) {
    const source = context.source || "chat_done";
    const text = String(rawText || "");
    const updates = extractUpdateBlocks(text, source).filter((update) => update.update_id && !seenUpdateIds.has(update.update_id));
    updates.forEach((update) => {
      seenUpdateIds.add(update.update_id);
      if (isNoChangeText(context.userText || "")) {
        update.no_change_guard = true;
        update.guard_reason = "用户消息明确表示没有状态变化，本轮自动更新已拦截。";
      }
      pushDebug("caught", `状态块捕获 ${update.name || update.id || "未命名角色"}`, readableUpdateDetail(update, null, findCurrentCharacter(update)) || source, update.raw_text || "");
      applyDetectedUpdate(update);
    });
    const cleanedText = sanitizeAssistantText(text);
    if (!updates.length) addNaturalCandidates(extractNaturalCandidates(cleanedText, context));
    if (lastState?.settings?.show_update_debug_blocks === true) safeRenderPanel(lastState);
    return { cleanedText, updates };
  }

  window.XuqiStatusPanel = Object.assign(window.XuqiStatusPanel || {}, { sanitizeAssistantText, processAssistantText, extractNaturalCandidates });

  document.addEventListener("DOMContentLoaded", async () => {
    await loadFieldSchema();
    await loadPanel();
    cleanupExistingAssistantBubbles();
    await scanChatForUpdates();
    window.setInterval(loadPanel, 15000);
    window.setInterval(scanChatForUpdates, 2000);
    window.addEventListener("resize", () => {
      const panel = document.getElementById(PANEL_ID);
      if (panel) applyStoredPosition(panel);
    });
    const messages = document.getElementById("messages") || document.body;
    const observer = new MutationObserver(scheduleScan);
    observer.observe(messages, { childList: true, subtree: true, characterData: true });
  });
})();
