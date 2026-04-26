(function () {
  const CLEAN_ROUTE_META = {
    chat: { title: "聊天" },
    config: { title: "配置" },
    card: { title: "角色卡" },
    memory: { title: "记忆库" },
    worldbook: { title: "世界书" },
  };

  function safeStatus(text) {
    const node = qs("statusText");
    if (node) node.textContent = text;
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

  function saveTextWithPicker(filename, content, mimeType = "text/plain") {
    if (!window.XuqiNative || typeof window.XuqiNative.saveTextFileAsync !== "function") {
      downloadText(filename, content);
      return Promise.resolve();
    }
    const requestId = createRequestId();
    return new Promise((resolve, reject) => {
      pendingNativeRequests.set(requestId, { type: "save", resolve, reject });
      try {
        window.XuqiNative.saveTextFileAsync(filename, mimeType, content, requestId);
      } catch (error) {
        pendingNativeRequests.delete(requestId);
        reject(error instanceof Error ? error : new Error("文件导出失败"));
      }
    });
  }

  renderGlobalChrome = function () {
    applyAppearance();
    const slot = getActiveSlot();
    qs("activeSlotName").textContent = slot.name;

    const slotSelect = qs("slotSelect");
    slotSelect.innerHTML = Object.entries(state.slots)
      .map(([slotId, item]) => {
        const selected = slotId === state.activeSlot ? "selected" : "";
        return `<option value="${slotId}" ${selected}>${escapeHtml(item.name)}</option>`;
      })
      .join("");

    qs("themeToggleButton").textContent = state.settings.theme === "light" ? "切到暗色" : "切到浅色";

    const routeMeta = CLEAN_ROUTE_META[state.activeRoute] || CLEAN_ROUTE_META.chat;
    qs("currentRouteTitle").textContent = routeMeta.title;
  };

  navigate = function (route) {
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
  };

  renderRoute = function (route) {
    renderGlobalChrome();
    if (route === "chat") renderChat();
    if (route === "config") renderConfig();
    if (route === "card") renderCard();
    if (route === "memory") renderMemory();
    if (route === "worldbook") renderWorldbook();
    bindDynamicEditors();
  };

  renderChat = function () {
    const slot = getActiveSlot();
    const list = qs("messageList");
    list.innerHTML = "";
    slot.messages.forEach((item) => list.appendChild(buildMessageNode(item)));
    list.scrollTop = list.scrollHeight;
    safeStatus("就绪");
  };

  exportChatHistory = async function () {
    const slot = getActiveSlot();
    const lines = slot.messages
      .map((item) => {
        const text = item.role === "assistant" ? parseAssistantReply(item.content).visible || item.content : item.content;
        const speaker = item.role === "user" ? "用户" : slot.persona.name || "角色";
        return `[${formatTime(item.createdAt)}] ${speaker}\n${text}\n`;
      })
      .join("\n");
    try {
      await saveTextWithPicker(`${safeFileName(slot.name, "slot")}_chat.txt`, lines || "暂无聊天记录");
      safeStatus("聊天记录已导出");
    } catch (error) {
      safeStatus("聊天记录导出失败");
      showModal("导出失败", error instanceof Error ? error.message : "聊天记录导出失败");
    }
  };

  exportCurrentCard = async function () {
    const slot = getActiveSlot();
    try {
      await saveTextWithPicker(
        slot.currentCard.sourceName || "role_card.json",
        JSON.stringify(slot.currentCard.raw, null, 2),
        "application/json"
      );
      safeStatus("角色卡已导出");
    } catch (error) {
      safeStatus("角色卡导出失败");
      showModal("导出失败", error instanceof Error ? error.message : "角色卡导出失败");
    }
  };

  exportState = async function () {
    try {
      await saveTextWithPicker("xuqi_mobile_state.json", JSON.stringify(state, null, 2), "application/json");
      safeStatus("全部数据已导出");
    } catch (error) {
      safeStatus("全部数据导出失败");
      showModal("导出失败", error instanceof Error ? error.message : "全部数据导出失败");
    }
  };

  bindGlobalEvents = function () {
    document.querySelectorAll("[data-nav]").forEach((button) => {
      button.addEventListener("click", () => navigate(button.dataset.nav));
    });

    qs("openDrawerButton").addEventListener("click", openDrawer);
    qs("closeDrawerButton").addEventListener("click", closeDrawer);
    qs("drawerBackdrop").addEventListener("click", (event) => {
      if (event.target === qs("drawerBackdrop")) closeDrawer();
    });

    qs("slotSelect").addEventListener("change", (event) => {
      state.activeSlot = event.target.value;
      saveState();
      renderAll();
    });

    qs("renameSlotButton").addEventListener("click", () => {
      const next = window.prompt("请输入新的存档名称：", getActiveSlot().name);
      if (!next) return;
      getActiveSlot().name = next.trim() || getActiveSlot().name;
      saveState();
      renderAll();
    });

    qs("resetSlotButton").addEventListener("click", () => {
      if (!window.confirm("确定要重置当前存档吗？")) return;
      state.slots[state.activeSlot] = createDefaultSlot(getActiveSlot().name);
      saveState();
      renderAll();
    });

    qs("themeToggleButton").addEventListener("click", () => {
      state.settings.theme = state.settings.theme === "light" ? "dark" : "light";
      saveState();
      renderAll();
    });

    qs("exportAllButton").addEventListener("click", () => void exportState());
    qs("closeModalButton").addEventListener("click", hideModal);
    qs("confirmModalButton").addEventListener("click", hideModal);
    qs("modalBackdrop").addEventListener("click", (event) => {
      if (event.target === qs("modalBackdrop")) hideModal();
    });

    qs("sendButton").addEventListener("click", () => void sendMessage());
    qs("messageInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void sendMessage();
      }
    });
    qs("endConversationButton").addEventListener("click", () => void endConversation());
    qs("exportChatButton").addEventListener("click", () => void exportChatHistory());

    qs("testConnectionButton").addEventListener("click", async () => {
      if (!state.settings.apiBaseUrl || !state.settings.model) {
        showModal("缺少配置", "请先填写 API URL 和模型名。");
        return;
      }
      safeStatus("正在测试连接...");
      try {
        const reply = await callModelAsync([{ role: "user", content: "请只回复：连接成功" }], {
          temperature: 0.1,
          timeoutSec: 30,
        });
        safeStatus("连接成功");
        showModal("连接成功", `模型回复：\n${reply}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : "请求失败";
        safeStatus("连接失败");
        showModal("连接失败", message);
      }
    });

    qs("presetSelect").addEventListener("change", () => {
      const preset = MODEL_PRESETS.find((item) => item.id === qs("presetSelect").value);
      if (preset && preset.id !== "custom") {
        qs("apiBaseUrl").value = preset.url;
      }
      saveSettingsFromForm();
    });

    [
      "apiBaseUrl",
      "apiKey",
      "modelName",
      "temperature",
      "timeoutSec",
      "historyLimit",
      "themeSelect",
      "uiOpacity",
      "backgroundOverlay",
      "backgroundImageUrl",
      "musicPresetSelect",
      "musicUrlInput",
    ].forEach((id) => {
      const node = qs(id);
      const eventName = node.tagName === "SELECT" ? "change" : "input";
      node.addEventListener(eventName, saveSettingsFromForm);
    });

    qs("backgroundFileInput").addEventListener("change", (event) => void importBackgroundImage(event));
    qs("clearBackgroundButton").addEventListener("click", () => {
      state.settings.backgroundImageUrl = "";
      saveState();
      renderAll();
      safeStatus("背景已清空");
    });

    if (qs("saveRefreshConfigButton")) {
      qs("saveRefreshConfigButton").addEventListener("click", saveAndRefreshSettings);
    }

    ["personaName", "personaGreeting", "personaPrompt"].forEach((id) => {
      qs(id).addEventListener("input", savePersonaFromForm);
    });

    if (qs("saveRefreshPersonaButton")) {
      qs("saveRefreshPersonaButton").addEventListener("click", saveAndRefreshPersona);
    }

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
      const card = normalizeRoleCard(getActiveSlot().currentCard.raw);
      card.plotStages[getNextStageKey(card.plotStages)] = blankPlotStage();
      getActiveSlot().currentCard.raw = card;
      saveState();
      renderCard();
      bindDynamicEditors();
    });

    qs("addPersonaButton").addEventListener("click", () => {
      const card = normalizeRoleCard(getActiveSlot().currentCard.raw);
      card.personas[getNextNumericKey(card.personas)] = blankPersona();
      getActiveSlot().currentCard.raw = card;
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
    qs("exportCardButton").addEventListener("click", () => void exportCurrentCard());

    qs("worldbookEnabled").addEventListener("change", updateWorldbookSettingsFromForm);
    qs("worldbookMaxEntries").addEventListener("input", updateWorldbookSettingsFromForm);
    qs("worldbookDefaultMatchMode").addEventListener("change", updateWorldbookSettingsFromForm);
    qs("worldbookIgnoreCase").addEventListener("change", updateWorldbookSettingsFromForm);
    qs("worldbookWholeWord").addEventListener("change", updateWorldbookSettingsFromForm);
    qs("addWorldbookButton").addEventListener("click", () => {
      getActiveSlot().worldbook.entries.unshift({
        title: "新词条",
        primaryTriggers: "",
        secondaryTriggers: "",
        content: "",
        priority: 100,
        matchMode: "any",
        enabled: true,
        ignoreCase: true,
        wholeWord: false,
        notes: "",
      });
      saveState();
      renderWorldbook();
      bindDynamicEditors();
    });

    qs("addMemoryButton").addEventListener("click", () => {
      const slot = getActiveSlot();
      slot.memories.unshift({
        title: "新的记忆片段",
        content: "",
        tags: ["memory-fragment"],
        notes: "",
      });
      cleanupDeletedMemories(slot);
      saveState();
      renderMemory();
      bindDynamicEditors();
    });

    qs("exportStateButton").addEventListener("click", () => void exportState());
    qs("importStateInput").addEventListener("change", (event) => void importState(event));

    qs("playMusicButton").addEventListener("click", playMusic);
    qs("pauseMusicButton").addEventListener("click", pauseMusic);
    qs("stopMusicButton").addEventListener("click", stopMusic);

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) flushActiveTypewriter();
    });
  };

  const originalSaveResultHandler = window.XuqiMobileApp.onNativeSaveResult;
  window.XuqiMobileApp.onNativeSaveResult = function (payloadJson) {
    try {
      const payload = typeof payloadJson === "string" ? JSON.parse(payloadJson) : payloadJson;
      const requestId = String(payload?.requestId || "");
      const pending = pendingNativeRequests.get(requestId);
      if (!pending) {
        if (typeof originalSaveResultHandler === "function") originalSaveResultHandler(payloadJson);
        return;
      }
      pendingNativeRequests.delete(requestId);
      if (payload.ok) {
        pending.resolve(payload.uri || "");
      } else {
        pending.reject(new Error(payload.error || "文件导出失败"));
      }
    } catch (error) {
      console.error(error);
    }
  };
})();
