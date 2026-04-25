(() => {
  const scriptUrl = new URL(document.currentScript?.src || "/mods/tts-studio/app/static/chat-voice.js", window.location.origin);
  const modBasePath = scriptUrl.pathname.replace(/\/static\/chat-voice\.js$/, "") || "/mods/tts-studio/app";
  const apiBase = `${modBasePath}/api`;
  const messageSelector = ".message.assistant .bubble-wrap, .message.system .bubble-wrap";
  const playbackByButton = new WeakMap();

  const icons = {
    play: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path fill="currentColor" d="M8.1 5.4c0-.9 1-1.5 1.8-1l9.2 5.6c.8.5.8 1.6 0 2.1l-9.2 5.6c-.8.5-1.8-.1-1.8-1V5.4Z"/>
      </svg>`,
    pause: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path fill="currentColor" d="M7.2 5.2c0-.7.5-1.2 1.2-1.2h1.8c.7 0 1.2.5 1.2 1.2v13.6c0 .7-.5 1.2-1.2 1.2H8.4c-.7 0-1.2-.5-1.2-1.2V5.2Zm5.4 0c0-.7.5-1.2 1.2-1.2h1.8c.7 0 1.2.5 1.2 1.2v13.6c0 .7-.5 1.2-1.2 1.2h-1.8c-.7 0-1.2-.5-1.2-1.2V5.2Z"/>
      </svg>`,
    loading: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path fill="currentColor" d="M12 3a9 9 0 1 0 9 9h-2.2a6.8 6.8 0 1 1-2-4.8L14.4 9.6H21V3l-2.6 2.6A9 9 0 0 0 12 3Z"/>
      </svg>`,
  };

  let activeButton = null;
  let activeAudio = null;

  function buildApiUrl(path) {
    if (!path) return "";
    if (/^https?:\/\//i.test(path)) return path;
    return `${modBasePath}${path.startsWith("/") ? path : `/${path}`}`;
  }

  async function fetchJson(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "";
      throw new Error(detail || `TTS 请求失败 (${response.status})`);
    }
    return data;
  }

  function compactTtsText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function findTtsDelimiter(value, start = 0) {
    const text = String(value || "");
    for (let index = start; index < text.length; index += 1) {
      const char = text[index];
      if (char === ":" || char === "：") return index;
    }
    return -1;
  }

  function parseTtsVoiceFields(payload) {
    const text = String(payload || "");
    const first = findTtsDelimiter(text, 0);
    if (first < 0) return null;
    const second = findTtsDelimiter(text, first + 1);
    if (second < 0) return null;
    const speech = compactTtsText(text.slice(second + 1));
    return speech || null;
  }

  function extractTtsVoiceSpeech(rawText) {
    const text = String(rawText || "");
    const pattern = /[\[【]TTSVoice[:：]([\s\S]*?)[\]】]/g;
    const results = [];
    let match;
    while ((match = pattern.exec(text)) !== null) {
      const speech = parseTtsVoiceFields(match[1]);
      if (speech) results.push(speech);
    }
    return results.join("\n");
  }

  function getRawMessageText(wrap) {
    const bubble = wrap?.querySelector(".bubble");
    if (!bubble) return "";
    const body = bubble.querySelector(".bubble-body");
    if (body) {
      return body.dataset.ttsRaw || bubble.dataset.ttsRaw || body.textContent || "";
    }
    const clone = bubble.cloneNode(true);
    clone.querySelectorAll(".bubble-think").forEach((node) => node.remove());
    return clone.textContent || "";
  }

  function collectRenderedTtsSpeech(wrap) {
    const bubble = wrap?.querySelector(".bubble");
    const body = bubble?.querySelector(".bubble-body");
    const fromBody = compactTtsText(body?.dataset?.ttsSpeech || "");
    if (fromBody) return fromBody;

    const fromBubble = compactTtsText(bubble?.dataset?.ttsSpeech || "");
    if (fromBubble) return fromBubble;

    const cards = body ? [...body.querySelectorAll(".tts-voice-card[data-tts-text]")] : [];
    const fromCards = cards
      .map((card) => compactTtsText(card.dataset.ttsText || ""))
      .filter(Boolean)
      .join("\n");
    return compactTtsText(fromCards);
  }

  function getMessageText(wrap) {
    // Prefer the hidden speech channel written by templates/index.html.
    const preparedSpeech = collectRenderedTtsSpeech(wrap);
    if (preparedSpeech) {
      return preparedSpeech;
    }

    const rawText = getRawMessageText(wrap);
    const ttsVoiceSpeech = compactTtsText(extractTtsVoiceSpeech(rawText));
    if (ttsVoiceSpeech) {
      return ttsVoiceSpeech;
    }

    // Strict mode: do not fall back to visible body text, or narration will be read.
    return "";
  }

  function getPlayback(button) {
    let state = playbackByButton.get(button);
    if (!state) {
      state = { audio: null, text: "", loading: false };
      playbackByButton.set(button, state);
    }
    return state;
  }

  function setButtonState(button, state = "ready", title = "") {
    const stateName = state || "ready";
    button.classList.remove("is-loading", "is-playing", "is-paused", "has-error");
    if (stateName === "loading") button.classList.add("is-loading");
    if (stateName === "playing") button.classList.add("is-playing");
    if (stateName === "paused") button.classList.add("is-paused");
    if (stateName === "error") button.classList.add("has-error");

    button.dataset.ttsState = stateName;
    button.disabled = stateName === "loading";
    button.innerHTML = stateName === "playing" ? icons.pause : stateName === "loading" ? icons.loading : icons.play;

    const fallbackTitle = stateName === "playing"
      ? "暂停播放"
      : stateName === "paused"
        ? "继续播放"
        : stateName === "loading"
          ? "正在生成语音"
          : "播放这条回复";
    button.title = title || fallbackTitle;
    button.setAttribute("aria-label", button.title);
  }

  function releaseAudioUrl(audio) {
    if (!audio?.src?.startsWith("blob:")) return;
    URL.revokeObjectURL(audio.src);
  }

  function pauseActivePlayback(nextButton = null) {
    if (!activeAudio || activeButton === nextButton) return;
    const previousButton = activeButton;
    const previousAudio = activeAudio;
    previousAudio.pause();
    if (previousButton) {
      setButtonState(previousButton, "paused", "继续播放");
    }
    activeButton = null;
    activeAudio = null;
  }

  function resetPlayback(button) {
    const state = getPlayback(button);
    if (state.audio) {
      state.audio.pause();
      releaseAudioUrl(state.audio);
      state.audio.src = "";
    }
    state.audio = null;
    state.text = "";
    state.loading = false;
    if (activeButton === button) {
      activeButton = null;
      activeAudio = null;
    }
    setButtonState(button, "ready", "播放这条回复");
  }

  async function createAudioForText(text, button, state) {
    const settingsData = await fetchJson("/settings", { cache: "no-store" });
    const voiceId = settingsData.settings?.active_voice_id || "";
    const data = await fetchJson("/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice_id: voiceId }),
    });
    if (!data.item?.url) {
      throw new Error("TTS 没有返回音频");
    }

    const audio = new Audio(buildApiUrl(data.item.url));
    state.audio = audio;
    state.text = text;

    audio.addEventListener("play", () => {
      activeButton = button;
      activeAudio = audio;
      setButtonState(button, "playing", "暂停播放");
    });

    audio.addEventListener("pause", () => {
      if (audio.ended) return;
      if (activeButton === button && activeAudio === audio) {
        setButtonState(button, "paused", "继续播放");
      }
    });

    audio.addEventListener("ended", () => {
      audio.currentTime = 0;
      if (activeButton === button && activeAudio === audio) {
        activeButton = null;
        activeAudio = null;
      }
      setButtonState(button, "ready", "重新播放这条回复");
    });

    audio.addEventListener("error", () => {
      if (state.audio === audio) {
        state.audio = null;
        state.text = "";
      }
      if (activeButton === button && activeAudio === audio) {
        activeButton = null;
        activeAudio = null;
      }
      setButtonState(button, "error", "音频播放失败");
      setTimeout(() => setButtonState(button, "ready", "播放这条回复"), 1600);
    });

    return audio;
  }

  async function playAudio(button, audio) {
    pauseActivePlayback(button);
    activeButton = button;
    activeAudio = audio;
    setButtonState(button, "playing", "暂停播放");
    await audio.play();
  }

  async function handleSpeak(button) {
    const state = getPlayback(button);
    if (state.loading) return;

    const wrap = button.closest(".bubble-wrap");
    const text = getMessageText(wrap);
    if (!text) {
      setButtonState(button, "error", "这条回复没有可播放文本");
      setTimeout(() => setButtonState(button, "ready", "播放这条回复"), 1400);
      return;
    }

    if (state.audio && state.text !== text) {
      resetPlayback(button);
    }

    if (state.audio) {
      if (activeButton === button && !state.audio.paused) {
        state.audio.pause();
        if (activeAudio === state.audio) {
          activeButton = null;
          activeAudio = null;
        }
        setButtonState(button, "paused", "继续播放");
        return;
      }
      try {
        await playAudio(button, state.audio);
      } catch (error) {
        setButtonState(button, "paused", error.message || "点击后继续播放");
      }
      return;
    }

    pauseActivePlayback(button);
    state.loading = true;
    setButtonState(button, "loading", "正在生成语音");

    try {
      const audio = await createAudioForText(text, button, state);
      await playAudio(button, audio);
    } catch (error) {
      state.audio = null;
      state.text = "";
      console.warn("TTS Studio playback failed:", error);
      setButtonState(button, "error", error.message || "播放失败");
      setTimeout(() => setButtonState(button, "ready", "播放这条回复"), 6000);
    } finally {
      state.loading = false;
    }
  }

  function createSpeakButton() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tts-chat-speak";
    setButtonState(button, "ready", "播放这条回复");
    button.addEventListener("click", () => {
      handleSpeak(button);
    });
    return button;
  }

  function hydrateMessage(wrap) {
    if (!wrap || wrap.querySelector(".tts-chat-speak")) return;
    const actions = document.createElement("div");
    actions.className = "tts-chat-actions";
    actions.appendChild(createSpeakButton());
    wrap.appendChild(actions);
  }

  function hydrateAll(root = document) {
    root.querySelectorAll(messageSelector).forEach(hydrateMessage);
  }

  function start() {
    hydrateAll();
    const messages = document.getElementById("messages");
    if (!messages) return;
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof HTMLElement)) return;
          if (node.matches?.(messageSelector)) {
            hydrateMessage(node);
          }
          hydrateAll(node);
        });
      }
    });
    observer.observe(messages, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
