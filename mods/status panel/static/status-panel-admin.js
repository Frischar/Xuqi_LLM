(() => {
  const API_STATE = "/mods/status-panel/app/api/state";
  const API_SUMMARY = "/mods/status-panel/app/api/summary";
  const API_SCHEMA = "/mods/status-panel/app/api/field-schema";
  const API_RESOLVE_PENDING = "/mods/status-panel/app/api/pending-updates/resolve";

  let state = { settings: {}, characters: [], pending_updates: [], processed_update_ids: [] };
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
      { key: "last_event", label: "最近变化" },
      { key: "updated_at", label: "更新时间" },
      { key: "extra.*", label: "扩展资料" },
    ],
  };

  let activeTab = "overview";
  let selectedCharacterId = "";
  let characterSearch = "";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function uid() {
    return `char-${Math.random().toString(16).slice(2, 10)}`;
  }

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function splitList(value) {
    if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
    return String(value || "")
      .replace(/[、/]/g, ",")
      .replace(/[，]/g, ",")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function aliasesToText(value) {
    return splitList(Array.isArray(value) ? value.join(",") : value).join("、");
  }

  function normalizeMentionKey(value) {
    return String(value || "")
      .trim()
      .replace(/[\s\u3000]+/g, "")
      .replace(/[“”\"'‘’「」『』（）()\[\]【】]/g, "")
      .replace(/[，。！？、,.!?~～—\-…:：;；]/g, "")
      .toLowerCase();
  }

  function sameMention(left, right) {
    const a = normalizeMentionKey(left);
    const b = normalizeMentionKey(right);
    return !!a && !!b && a === b;
  }

  function textToAliases(value) {
    return splitList(value);
  }

  function joinList(value) {
    return splitList(value).join(", ");
  }

  function normalizeExtra(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const result = {};
    Object.entries(value).forEach(([key, rawVal]) => {
      const name = String(key || "").trim();
      const text = Array.isArray(rawVal)
        ? rawVal.map((item) => String(item || "").trim()).filter(Boolean).join("、")
        : String(rawVal || "").trim();
      if (name && text) result[name] = text;
    });
    return result;
  }

  function extraToText(value) {
    const extra = normalizeExtra(value);
    return Object.entries(extra).map(([key, val]) => `${key}: ${val}`).join("\n");
  }

  function parseExtraText(text) {
    const result = {};
    String(text || "").split(/\n+/).forEach((line) => {
      const match = line.match(/^([^:：]+)[:：]\s*(.*)$/);
      if (!match) return;
      const key = match[1].trim();
      const value = match[2].trim();
      if (key && value) result[key] = value;
    });
    return result;
  }

  function nowString() {
    return new Date().toLocaleString("zh-CN", { hour12: false });
  }

  function isEmptyValue(value) {
    const text = String(value ?? "").trim();
    return !text || ["?", "未知", "未记录", "未提取", "无", "无明显异常"].includes(text);
  }

  function hpText(item) {
    return item?.hp_current || item?.hp_max ? `${item.hp_current || "?"}/${item.hp_max || "?"}` : "未记录";
  }

  function mpText(item) {
    return item?.mp_current || item?.mp_max ? `${item.mp_current || "?"}/${item.mp_max || "?"}` : "未记录";
  }

  function statusText(item) {
    const effects = splitList(item?.status_effects);
    return effects.length ? effects.join("、") : "无明显异常";
  }

  function normalizeSchema(schema) {
    const fallbackDetails = fieldSchema.detail_fields?.length ? fieldSchema.detail_fields : [
      { key: "group", label: "分组" },
      { key: "relationship", label: "关系" },
      { key: "short_summary", label: "摘要" },
      { key: "last_event", label: "最近变化" },
      { key: "updated_at", label: "更新时间" },
      { key: "extra.*", label: "扩展资料" },
    ];
    const rawColumns = Array.isArray(schema?.table_columns) ? schema.table_columns : [];
    const seen = new Set();
    const columns = [];
    rawColumns.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const key = String(item.key || "").trim();
      const label = String(item.label || key).trim();
      if (!key || seen.has(key)) return;
      seen.add(key);
      columns.push({ key, label: label || key });
    });
    return {
      table_columns: columns.length ? columns : [
        { key: "name", label: "角色名" },
        { key: "alive_status", label: "存活状态" },
        { key: "hp", label: "HP" },
        { key: "mp", label: "MP" },
        { key: "location", label: "地点" },
        { key: "status_effects", label: "身体状态" },
      ],
      detail_fields: Array.isArray(schema?.detail_fields) && schema.detail_fields.length ? schema.detail_fields : fallbackDetails,
    };
  }

  async function loadFieldSchema() {
    try {
      const response = await fetch(API_SCHEMA, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      fieldSchema = normalizeSchema(data.schema || {});
    } catch {
      fieldSchema = normalizeSchema(fieldSchema);
    }
    renderFieldSchema();
  }

  function renderFieldSchema() {
    const list = $("#xsp-table-column-list");
    if (!list) return;
    const columns = Array.isArray(fieldSchema.table_columns) ? fieldSchema.table_columns : [];
    list.innerHTML = `
      <div class="xsp-field-table-header" aria-hidden="true">
        <span class="xsp-field-table-handle">排序</span>
        <span>字段来源</span>
        <span>显示名称</span>
        <span>操作</span>
      </div>
    `;
    columns.forEach((column, index) => {
      const row = document.createElement("div");
      row.className = "xsp-column-row xsp-field-card xsp-field-table-row";
      row.dataset.index = String(index);
      row.innerHTML = `
        <div class="xsp-field-drag-cell xsp-field-order-cell" title="拖动排序，也可使用右侧上移/下移">
          <button type="button" class="xsp-drag-handle" draggable="true" data-drag-index="${index}" aria-label="拖动调整顺序">⋮⋮</button>
          <span class="xsp-column-order">${index + 1}</span>
        </div>
        <label class="xsp-field-source-cell">
          <span>字段来源</span>
          <input data-column-field="key" value="${esc(column.key || "")}" placeholder="name 或 extra.腿部状态" />
        </label>
        <label class="xsp-field-label-cell">
          <span>显示名称</span>
          <input data-column-field="label" value="${esc(column.label || column.key || "")}" placeholder="角色名 / 腿部" />
        </label>
        <div class="xsp-column-actions xsp-field-card-actions">
          <button type="button" class="xsp-icon-btn" title="上移" data-column-action="up" ${index === 0 ? "disabled" : ""}>↑</button>
          <button type="button" class="xsp-icon-btn" title="下移" data-column-action="down" ${index === columns.length - 1 ? "disabled" : ""}>↓</button>
          <button type="button" class="xsp-mini-danger" data-column-action="delete">删除</button>
        </div>
      `;
      list.appendChild(row);
    });

    list.querySelectorAll("[data-column-field]").forEach((input) => {
      input.addEventListener("input", () => {
        collectFieldSchema();
        const row = input.closest(".xsp-field-card");
        const label = row?.querySelector('[data-column-field="label"]')?.value?.trim();
        const key = row?.querySelector('[data-column-field="key"]')?.value?.trim();
        row?.setAttribute("data-field-title", label || key || "未命名字段");
      });
      input.addEventListener("change", collectFieldSchema);
    });
    list.querySelectorAll("[data-column-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".xsp-column-row");
        const index = Number(row?.dataset?.index ?? -1);
        if (!Number.isInteger(index) || index < 0) return;
        collectFieldSchema();
        const action = button.dataset.columnAction;
        if (action === "delete") fieldSchema.table_columns.splice(index, 1);
        if (action === "up" && index > 0) [fieldSchema.table_columns[index - 1], fieldSchema.table_columns[index]] = [fieldSchema.table_columns[index], fieldSchema.table_columns[index - 1]];
        if (action === "down" && index < fieldSchema.table_columns.length - 1) [fieldSchema.table_columns[index + 1], fieldSchema.table_columns[index]] = [fieldSchema.table_columns[index], fieldSchema.table_columns[index + 1]];
        renderFieldSchema();
      });
    });

    let dragSourceIndex = null;
    list.querySelectorAll(".xsp-drag-handle").forEach((handle) => {
      handle.addEventListener("dragstart", (event) => {
        collectFieldSchema();
        const row = handle.closest(".xsp-column-row");
        dragSourceIndex = Number(row?.dataset?.index ?? -1);
        if (!Number.isInteger(dragSourceIndex) || dragSourceIndex < 0) {
          event.preventDefault();
          dragSourceIndex = null;
          return;
        }
        row.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(dragSourceIndex));
      });
      handle.addEventListener("dragend", () => {
        dragSourceIndex = null;
        list.querySelectorAll(".xsp-column-row").forEach((row) => row.classList.remove("is-dragging", "is-drop-target"));
      });
    });

    list.querySelectorAll(".xsp-column-row").forEach((row) => {
      row.addEventListener("dragover", (event) => {
        if (dragSourceIndex === null) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        row.classList.add("is-drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("is-drop-target"));
      row.addEventListener("drop", (event) => {
        if (dragSourceIndex === null) return;
        event.preventDefault();
        const targetIndex = Number(row.dataset.index ?? -1);
        if (!Number.isInteger(targetIndex) || targetIndex < 0 || targetIndex === dragSourceIndex) {
          row.classList.remove("is-drop-target");
          return;
        }
        collectFieldSchema();
        const nextColumns = [...fieldSchema.table_columns];
        const [moved] = nextColumns.splice(dragSourceIndex, 1);
        nextColumns.splice(targetIndex, 0, moved);
        fieldSchema = { ...fieldSchema, table_columns: nextColumns };
        dragSourceIndex = null;
        renderFieldSchema();
      });
    });
  }

  function collectFieldSchema() {
    const rows = $$(".xsp-column-row");
    const columns = [];
    const seen = new Set();
    rows.forEach((row) => {
      const key = row.querySelector('[data-column-field="key"]')?.value?.trim() || "";
      const label = row.querySelector('[data-column-field="label"]')?.value?.trim() || key;
      if (!key || seen.has(key)) return;
      seen.add(key);
      columns.push({ key, label: label || key });
    });
    fieldSchema = { ...fieldSchema, table_columns: columns };
    return fieldSchema;
  }

  function addTableColumn() {
    collectFieldSchema();
    const keyInput = $("#xsp-new-column-key");
    const labelInput = $("#xsp-new-column-label");
    const key = keyInput.value.trim();
    const label = labelInput.value.trim() || key;
    const status = $("#xsp-schema-status");
    if (!key) {
      status.textContent = "请先填写字段来源";
      return;
    }
    if (fieldSchema.table_columns.some((item) => item.key === key)) {
      status.textContent = "这一列已经存在";
      return;
    }
    fieldSchema.table_columns.push({ key, label });
    keyInput.value = "";
    labelInput.value = "";
    status.textContent = "已加入，记得保存";
    renderFieldSchema();
  }

  async function saveFieldSchema({ quiet = false } = {}) {
    collectFieldSchema();
    const status = $("#xsp-schema-status");
    if (!quiet && status) status.textContent = "保存中...";
    try {
      const response = await fetch(API_SCHEMA, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fieldSchema),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      fieldSchema = normalizeSchema(data.schema || fieldSchema);
      renderFieldSchema();
      if (!quiet && status) {
        status.textContent = "显示字段已保存";
        setTimeout(() => { status.textContent = ""; }, 1600);
      }
      return true;
    } catch {
      if (status) status.textContent = "显示字段保存失败";
      return false;
    }
  }

  async function loadState() {
    const response = await fetch(API_STATE, { cache: "no-store" });
    const data = await response.json();
    state = {
      settings: data.settings || {},
      characters: Array.isArray(data.characters) ? data.characters : [],
      pending_updates: Array.isArray(data.pending_updates) ? data.pending_updates : [],
      processed_update_ids: Array.isArray(data.processed_update_ids) ? data.processed_update_ids : [],
    };
    ensureSelectedCharacter();
    renderAll();
    await renderSummary();
  }

  function renderAll() {
    renderSettings();
    renderDashboardStats();
    renderPendingList();
    renderOverviewCards();
    renderCharacterNav();
    renderCharacterEditor();
    renderSummaryLocal();
  }

  function renderSettings() {
    const setChecked = (selector, value) => { const el = $(selector); if (el) el.checked = value; };
    const setValue = (selector, value) => { const el = $(selector); if (el) el.value = value; };
    setChecked("#xsp-enabled", state.settings.enabled !== false);
    setChecked("#xsp-chat-panel-enabled", state.settings.chat_panel_enabled !== false);
    setChecked("#xsp-compact", state.settings.compact !== false);
    setChecked("#xsp-hide-update-blocks", state.settings.hide_update_blocks !== false);
    setChecked("#xsp-show-update-debug-blocks", state.settings.show_update_debug_blocks === true);
    setChecked("#xsp-show-pending-in-chat", state.settings.show_pending_in_chat !== false);
    setChecked("#xsp-hide-table-extras-in-detail", state.settings.hide_table_extras_in_detail === true);
    setValue("#xsp-title", state.settings.title || "角色状态");
    setValue("#xsp-max-visible", Number(state.settings.max_visible || 8));
    setValue("#xsp-auto-apply-mode", state.settings.auto_apply_mode || "safe");
  }

  function collectSettings() {
    const checked = (selector, fallback = false) => $(selector)?.checked ?? fallback;
    const value = (selector, fallback = "") => $(selector)?.value ?? fallback;
    state.settings = {
      ...state.settings,
      enabled: checked("#xsp-enabled", true),
      chat_panel_enabled: checked("#xsp-chat-panel-enabled", true),
      compact: checked("#xsp-compact", true),
      title: String(value("#xsp-title", "角色状态")).trim() || "角色状态",
      max_visible: Math.max(1, Math.min(50, Number(value("#xsp-max-visible", 8) || 8))),
      hide_update_blocks: checked("#xsp-hide-update-blocks", true),
      show_update_debug_blocks: checked("#xsp-show-update-debug-blocks", false),
      show_pending_in_chat: checked("#xsp-show-pending-in-chat", true),
      hide_table_extras_in_detail: checked("#xsp-hide-table-extras-in-detail", false),
      auto_apply_mode: value("#xsp-auto-apply-mode", "safe") || "safe",
    };
  }

  function ensureSelectedCharacter() {
    if (selectedCharacterId && state.characters.some((item) => String(item.id) === String(selectedCharacterId))) return;
    selectedCharacterId = String(state.characters[0]?.id || "");
  }

  function selectedCharacter() {
    return state.characters.find((item) => String(item.id) === String(selectedCharacterId));
  }

  function renderDashboardStats() {
    const root = $("#xsp-dashboard-stats");
    if (!root) return;
    const visible = state.characters.filter((item) => item.visible !== false).length;
    const hidden = Math.max(0, state.characters.length - visible);
    const pending = state.pending_updates.length;
    const latest = state.characters
      .map((item) => item.updated_at)
      .filter(Boolean)
      .slice(-1)[0] || "暂无";
    root.innerHTML = `
      <article><strong>${state.characters.length}</strong><span>角色总数</span></article>
      <article><strong>${visible}</strong><span>聊天页显示</span></article>
      <article><strong>${hidden}</strong><span>已隐藏</span></article>
      <article class="${pending ? "has-pending" : ""}"><strong>${pending}</strong><span>待确认</span></article>
      <article class="is-wide"><strong>${esc(latest)}</strong><span>最近更新时间</span></article>
    `;
  }

  function renderPendingList() {
    const root = $("#xsp-pending-list");
    const status = $("#xsp-pending-status");
    if (!root) return;
    if (status) status.textContent = state.pending_updates.length ? `${state.pending_updates.length} 条待处理` : "暂无待确认";
    root.innerHTML = "";
    if (!state.pending_updates.length) {
      root.innerHTML = `<p class="xsp-muted">当前没有待确认状态变化。</p>`;
      return;
    }
    for (const item of state.pending_updates) {
      const update = item.update || {};
      const fields = Array.isArray(item.pending_fields) ? item.pending_fields.join("、") : "all";
      const card = document.createElement("article");
      card.className = "xsp-admin-pending-card";
      card.innerHTML = `
        <div>
          <strong>${esc(update.name || update.id || "未命名角色")}</strong>
          <p>${esc(update.last_event || update.short_summary || update.summary || update.location || "有一条待确认更新")}</p>
          <span>来源：${esc(item.source || "聊天")}｜字段：${esc(fields)}｜${esc(item.created_at || "")}</span>
        </div>
        <div class="xsp-pending-actions">
          <button type="button" class="xsp-btn xsp-btn-primary" data-action="apply">应用</button>
          <button type="button" class="xsp-btn xsp-btn-danger-soft" data-action="ignore">忽略</button>
        </div>
      `;
      card.querySelector('[data-action="apply"]').addEventListener("click", () => resolvePending(item.update_id, "apply"));
      card.querySelector('[data-action="ignore"]').addEventListener("click", () => resolvePending(item.update_id, "ignore"));
      root.appendChild(card);
    }
  }

  async function resolvePending(updateId, action) {
    if (!updateId) return;
    const status = $("#xsp-pending-status");
    if (status) status.textContent = action === "ignore" ? "正在忽略..." : "正在应用...";
    try {
      const response = await fetch(API_RESOLVE_PENDING, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ update_id: updateId, action }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await loadState();
    } catch (error) {
      if (status) status.textContent = `处理失败：${error.message || error}`;
    }
  }

  function renderOverviewCards() {
    const root = $("#xsp-overview-list");
    if (!root) return;
    root.innerHTML = "";
    if (!state.characters.length) {
      root.innerHTML = `<div class="xsp-empty-card">当前还没有角色状态。可以新增角色，也可以去“资料扫描”里导入初始化资料。</div>`;
      return;
    }
    for (const item of state.characters) {
      const card = document.createElement("article");
      card.className = `xsp-overview-card ${item.visible === false ? "is-hidden" : ""}`;
      card.innerHTML = `
        <div class="xsp-overview-card-head">
          <div>
            <strong>${esc(item.name || "未命名角色")}</strong>
            <span>${esc(item.group || "未分组")}</span>
          </div>
          <em>${item.visible === false ? "已隐藏" : "显示中"}</em>
        </div>
        <div class="xsp-overview-fields xsp-status-chip-row">
          <span class="xsp-status-chip"><b>地点</b>${esc(item.location || "未记录")}</span>
          <span class="xsp-status-chip"><b>身体</b>${esc(statusText(item))}</span>
          <span class="xsp-status-chip"><b>HP</b>${esc(hpText(item))}</span>
          <span class="xsp-status-chip"><b>MP</b>${esc(mpText(item))}</span>
        </div>
        <p class="xsp-overview-summary">${esc(item.last_event || item.short_summary || "暂无最近变化。")}</p>
        <div class="xsp-overview-actions">
          <button type="button" class="xsp-btn" data-edit>编辑</button>
        </div>
      `;
      card.querySelector("[data-edit]").addEventListener("click", () => {
        selectedCharacterId = item.id;
        switchTab("editor");
        renderCharacterNav();
        renderCharacterEditor();
      });
      root.appendChild(card);
    }
  }

  function renderCharacterNav() {
    const root = $("#xsp-character-nav-list");
    if (!root) return;
    const keyword = characterSearch.trim().toLowerCase();
    const filtered = state.characters.filter((item) => {
      if (!keyword) return true;
      return [item.name, item.group, item.location, item.relationship].some((value) => String(value || "").toLowerCase().includes(keyword));
    });
    root.innerHTML = "";
    if (!filtered.length) {
      root.innerHTML = `<p class="xsp-muted">没有匹配的角色。</p>`;
      return;
    }
    for (const item of filtered) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `xsp-character-nav-item ${String(item.id) === String(selectedCharacterId) ? "is-active" : ""}`;
      button.innerHTML = `
        <strong>${esc(item.name || "未命名角色")}</strong>
        <span>${esc(item.location || item.group || "未记录")}</span>
      `;
      button.addEventListener("click", () => {
        collectActiveEditor();
        selectedCharacterId = item.id;
        renderCharacterNav();
        renderCharacterEditor();
      });
      root.appendChild(button);
    }
  }

  function renderCharacterEditor() {
    const root = $("#xsp-character-editor");
    const template = $("#xsp-character-editor-template");
    if (!root || !template) return;
    root.innerHTML = "";
    ensureSelectedCharacter();
    const character = selectedCharacter();
    if (!character) {
      root.innerHTML = `<div class="xsp-empty-card">还没有可编辑角色。点击左侧“新增”。</div>`;
      return;
    }
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.characterId = character.id || uid();
    node.querySelectorAll("[data-field]").forEach((input) => {
      const field = input.dataset.field;
      if (field === "visible") input.checked = character.visible !== false;
      else if (field === "status_effects") input.value = joinList(character.status_effects);
      else if (field === "_aliases_text") input.value = aliasesToText(character.aliases || []);
      else if (field === "_extra_text") input.value = extraToText(character.extra || character.extras || character.custom || {});
      else input.value = character[field] || "";
    });

    node.querySelector("[data-action='delete']").addEventListener("click", () => {
      const name = character.name || "这个角色";
      if (!window.confirm(`确认删除 ${name} 的状态吗？`)) return;
      state.characters = state.characters.filter((item) => String(item.id) !== String(node.dataset.characterId));
      selectedCharacterId = String(state.characters[0]?.id || "");
      renderAll();
    });

    node.addEventListener("input", () => {
      collectActiveEditor();
      renderSummaryLocal();
    });
    node.addEventListener("change", () => {
      collectActiveEditor();
      renderCharacterNav();
      renderDashboardStats();
      renderSummaryLocal();
    });

    root.appendChild(node);
  }

  function collectActiveEditor() {
    const card = $("#xsp-character-editor .xsp-edit-card");
    if (!card) return;
    const id = card.dataset.characterId || selectedCharacterId || uid();
    let item = state.characters.find((character) => String(character.id) === String(id));
    if (!item) {
      item = { id };
      state.characters.push(item);
    }
    item.id = id;
    card.querySelectorAll("[data-field]").forEach((input) => {
      const field = input.dataset.field;
      if (field === "visible") item[field] = input.checked;
      else if (field === "status_effects") item[field] = splitList(input.value);
      else if (field === "_aliases_text") item.aliases = textToAliases(input.value);
      else if (field === "_extra_text") item.extra = parseExtraText(input.value);
      else item[field] = input.value.trim();
    });
    item.updated_at = item.updated_at || nowString();
  }

  function collectCharacters() {
    collectActiveEditor();
    return state.characters;
  }

  function buildSummaryTextLocal() {
    const lines = [];
    const visible = state.characters.filter((item) => item.visible !== false);
    if (visible.length) lines.push("【角色状态摘要】");
    for (const item of visible) {
      const parts = [
        `${item.name || "未命名角色"}：${item.alive_status || "未知"}`,
        `HP ${hpText(item)}`,
        `MP ${mpText(item)}`,
        item.location ? `位置：${item.location}` : "",
        item.relationship ? `关系：${item.relationship}` : "",
        `状态：${statusText(item)}`,
        item.last_event ? `最近：${item.last_event}` : "",
        item.short_summary || "",
      ].filter(Boolean);
      lines.push(parts.join("，"));
    }
    return lines.join("\n") || "暂无可见角色。";
  }

  function renderSummaryPreview(rawText = "") {
    const tableRoot = $("#xsp-summary-preview-table");
    const rawRoot = $("#xsp-summary-preview-raw");
    if (rawRoot) rawRoot.textContent = rawText || buildSummaryTextLocal();
    if (!tableRoot) return;

    const visible = state.characters.filter((item) => item.visible !== false);
    if (!visible.length) {
      tableRoot.innerHTML = `<div class="xsp-summary-empty">暂无可见角色。</div>`;
      return;
    }

    tableRoot.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>角色</th><th>生存</th><th>HP</th><th>MP</th><th>地点</th><th>关系</th><th>状态</th><th>最近变化</th>
          </tr>
        </thead>
        <tbody>
          ${visible.map((item) => `
            <tr>
              <th>${esc(item.name || "未命名角色")}</th>
              <td>${esc(item.alive_status || "未知")}</td>
              <td>${esc(hpText(item))}</td>
              <td>${esc(mpText(item))}</td>
              <td>${esc(item.location || "未记录")}</td>
              <td>${esc(item.relationship || "未记录")}</td>
              <td>${esc(statusText(item))}</td>
              <td>${esc(item.last_event || item.short_summary || "未记录")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function renderSummaryLocal() {
    renderSummaryPreview(buildSummaryTextLocal());
  }

  async function renderSummary() {
    try {
      const response = await fetch(API_SUMMARY, { cache: "no-store" });
      const data = await response.json();
      renderSummaryPreview(data.summary || buildSummaryTextLocal());
    } catch {
      renderSummaryLocal();
    }
  }

  async function saveState({ quiet = false } = {}) {
    collectSettings();
    collectCharacters();
    const status = $("#xsp-save-status");
    if (!quiet && status) status.textContent = "保存中...";

    const response = await fetch(API_STATE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state),
    });

    if (!response.ok) {
      if (status) status.textContent = "保存失败";
      return false;
    }

    const data = await response.json();
    const schemaSaved = await saveFieldSchema({ quiet: true });
    state = {
      settings: data.settings || {},
      characters: Array.isArray(data.characters) ? data.characters : [],
      pending_updates: Array.isArray(data.pending_updates) ? data.pending_updates : [],
      processed_update_ids: Array.isArray(data.processed_update_ids) ? data.processed_update_ids : [],
    };
    ensureSelectedCharacter();
    renderAll();
    await renderSummary();

    if (!quiet && status) {
      status.textContent = schemaSaved ? "已保存" : "状态已保存，显示字段保存失败";
      setTimeout(() => { status.textContent = ""; }, 1800);
    }
    return true;
  }

  function addCharacter() {
    collectCharacters();
    const item = {
      id: uid(),
      name: "",
      aliases: [],
      group: "未分组",
      visible: true,
      alive_status: "存活",
      hp_current: "",
      hp_max: "",
      mp_current: "",
      mp_max: "",
      location: "",
      relationship: "",
      status_effects: [],
      short_summary: "",
      last_event: "",
      private_note: "",
      extra: {},
      updated_at: nowString(),
    };
    state.characters.push(item);
    selectedCharacterId = item.id;
    switchTab("editor");
    renderAll();
  }

  function findCharacter(candidate) {
    const id = String(candidate.id || "").trim();
    const name = String(candidate.name || "").trim();
    return state.characters.find((item) => {
      const itemId = String(item.id || "").trim();
      const itemName = String(item.name || "").trim();
      const aliases = textToAliases(Array.isArray(item.aliases) ? item.aliases.join(",") : item.aliases || "");
      return (id && itemId === id)
        || (name && sameMention(itemName, name))
        || (name && aliases.some((alias) => sameMention(alias, name)));
    });
  }

  const SCAN_FIELDS = [
    ["name", "角色名"],
    ["group", "分组"],
    ["alive_status", "生存"],
    ["hp_current", "HP 当前"],
    ["hp_max", "HP 上限"],
    ["mp_current", "MP 当前"],
    ["mp_max", "MP 上限"],
    ["location", "地点"],
    ["relationship", "关系"],
    ["short_summary", "长期摘要"],
    ["last_event", "最近变化"],
  ];

  function candidateFieldValue(candidate, field) {
    if (field === "status_effects") return joinList(candidate.status_effects || candidate.effects_add || []);
    return String(candidate[field] ?? "").trim();
  }

  function characterFieldValue(character, field) {
    if (field === "status_effects") return joinList(character.status_effects || []);
    return String(character?.[field] ?? "").trim();
  }

  function hasCandidateValue(candidate, field) {
    if (field === "status_effects") return splitList(candidate.status_effects || candidate.effects_add || []).length > 0;
    return !isEmptyValue(candidateFieldValue(candidate, field));
  }

  function applyCandidate(candidate, mode = "fill") {
    collectCharacters();
    let target = findCharacter(candidate);
    if (!target) {
      if (candidate.kind === "loose_memory") {
        window.alert?.("记忆候选只能绑定已有角色。请先创建角色，或在角色的别名里加入这个称呼。");
        return;
      }
      target = {
        id: candidate.id || uid(),
        name: candidate.name || "未命名角色",
        aliases: textToAliases(Array.isArray(candidate.aliases) ? candidate.aliases.join(",") : candidate.aliases || ""),
        group: candidate.group || "自动提取",
        visible: true,
        alive_status: "未知",
        hp_current: "",
        hp_max: "",
        mp_current: "",
        mp_max: "",
        location: "",
        relationship: "",
        status_effects: [],
        short_summary: "",
        last_event: "",
        private_note: "",
        extra: {},
      };
      state.characters.push(target);
    }

    if (Array.isArray(candidate.aliases) && candidate.aliases.length) {
      const aliasSet = new Set(textToAliases(Array.isArray(target.aliases) ? target.aliases.join(",") : target.aliases || ""));
      candidate.aliases.forEach((alias) => { if (alias) aliasSet.add(alias); });
      target.aliases = Array.from(aliasSet);
    }

    for (const [field] of SCAN_FIELDS) {
      if (!hasCandidateValue(candidate, field)) continue;
      const nextValue = candidateFieldValue(candidate, field);
      const currentValue = characterFieldValue(target, field);
      if (mode === "overwrite" || isEmptyValue(currentValue)) {
        target[field] = nextValue;
      }
    }

    const candidateEffects = splitList(candidate.status_effects);
    if (candidateEffects.length && (mode === "overwrite" || !splitList(target.status_effects).length)) {
      target.status_effects = candidateEffects;
    } else if (mode === "overwrite") {
      let effects = splitList(target.status_effects);
      for (const effect of splitList(candidate.effects_add)) if (!effects.includes(effect)) effects.push(effect);
      const remove = new Set(splitList(candidate.effects_remove));
      if (remove.size) effects = effects.filter((effect) => !remove.has(effect));
      target.status_effects = effects;
    } else if (!splitList(target.status_effects).length && splitList(candidate.effects_add).length) {
      target.status_effects = splitList(candidate.effects_add);
    }

    const nextExtra = normalizeExtra(candidate.extra || {});
    if (Object.keys(nextExtra).length) {
      const currentExtra = normalizeExtra(target.extra || {});
      for (const [key, value] of Object.entries(nextExtra)) {
        if (mode === "overwrite" || isEmptyValue(currentExtra[key])) currentExtra[key] = value;
      }
      target.extra = currentExtra;
    }

    target.updated_at = nowString();
    selectedCharacterId = target.id;
    renderAll();
    saveState({ quiet: true });
  }

  function sourceText(candidate) {
    if (Array.isArray(candidate.sources) && candidate.sources.length) {
      return [...new Set(candidate.sources.map((item) => {
        const title = item.source_title ? `｜${item.source_title}` : "";
        return `${item.source || "未知来源"}${title}${item.kind === "status_panel_update" ? "·更新" : ""}`;
      }))].join(" / ");
    }
    return candidate.source_title ? `${candidate.source || "未知来源"}｜${candidate.source_title}` : (candidate.source || "未知来源");
  }

  function scanMode() {
    return document.querySelector('input[name="xsp-scan-mode"]:checked')?.value || "safe";
  }

  function updateScanModeCards() {
    const current = scanMode();
    $$(".xsp-scan-mode-card").forEach((card) => {
      const input = card.querySelector('input[name="xsp-scan-mode"]');
      const selected = input?.value === current;
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-checked", selected ? "true" : "false");
    });
  }

  function renderDiffRows(candidate, existing) {
    const rows = [];
    for (const [field, label] of [...SCAN_FIELDS, ["status_effects", "身体状态"]]) {
      if (!hasCandidateValue(candidate, field)) continue;
      const current = existing ? characterFieldValue(existing, field) : "";
      const scanned = candidateFieldValue(candidate, field);
      let badge = "可补入";
      if (!existing) badge = "新角色";
      else if (isEmptyValue(current)) badge = "可补入";
      else if (current === scanned) badge = "无变化";
      else badge = "冲突";
      rows.push(`
        <tr class="${badge === "冲突" ? "is-conflict" : badge === "无变化" ? "is-same" : ""}">
          <th>${esc(label)}</th>
          <td>${esc(current || "空")}</td>
          <td>${esc(scanned || "空")}</td>
          <td><span class="xsp-diff-badge" data-diff-badge="${esc(badge)}">${esc(badge)}</span></td>
        </tr>
      `);
    }

    const extra = normalizeExtra(candidate.extra || {});
    for (const [key, scanned] of Object.entries(extra)) {
      const current = existing ? normalizeExtra(existing.extra || {})[key] : "";
      let badge = !existing ? "新角色" : isEmptyValue(current) ? "可补入" : current === scanned ? "无变化" : "冲突";
      rows.push(`
        <tr class="${badge === "冲突" ? "is-conflict" : badge === "无变化" ? "is-same" : ""}">
          <th>${esc(key)}</th>
          <td>${esc(current || "空")}</td>
          <td>${esc(scanned || "空")}</td>
          <td><span class="xsp-diff-badge" data-diff-badge="${esc(badge)}">${esc(badge)}</span></td>
        </tr>
      `);
    }

    return rows.join("") || `<tr><td colspan="4">没有可展示字段。</td></tr>`;
  }

  function renderScanResults(candidates, sourceResults = []) {
    const root = $("#xsp-scan-results");
    if (!root) return;
    root.innerHTML = "";

    const sourceLine = document.createElement("div");
    sourceLine.className = "xsp-source-result-line";
    sourceLine.innerHTML = sourceResults.map((item) => {
      const cls = item.ok ? "is-ok" : "is-fail";
      if (item.isInfo) return `<span class="${cls} xsp-source-index-chip">${esc(item.label)}</span>`;
      return `<span class="${cls}">${esc(item.label)}：${item.ok ? `${item.count} 条` : "读取失败"}</span>`;
    }).join("");
    root.appendChild(sourceLine);

    if (!candidates.length) {
      root.insertAdjacentHTML("beforeend", `<p class="xsp-muted">没有扫描到可用状态信息。标准状态块最稳定；原记忆区会尝试提取自然语言候选，但不会直接覆盖当前状态。</p>`);
      return;
    }

    for (const candidate of candidates) {
      const existing = findCharacter(candidate);
      const modeText = candidate.kind === "status_panel_update" ? "动态更新" : candidate.kind === "status_panel" ? "初始化资料" : candidate.kind === "loose_memory" ? "记忆候选" : "兼容识别";
      const card = document.createElement("article");
      card.className = `xsp-candidate-card xsp-clean-candidate ${candidate.kind === "status_panel_update" ? "is-update" : ""}`;
      card.innerHTML = `
        <div class="xsp-candidate-head">
          <div>
            <strong>${esc(candidate.name || "未命名角色")}</strong>
            <span class="xsp-candidate-badge">${esc(modeText)}</span>
            ${existing ? `<span class="xsp-candidate-badge is-existing">已有角色</span>` : `<span class="xsp-candidate-badge">新角色</span>`}
            ${candidate.matched_alias ? `<span class="xsp-candidate-badge is-existing">匹配别名：${esc(candidate.matched_alias)}</span>` : ""}
            ${candidate.source_title ? `<span class="xsp-candidate-badge">来源：${esc(candidate.source_title)}</span>` : ""}
          </div>
          <span>${esc(sourceText(candidate))}</span>
        </div>
        <table class="xsp-scan-diff-table">
          <thead><tr><th>字段</th><th>当前状态</th><th>扫描结果</th><th>建议</th></tr></thead>
          <tbody>${renderDiffRows(candidate, existing)}</tbody>
        </table>
        <div class="xsp-candidate-operation-bar">
          <details class="xsp-raw-details">
            <summary>查看来源片段</summary>
            <pre>${esc((candidate.sources?.[0]?.raw_text || candidate.raw_text || "").slice(0, 1200))}</pre>
          </details>
          <div class="xsp-candidate-actions">
            <span class="xsp-action-label">建议操作</span>
            <button type="button" class="xsp-btn xsp-btn-primary" data-apply-fill>只补空字段</button>
            <button type="button" class="xsp-btn xsp-btn-warning" data-apply-overwrite>覆盖当前状态</button>
            <button type="button" class="xsp-btn xsp-btn-danger-soft" data-ignore>忽略</button>
          </div>
        </div>
      `;
      const currentMode = scanMode();
      if (currentMode === "overwrite") {
        card.querySelector("[data-apply-overwrite]").classList.add("is-default-warning");
      }
      card.querySelector("[data-apply-fill]").addEventListener("click", () => {
        applyCandidate(candidate, "fill");
        card.classList.add("is-applied");
        card.querySelector("[data-apply-fill]").textContent = "已补入";
        card.querySelector("[data-apply-fill]").disabled = true;
      });
      card.querySelector("[data-apply-overwrite]").addEventListener("click", () => {
        applyCandidate(candidate, "overwrite");
        card.classList.add("is-applied");
        card.querySelector("[data-apply-overwrite]").textContent = "已覆盖";
        card.querySelector("[data-apply-overwrite]").disabled = true;
      });
      card.querySelector("[data-ignore]").addEventListener("click", () => card.remove());
      root.appendChild(card);
    }
  }

  function getEnabledSources() {
    return $$('[data-source-toggle]')
      .filter((input) => input.checked)
      .map((input) => input.dataset.sourceToggle);
  }


  function mergeFreshCharacterAliasesForScan(freshCharacters = []) {
    const freshList = Array.isArray(freshCharacters) ? freshCharacters : [];
    if (!freshList.length) return state.characters;
    const normalizeKey = (value) => String(value || "").trim().replace(/[\s\u3000]+/g, "").toLowerCase();
    const currentById = new Map();
    const currentByName = new Map();
    state.characters.forEach((item) => {
      const id = normalizeKey(item.id);
      const name = normalizeKey(item.name);
      if (id) currentById.set(id, item);
      if (name) currentByName.set(name, item);
    });
    freshList.forEach((fresh) => {
      const id = normalizeKey(fresh?.id);
      const name = normalizeKey(fresh?.name);
      let target = (id && currentById.get(id)) || (name && currentByName.get(name));
      if (!target) {
        target = { ...(fresh || {}) };
        target.aliases = textToAliases(Array.isArray(fresh?.aliases) ? fresh.aliases.join(",") : fresh?.aliases || "");
        state.characters.push(target);
        if (id) currentById.set(id, target);
        if (name) currentByName.set(name, target);
        return;
      }
      const aliasSet = new Set(textToAliases(Array.isArray(target.aliases) ? target.aliases.join(",") : target.aliases || ""));
      textToAliases(Array.isArray(fresh?.aliases) ? fresh.aliases.join(",") : fresh?.aliases || "").forEach((alias) => aliasSet.add(alias));
      target.aliases = Array.from(aliasSet).filter(Boolean);
    });
    return state.characters;
  }

  async function refreshCharactersForScan() {
    try {
      const response = await fetch(API_STATE, { cache: "no-store" });
      if (!response.ok) return state.characters;
      const data = await response.json();
      const freshCharacters = Array.isArray(data.characters) ? data.characters : [];
      return mergeFreshCharacterAliasesForScan(freshCharacters);
    } catch (error) {
      console.warn("Status panel scan state refresh failed:", error);
      return state.characters;
    }
  }

  function scanRoleIndexSummary(characters = []) {
    const list = Array.isArray(characters) ? characters : [];
    if (!list.length) return "角色索引：空";
    return "角色索引：" + list.map((item) => {
      const aliases = textToAliases(Array.isArray(item.aliases) ? item.aliases.join(",") : item.aliases || "");
      return `${item.name || item.id || "未命名"}${aliases.length ? `（别名：${aliases.join("、")}）` : ""}`;
    }).join("；");
  }

  async function scanSources() {
    const button = $("#xsp-scan-sources");
    const status = $("#xsp-scan-status");
    button.disabled = true;
    button.textContent = "扫描中...";
    status.textContent = "正在读取资料";

    try {
      collectCharacters();
      const scanCharacters = await refreshCharactersForScan();
      const result = await window.XuqiStatusPanelExtractor.scan({ enabledSources: getEnabledSources(), characters: scanCharacters });
      result.sourceResults = Array.isArray(result.sourceResults) ? result.sourceResults : [];
      result.sourceResults.unshift({ key: "role_index", label: scanRoleIndexSummary(scanCharacters), ok: true, count: scanCharacters.length, isInfo: true });
      renderScanResults(result.candidates || [], result.sourceResults || []);
      status.textContent = `找到 ${(result.candidates || []).length} 个候选`;
    } catch (error) {
      status.textContent = "扫描失败";
      $("#xsp-scan-results").innerHTML = `<p class="xsp-muted">扫描失败：${esc(error)}</p>`;
    } finally {
      button.disabled = false;
      button.textContent = "扫描资料";
    }
  }

  function switchTab(name) {
    activeTab = name || "overview";
    $$('[data-xsp-tab-button]').forEach((button) => {
      button.classList.toggle("is-active", button.dataset.xspTabButton === activeTab);
    });
    $$('[data-xsp-tab-panel]').forEach((panel) => {
      const active = panel.dataset.xspTabPanel === activeTab;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  }

  function bindEvents() {
    $$('[data-xsp-tab-button]').forEach((button) => {
      button.addEventListener("click", () => {
        collectCharacters();
        switchTab(button.dataset.xspTabButton);
      });
    });

    $$('[data-xsp-tab-jump]').forEach((button) => {
      button.addEventListener("click", () => switchTab(button.dataset.xspTabJump));
    });

    $$('input[name="xsp-scan-mode"]').forEach((input) => {
      input.addEventListener("change", updateScanModeCards);
    });

    $("#xsp-add-character")?.addEventListener("click", addCharacter);
    $("#xsp-add-character-rail")?.addEventListener("click", addCharacter);
    $("#xsp-save")?.addEventListener("click", () => saveState());
    $("#xsp-scan-sources")?.addEventListener("click", scanSources);
    $("#xsp-add-table-column")?.addEventListener("click", addTableColumn);
    $("#xsp-character-search")?.addEventListener("input", (event) => {
      characterSearch = event.target.value || "";
      renderCharacterNav();
    });

    [
      "#xsp-enabled",
      "#xsp-chat-panel-enabled",
      "#xsp-compact",
      "#xsp-title",
      "#xsp-max-visible",
      "#xsp-hide-update-blocks",
      "#xsp-show-update-debug-blocks",
      "#xsp-show-pending-in-chat",
      "#xsp-hide-table-extras-in-detail",
      "#xsp-auto-apply-mode",
    ].forEach((selector) => {
      const element = $(selector);
      if (!element) return;
      element.addEventListener("input", collectSettings);
      element.addEventListener("change", collectSettings);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    updateScanModeCards();
    Promise.all([loadFieldSchema(), loadState()]);
  });
})();
