(() => {
  const API_STATE = "/mods/status-panel/app/api/state";
  const API_SUMMARY = "/mods/status-panel/app/api/summary";
  const API_SCHEMA = "/mods/status-panel/app/api/field-schema";

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
  let latestScanCandidates = [];

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function uid() {
    return `char-${Math.random().toString(16).slice(2, 10)}`;
  }

  function esc(value) {
    return String(value || "")
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

  function joinList(value) {
    return splitList(value).join(", ");
  }

  function normalizeExtra(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const result = {};
    Object.entries(value).forEach(([key, rawVal]) => {
      const name = String(key || "").trim();
      const text = Array.isArray(rawVal) ? rawVal.map((item) => String(item || "").trim()).filter(Boolean).join("、") : String(rawVal || "").trim();
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

  function normalizeSchema(schema) {
    const fallbackDetails = fieldSchema.detail_fields?.length ? fieldSchema.detail_fields : [
      { key: "group", label: "分组" },
      { key: "relationship", label: "关系" },
      { key: "short_summary", label: "摘要" },
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
    list.innerHTML = "";
    columns.forEach((column, index) => {
      const row = document.createElement("div");
      row.className = "xsp-column-row";
      row.dataset.index = String(index);
      row.innerHTML = `
        <span class="xsp-column-order">${index + 1}</span>
        <label>
          字段来源
          <input data-column-field="key" value="${esc(column.key || "")}" placeholder="name 或 extra.腿部状态" />
        </label>
        <label>
          表头名称
          <input data-column-field="label" value="${esc(column.label || column.key || "")}" placeholder="角色名 / 腿部" />
        </label>
        <div class="xsp-column-actions">
          <button type="button" class="xsp-mini-btn" data-column-action="up" ${index === 0 ? "disabled" : ""}>上移</button>
          <button type="button" class="xsp-mini-btn" data-column-action="down" ${index === columns.length - 1 ? "disabled" : ""}>下移</button>
          <button type="button" class="xsp-mini-danger" data-column-action="delete">删除</button>
        </div>
      `;
      list.appendChild(row);
    });

    list.querySelectorAll("[data-column-field]").forEach((input) => {
      input.addEventListener("input", collectFieldSchema);
      input.addEventListener("change", collectFieldSchema);
    });
    list.querySelectorAll("[data-column-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".xsp-column-row");
        const index = Number(row?.dataset?.index ?? -1);
        if (!Number.isInteger(index) || index < 0) return;
        collectFieldSchema();
        const action = button.dataset.columnAction;
        if (action === "delete") {
          fieldSchema.table_columns.splice(index, 1);
        } else if (action === "up" && index > 0) {
          [fieldSchema.table_columns[index - 1], fieldSchema.table_columns[index]] = [fieldSchema.table_columns[index], fieldSchema.table_columns[index - 1]];
        } else if (action === "down" && index < fieldSchema.table_columns.length - 1) {
          [fieldSchema.table_columns[index + 1], fieldSchema.table_columns[index]] = [fieldSchema.table_columns[index], fieldSchema.table_columns[index + 1]];
        }
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
    fieldSchema = {
      ...fieldSchema,
      table_columns: columns,
    };
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
        status.textContent = "表格列已保存";
        setTimeout(() => { status.textContent = ""; }, 1600);
      }
      return true;
    } catch {
      if (status) status.textContent = "表格列保存失败";
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
    renderSettings();
    renderCharacters();
    renderSummary();
  }

  function renderSettings() {
    $("#xsp-enabled").checked = state.settings.enabled !== false;
    $("#xsp-chat-panel-enabled").checked = state.settings.chat_panel_enabled !== false;
    $("#xsp-compact").checked = state.settings.compact !== false;
    $("#xsp-title").value = state.settings.title || "角色状态";
    $("#xsp-max-visible").value = Number(state.settings.max_visible || 8);
    $("#xsp-hide-update-blocks").checked = state.settings.hide_update_blocks !== false;
    const debugToggle = $("#xsp-show-update-debug-blocks");
    if (debugToggle) debugToggle.checked = state.settings.show_update_debug_blocks === true;
    $("#xsp-show-pending-in-chat").checked = state.settings.show_pending_in_chat !== false;
    $("#xsp-hide-table-extras-in-detail").checked = state.settings.hide_table_extras_in_detail === true;
    $("#xsp-auto-apply-mode").value = state.settings.auto_apply_mode || "safe";
  }

  function collectSettings() {
    state.settings = {
      ...state.settings,
      enabled: $("#xsp-enabled").checked,
      chat_panel_enabled: $("#xsp-chat-panel-enabled").checked,
      compact: $("#xsp-compact").checked,
      title: $("#xsp-title").value.trim() || "角色状态",
      max_visible: Math.max(1, Math.min(50, Number($("#xsp-max-visible").value || 8))),
      hide_update_blocks: $("#xsp-hide-update-blocks").checked,
      show_update_debug_blocks: $("#xsp-show-update-debug-blocks")?.checked === true,
      show_pending_in_chat: $("#xsp-show-pending-in-chat").checked,
      hide_table_extras_in_detail: $("#xsp-hide-table-extras-in-detail").checked,
      auto_apply_mode: $("#xsp-auto-apply-mode").value || "safe",
    };
  }

  function renderCharacters() {
    const list = $("#xsp-character-list");
    const template = $("#xsp-character-template");
    list.innerHTML = "";

    if (!state.characters.length) {
      const empty = document.createElement("div");
      empty.className = "xsp-empty-card";
      empty.textContent = "当前还没有角色状态。你可以新增，也可以先扫描资料后应用候选。";
      list.appendChild(empty);
      renderSummaryLocal();
      return;
    }

    state.characters.forEach((character) => {
      const node = template.content.firstElementChild.cloneNode(true);
      node.dataset.characterId = character.id || uid();

      node.querySelectorAll("[data-field]").forEach((input) => {
        const field = input.dataset.field;
        if (field === "visible") {
          input.checked = character.visible !== false;
        } else if (field === "status_effects") {
          input.value = joinList(character.status_effects);
        } else if (field === "_extra_text") {
          input.value = extraToText(character.extra || character.extras || character.custom || {});
        } else {
          input.value = character[field] || "";
        }
      });

      node.querySelector("[data-action='delete']").addEventListener("click", () => {
        state.characters = state.characters.filter((item) => String(item.id) !== String(node.dataset.characterId));
        renderCharacters();
        renderSummaryLocal();
      });

      node.addEventListener("input", () => {
        collectCharacters();
        renderSummaryLocal();
      });
      node.addEventListener("change", () => {
        collectCharacters();
        renderSummaryLocal();
      });

      list.appendChild(node);
    });

    renderSummaryLocal();
  }

  function collectCharacters() {
    state.characters = $$(".xsp-edit-card").map((card) => {
      const item = { id: card.dataset.characterId || uid() };
      card.querySelectorAll("[data-field]").forEach((input) => {
        const field = input.dataset.field;
        if (field === "visible") {
          item[field] = input.checked;
        } else if (field === "status_effects") {
          item[field] = splitList(input.value);
        } else if (field === "_extra_text") {
          item.extra = parseExtraText(input.value);
        } else {
          item[field] = input.value.trim();
        }
      });
      return item;
    });
  }

  function renderSummaryLocal() {
    const lines = [];
    const visible = state.characters.filter((item) => item.visible !== false);
    if (visible.length) lines.push("【角色状态摘要】");
    for (const item of visible) {
      const hp = item.hp_current || item.hp_max ? `HP ${item.hp_current || "?"}/${item.hp_max || "?"}` : "HP 未记录";
      const mp = item.mp_current || item.mp_max ? `MP ${item.mp_current || "?"}/${item.mp_max || "?"}` : "MP 未记录";
      const effects = splitList(item.status_effects).length ? splitList(item.status_effects).join("、") : "无明显异常";
      const parts = [
        `${item.name || "未命名角色"}：${item.alive_status || "未知"}`,
        hp,
        mp,
        item.location ? `位置：${item.location}` : "",
        item.relationship ? `关系：${item.relationship}` : "",
        `状态：${effects}`,
        item.short_summary || "",
      ].filter(Boolean);
      lines.push(parts.join("，"));
    }
    $("#xsp-summary-preview").textContent = lines.join("\n") || "暂无可见角色。";
  }

  async function renderSummary() {
    try {
      const response = await fetch(API_SUMMARY, { cache: "no-store" });
      const data = await response.json();
      $("#xsp-summary-preview").textContent = data.summary || "暂无可见角色。";
    } catch {
      renderSummaryLocal();
    }
  }

  async function saveState({ quiet = false } = {}) {
    collectSettings();
    collectCharacters();
    const status = $("#xsp-save-status");
    if (!quiet) status.textContent = "保存中...";

    const response = await fetch(API_STATE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state),
    });

    if (!response.ok) {
      status.textContent = "保存失败";
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
    renderSettings();
    renderCharacters();
    renderSummary();

    if (!quiet) {
      status.textContent = schemaSaved ? "已保存" : "角色状态已保存，表格列保存失败";
      setTimeout(() => { status.textContent = ""; }, 1800);
    }
    return true;
  }

  function addCharacter() {
    collectCharacters();
    state.characters.push({
      id: uid(),
      name: "",
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
      private_note: "",
      extra: {},
      updated_at: nowString(),
    });
    renderCharacters();
  }

  function findCharacter(candidate) {
    const id = String(candidate.id || "").trim();
    const name = String(candidate.name || "").trim();
    return state.characters.find((item) => {
      const itemId = String(item.id || "").trim();
      const itemName = String(item.name || "").trim();
      return (id && itemId === id) || (name && itemName === name);
    });
  }

  function applyCandidate(candidate) {
    collectCharacters();
    let target = findCharacter(candidate);
    if (!target) {
      target = {
        id: candidate.id || uid(),
        name: candidate.name || "未命名角色",
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
        private_note: "",
        extra: {},
      };
      state.characters.push(target);
    }

    const fields = ["name", "group", "alive_status", "hp_current", "hp_max", "mp_current", "mp_max", "location", "relationship", "short_summary"];
    fields.forEach((field) => {
      if (candidate[field]) target[field] = candidate[field];
    });
    if (candidate.extra && typeof candidate.extra === "object") {
      target.extra = { ...(target.extra || {}), ...normalizeExtra(candidate.extra) };
    }

    let effects = splitList(target.status_effects);
    if (candidate.status_effects?.length) {
      effects = splitList(candidate.status_effects);
    }
    if (candidate.effects_add?.length) {
      for (const effect of splitList(candidate.effects_add)) {
        if (!effects.includes(effect)) effects.push(effect);
      }
    }
    if (candidate.effects_remove?.length) {
      const removeSet = new Set(splitList(candidate.effects_remove));
      effects = effects.filter((effect) => !removeSet.has(effect));
    }
    target.status_effects = effects;
    target.updated_at = nowString();

    renderCharacters();
    renderSummaryLocal();
    saveState({ quiet: true });
  }

  function sourceText(candidate) {
    if (Array.isArray(candidate.sources) && candidate.sources.length) {
      return [...new Set(candidate.sources.map((item) => `${item.source}${item.kind === "status_panel_update" ? "·更新" : ""}`))].join(" / ");
    }
    return candidate.source || "未知来源";
  }

  function renderScanResults(candidates, sourceResults = []) {
    latestScanCandidates = candidates;
    const root = $("#xsp-scan-results");
    root.innerHTML = "";

    const sourceLine = document.createElement("div");
    sourceLine.className = "xsp-source-result-line";
    sourceLine.innerHTML = sourceResults.map((item) => {
      const cls = item.ok ? "is-ok" : "is-fail";
      return `<span class="${cls}">${esc(item.label)}：${item.ok ? `${item.count} 条` : "读取失败"}</span>`;
    }).join("");
    root.appendChild(sourceLine);

    if (!candidates.length) {
      const empty = document.createElement("p");
      empty.className = "xsp-muted";
      empty.textContent = "没有扫描到可用状态信息。当前版本只识别 status_panel / status_panel_update 代码块。";
      root.appendChild(empty);
      return;
    }

    for (const candidate of candidates) {
      const card = document.createElement("article");
      card.className = `xsp-candidate-card ${candidate.kind === "status_panel_update" ? "is-update" : ""}`;
      const effects = splitList(candidate.status_effects).length ? splitList(candidate.status_effects).join("、") : "未提取";
      const addEffects = splitList(candidate.effects_add).join("、");
      const removeEffects = splitList(candidate.effects_remove).join("、");
      const existing = findCharacter(candidate);
      const modeText = candidate.kind === "status_panel_update" ? "动态更新" : candidate.kind === "status_panel" ? "状态资料" : "兼容识别";

      card.innerHTML = `
        <div class="xsp-candidate-head">
          <div>
            <strong>${esc(candidate.name || "未命名角色")}</strong>
            <span class="xsp-candidate-badge">${esc(modeText)}</span>
            ${existing ? `<span class="xsp-candidate-badge is-existing">将覆盖已有角色</span>` : `<span class="xsp-candidate-badge">新角色</span>`}
          </div>
          <span>${esc(sourceText(candidate))}</span>
        </div>
        <div class="xsp-candidate-grid">
          <span>生存：${esc(candidate.alive_status || "未提取")}</span>
          <span>HP：${esc(candidate.hp_current || "?")}/${esc(candidate.hp_max || "?")}</span>
          <span>MP：${esc(candidate.mp_current || "?")}/${esc(candidate.mp_max || "?")}</span>
          <span>位置：${esc(candidate.location || "未提取")}</span>
          <span>关系：${esc(candidate.relationship || "未提取")}</span>
          <span>状态：${esc(effects)}</span>
          ${addEffects ? `<span>新增状态：${esc(addEffects)}</span>` : ""}
          ${removeEffects ? `<span>移除状态：${esc(removeEffects)}</span>` : ""}
        </div>
        ${candidate.short_summary ? `<p>${esc(candidate.short_summary)}</p>` : ""}
        <details class="xsp-raw-details">
          <summary>查看来源片段</summary>
          <pre>${esc((candidate.sources?.[0]?.raw_text || candidate.raw_text || "").slice(0, 1200))}</pre>
        </details>
        <div class="xsp-candidate-actions">
          <button type="button" class="xsp-btn xsp-btn-primary" data-apply>应用到状态栏</button>
          <button type="button" class="xsp-btn" data-ignore>忽略</button>
        </div>
      `;

      card.querySelector("[data-apply]").addEventListener("click", () => {
        applyCandidate(candidate);
        card.classList.add("is-applied");
        card.querySelector("[data-apply]").textContent = "已应用";
        card.querySelector("[data-apply]").disabled = true;
      });
      card.querySelector("[data-ignore]").addEventListener("click", () => {
        card.remove();
      });

      root.appendChild(card);
    }
  }

  function getEnabledSources() {
    return $$('[data-source-toggle]')
      .filter((input) => input.checked)
      .map((input) => input.dataset.sourceToggle);
  }

  async function scanSources() {
    const button = $("#xsp-scan-sources");
    const status = $("#xsp-scan-status");
    button.disabled = true;
    button.textContent = "扫描中...";
    status.textContent = "正在读取资料";

    try {
      const result = await window.XuqiStatusPanelExtractor.scan({ enabledSources: getEnabledSources() });
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

  document.addEventListener("DOMContentLoaded", () => {
    $("#xsp-add-character").addEventListener("click", addCharacter);
    $("#xsp-save").addEventListener("click", () => saveState());
    $("#xsp-scan-sources").addEventListener("click", scanSources);
    $("#xsp-add-table-column")?.addEventListener("click", addTableColumn);

    ["#xsp-enabled", "#xsp-chat-panel-enabled", "#xsp-compact", "#xsp-title", "#xsp-max-visible", "#xsp-hide-update-blocks", "#xsp-show-pending-in-chat", "#xsp-hide-table-extras-in-detail", "#xsp-auto-apply-mode"].forEach((selector) => {
      const element = $(selector);
      element.addEventListener("input", collectSettings);
      element.addEventListener("change", collectSettings);
    });

    Promise.all([loadFieldSchema(), loadState()]);
  });
})();
