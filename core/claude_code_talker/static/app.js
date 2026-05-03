// codetalker control panel — vanilla JS, no build step.
(function() {
  "use strict";

  const POLL_INTERVAL_MS = 2000;
  const POLL_BACKOFF_OFFLINE_MS = 10000;
  const API = "/api";

  const state = {
    sessions: [],
    profiles: [],
    selectedSessionId: null,
    selectedSessionDetail: null,  // {state, resolved_cfg}
    voicesByEngine: {},
    activeTab: "quick",
    enabled: true,
    offline: false,
    filter: 'all',  // 'all' | 'live' | 'enabled'
  };

  // ---- HTTP helpers ----

  async function api(path, opts = {}) {
    const init = Object.assign({ headers: {} }, opts);
    if (init.body && typeof init.body !== "string") {
      init.body = JSON.stringify(init.body);
      init.headers["Content-Type"] = "application/json";
    }
    const r = await fetch(API + path, init);
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`${r.status} ${path}: ${text}`);
    }
    return r.json();
  }

  // ---- Toast helper ----

  function toast(message, kind = "info") {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  // ---- Polling loop ----

  async function poll() {
    try {
      const [sessions, profiles, status] = await Promise.all([
        api("/sessions"),
        api("/profiles"),
        api("/status"),
      ]);
      state.sessions = sessions;
      state.profiles = profiles;
      state.enabled = status.enabled;
      state.providers = status.providers || ["ollama"];
      // Lazy-load voices for engines we haven't seen
      for (const eng of status.engines || []) {
        if (!state.voicesByEngine[eng]) {
          try {
            state.voicesByEngine[eng] = await api("/voices?engine=" + encodeURIComponent(eng));
          } catch (e) {
            state.voicesByEngine[eng] = [];
          }
        }
      }
      if (state.offline) {
        state.offline = false;
        toast("Daemon reconnected", "success");
      }
      if (state.selectedSessionId) {
        try {
          state.selectedSessionDetail = await api("/sessions/" + state.selectedSessionId);
        } catch (e) {
          state.selectedSessionDetail = null;
          state.selectedSessionId = null;
        }
      }
      render();
    } catch (e) {
      if (!state.offline) {
        state.offline = true;
        render();
      }
    }
    const delay = state.offline ? POLL_BACKOFF_OFFLINE_MS : POLL_INTERVAL_MS;
    setTimeout(poll, delay);
  }

  // ---- Render (placeholders for now; tabs filled in later tasks) ----

  function render() {
    document.getElementById("offline-banner").classList.toggle("hidden", !state.offline);
    const muteBtn = document.getElementById("mute-toggle");
    muteBtn.textContent = state.enabled ? "🔊" : "🔇";
    muteBtn.classList.toggle("muted", !state.enabled);

    renderCatalog();
    renderProfiles();
    renderDetail();
  }

  function renderCatalog() {
    const list = document.getElementById("session-list");
    const count = document.getElementById("session-count");
    const filtered = state.sessions.filter(s => {
      if (state.filter === 'all') return true;
      if (state.filter === 'live') return s.is_live === true;
      if (state.filter === 'enabled') return s.enabled !== false;
      return true;
    });
    count.textContent = "(" + filtered.length +
      (state.sessions.length !== filtered.length ? " of " + state.sessions.length : "") + ")";
    list.innerHTML = "";
    if (filtered.length === 0) {
      const li = document.createElement("li");
      li.className = "empty-state";
      if (state.sessions.length === 0) {
        li.innerHTML = `
          No sessions yet.<br>
          Start a Claude Code conversation, or
          <a href="#" id="install-hooks-link">install hooks</a> if not yet set up.
        `;
        list.appendChild(li);
        const link = document.getElementById("install-hooks-link");
        if (link) link.onclick = (e) => { e.preventDefault(); installHooks(); };
      } else {
        li.textContent = "No sessions match the current filter.";
        list.appendChild(li);
      }
      return;
    }
    for (const s of filtered) {
      const li = document.createElement("li");
      li.className = "session-item";
      if (s.is_live) li.classList.add("live");
      if (s.enabled === false) li.classList.add("disabled");
      if (s.session_id === state.selectedSessionId) li.classList.add("selected");
      const title = document.createElement("div");
      title.className = "session-item-title";
      title.textContent = s.display_name || s.project_slug || s.session_id.slice(0, 12);
      const meta = document.createElement("div");
      meta.className = "session-item-meta";
      meta.textContent = (s.attached_profile || "—") + " · " + idleAgo(s.last_modified);
      li.appendChild(title);
      li.appendChild(meta);
      li.onclick = () => selectSession(s.session_id);
      list.appendChild(li);
    }
  }

  async function installHooks() {
    if (!confirm("Add codetalker hooks to ~/.claude/settings.json? Existing hooks will be preserved.")) return;
    try {
      const r = await api("/install-hooks", { method: "POST" });
      toast(`Hooks installed (${r.hooks_added} added)`, "success");
    } catch (e) {
      toast("Install failed: " + e.message, "error");
    }
  }

  function renderProfiles() {
    const list = document.getElementById("profile-list");
    list.innerHTML = "";
    for (const p of state.profiles) {
      const li = document.createElement("li");
      li.className = "profile-item";
      const name = document.createElement("span");
      name.className = "profile-name";
      name.textContent = p.name;
      name.title = p.name;
      const del = document.createElement("button");
      del.className = "profile-delete";
      del.textContent = "✕";
      del.title = "Delete profile";
      del.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm("Delete profile '" + p.name + "'? Sessions using it will be detached.")) return;
        try {
          const r = await api("/profiles/" + encodeURIComponent(p.name), { method: "DELETE" });
          toast(`Deleted '${p.name}' (detached from ${r.detached_from_sessions} session${r.detached_from_sessions === 1 ? "" : "s"})`, "success");
          await poll();
        } catch (err) {
          toast("Delete failed: " + err.message, "error");
        }
      };
      li.appendChild(name);
      li.appendChild(del);
      list.appendChild(li);
    }
  }

  function renderDetail() {
    const empty = document.getElementById("detail-empty");
    const content = document.getElementById("detail-content");
    if (!state.selectedSessionDetail) {
      empty.classList.remove("hidden");
      content.classList.add("hidden");
      return;
    }
    empty.classList.add("hidden");
    content.classList.remove("hidden");

    const s = state.selectedSessionDetail.state;
    const cfg = state.selectedSessionDetail.resolved_cfg;
    document.getElementById("detail-title").textContent = shortName(s.cwd) || s.session_id;
    document.getElementById("detail-subtitle").textContent =
      "session " + s.session_id.slice(0, 12) +
      " · cwd " + (s.cwd || "(none)") +
      " · last hook " + idleAgo(s.last_hook_at);

    const pill = document.getElementById("profile-attached");
    if (s.attached_profile) {
      pill.textContent = "▼ " + s.attached_profile;
      pill.classList.remove("hidden");
      pill.onclick = () => detachProfile(s.session_id);
      pill.title = "Click to detach";
    } else {
      pill.classList.add("hidden");
    }

    const select = document.getElementById("profile-attach-select");
    select.innerHTML = '<option value="">Attach profile…</option>';
    for (const p of state.profiles) {
      if (p.name === s.attached_profile) continue;
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = p.name;
      select.appendChild(opt);
    }

    renderActiveTab(s, cfg);
  }

  function renderActiveTab(s, cfg) {
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelector(`.tab[data-tab="${state.activeTab}"]`).classList.add("active");
    const pane = document.querySelector(`.tab-pane[data-pane="${state.activeTab}"]`);
    pane.classList.add("active");
    pane.innerHTML = "";
    const renderer = TAB_RENDERERS[state.activeTab];
    if (renderer) renderer(pane, s, cfg);
  }

  // Pane renderers — populated as each tab task lands.
  const TAB_RENDERERS = {};

  TAB_RENDERERS.quick = function(pane, s, cfg) {
    const voiceCfg = cfg.voice || {};
    pane.appendChild(makeFieldSelect("Mode", "active_mode",
      ["direct", "brief", "live"], cfg.active_mode || "direct", s.session_id));
    pane.appendChild(makeFieldSelect("Voice", "voice.model",
      voicesForEngine(voiceCfg.engine || "piper"),
      voiceCfg.model || "(none)", s.session_id));
    const playRow = makeFieldRow("Sample");
    const btn = document.createElement("button");
    btn.textContent = "▶ Play sample";
    btn.onclick = () => playSample(s.session_id);
    playRow.querySelector(".field-control").appendChild(btn);
    pane.appendChild(playRow);
  };

  function voicesForEngine(engine) {
    return state.voicesByEngine[engine] || ["(loading…)"];
  }

  function makeFieldRow(label) {
    const row = document.createElement("div");
    row.className = "field";
    const lab = document.createElement("label");
    lab.textContent = label;
    const ctrl = document.createElement("div");
    ctrl.className = "field-control";
    row.appendChild(lab);
    row.appendChild(ctrl);
    return row;
  }

  function makeFieldSelect(label, keypath, options, current, sessionId) {
    const row = makeFieldRow(label);
    const sel = document.createElement("select");
    for (const o of options) {
      const opt = document.createElement("option");
      opt.value = o;
      opt.textContent = o;
      if (o === current) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.onchange = () => updateOverlayKeypath(sessionId, keypath, sel.value);
    row.querySelector(".field-control").appendChild(sel);
    return row;
  }

  async function updateOverlayKeypath(sessionId, keypath, value) {
    const partial = setNested({}, keypath, value);
    try {
      await api("/sessions/" + sessionId + "/overlay",
                { method: "PUT", body: partial });
      await poll();
    } catch (e) {
      toast("Update failed: " + e.message, "error");
    }
  }

  function setNested(obj, keypath, value) {
    const parts = keypath.split(".");
    let cur = obj;
    for (let i = 0; i < parts.length - 1; i++) {
      cur[parts[i]] = cur[parts[i]] || {};
      cur = cur[parts[i]];
    }
    cur[parts[parts.length - 1]] = value;
    return obj;
  }

  async function playSample(sessionId) {
    toast("Sample playback wires up in next task (uses a forthcoming /api/sessions/<id>/speak-sample endpoint)", "info");
  }

  const CADENCES = ["periodic", "per_tool_call", "per_cluster", "significant_only", "hybrid"];

  TAB_RENDERERS.behavior = function(pane, s, cfg) {
    const mode = cfg.active_mode || "direct";
    const liveCfg = cfg.live || {};
    pane.appendChild(makeFieldSelect("Mode", "active_mode",
      ["direct", "brief", "live"], mode, s.session_id));

    if (mode === "live") {
      pane.appendChild(makeFieldSelect("Cadence", "live.cadence",
        CADENCES, liveCfg.cadence || "periodic", s.session_id));
      pane.appendChild(makeFieldNumber("Significance threshold", "live.significance_threshold",
        liveCfg.significance_threshold ?? 0.5, 0.0, 1.0, 0.05, s.session_id));
    } else {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = "Cadence and significance threshold apply to live mode only.";
      pane.appendChild(note);
    }

    if (mode === "brief" || mode === "live") {
      pane.appendChild(makeFieldSelect("LLM Provider",
        "modes." + (mode === "live" ? "live" : "brief") + ".provider",
        providersFromStatus(),
        getProviderForMode(cfg, mode),
        s.session_id));
    }
  };

  function providersFromStatus() {
    return state.providers || ["ollama"];
  }

  function getProviderForMode(cfg, mode) {
    const modeKey = mode === "live" ? "live" : "brief";
    return ((cfg.modes || {})[modeKey] || {}).provider || "ollama";
  }

  TAB_RENDERERS.audio = function(pane, s, cfg) {
    const voiceCfg = cfg.voice || {};
    const enginesAvail = Object.keys(state.voicesByEngine);
    pane.appendChild(makeFieldSelect("Engine", "voice.engine",
      enginesAvail.length ? enginesAvail : ["piper"],
      voiceCfg.engine || "piper", s.session_id));
    pane.appendChild(makeFieldSelect("Voice", "voice.model",
      voicesForEngine(voiceCfg.engine || "piper"),
      voiceCfg.model || "(none)", s.session_id));
    pane.appendChild(makeFieldNumber("Rate", "voice.rate",
      voiceCfg.rate ?? 1.0, 0.5, 2.0, 0.05, s.session_id));
  };

  TAB_RENDERERS.advanced = function(pane, s, cfg) {
    const liveCfg = cfg.live || {};
    pane.appendChild(makeFieldNumber("Queue max depth", "live.queue_max_depth",
      liveCfg.queue_max_depth ?? 5, 1, 100, 1, s.session_id));
    pane.appendChild(makeFieldNumber("Staleness (s)", "live.staleness_seconds",
      liveCfg.staleness_seconds ?? 20, 1, 600, 1, s.session_id));
    pane.appendChild(makeFieldSelect("Code blocks", "code_blocks",
      ["stub", "speak"], cfg.code_blocks || "stub", s.session_id));
    pane.appendChild(makeFieldSelect("File paths", "paths.handling",
      ["filename", "omit"], (cfg.paths || {}).handling || "filename", s.session_id));

    const note = document.createElement("p");
    note.className = "muted";
    note.style.marginTop = "16px";
    note.textContent = "These knobs are per-session live overrides. Defaults come from your global + workspace config.";
    pane.appendChild(note);

    const resetRow = makeFieldRow("Reset overlay");
    const btn = document.createElement("button");
    btn.textContent = "Clear all overrides";
    btn.onclick = async () => {
      if (!confirm("Clear all per-session overrides? This reverts to global/workspace/profile defaults.")) return;
      const overlay = state.selectedSessionDetail.state.live_overlay;
      const paths = collectKeypaths(overlay);
      for (const path of paths) {
        try {
          await api("/sessions/" + s.session_id + "/overlay/" + encodeURIComponent(path),
                    { method: "DELETE" });
        } catch (e) {
          toast("Reset failed for " + path + ": " + e.message, "error");
        }
      }
      toast("Overlay cleared", "success");
      await poll();
    };
    resetRow.querySelector(".field-control").appendChild(btn);
    pane.appendChild(resetRow);
  };

  function collectKeypaths(obj, prefix = "") {
    const out = [];
    for (const k in obj) {
      const path = prefix ? prefix + "." + k : k;
      if (obj[k] && typeof obj[k] === "object" && !Array.isArray(obj[k])) {
        out.push(...collectKeypaths(obj[k], path));
      } else {
        out.push(path);
      }
    }
    return out;
  }

  function makeFieldNumber(label, keypath, current, min, max, step, sessionId) {
    const row = makeFieldRow(label);
    const input = document.createElement("input");
    input.type = "number";
    input.value = String(current);
    input.min = String(min);
    input.max = String(max);
    input.step = String(step);
    input.style.width = "100px";
    input.onchange = () => {
      const n = parseFloat(input.value);
      if (isNaN(n) || n < min || n > max) {
        toast(`${label} must be ${min}–${max}`, "error");
        input.value = String(current);
        return;
      }
      updateOverlayKeypath(sessionId, keypath, n);
    };
    row.querySelector(".field-control").appendChild(input);
    return row;
  }

  async function detachProfile(sessionId) {
    try {
      await api("/sessions/" + sessionId + "/profile", { method: "DELETE" });
      toast("Profile detached", "success");
      await poll();
    } catch (e) {
      toast("Detach failed: " + e.message, "error");
    }
  }

  // ---- Helpers ----

  function shortName(cwd) {
    if (!cwd) return "(no cwd)";
    const parts = cwd.replace(/\\/g, "/").split("/").filter(Boolean);
    return parts[parts.length - 1] || cwd;
  }

  function idleAgo(timestamp) {
    if (!timestamp) return "never";
    const seconds = Math.floor(Date.now() / 1000 - timestamp);
    if (seconds < 60) return seconds + "s ago";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    return Math.floor(seconds / 3600) + "h ago";
  }

  async function selectSession(sessionId) {
    state.selectedSessionId = sessionId;
    try {
      state.selectedSessionDetail = await api("/sessions/" + sessionId);
      render();
    } catch (e) {
      toast("Failed to load session: " + e.message, "error");
    }
  }

  // ---- Wire up static handlers ----

  function init() {
    document.getElementById("mute-toggle").onclick = async () => {
      try {
        await api(state.enabled ? "/mute" : "/unmute", { method: "POST" });
        await poll();
      } catch (e) {
        toast("Mute toggle failed: " + e.message, "error");
      }
    };
    document.getElementById("reconnect-btn").onclick = () => poll();
    document.querySelectorAll(".tab").forEach(t => {
      t.onclick = () => {
        state.activeTab = t.dataset.tab;
        render();
      };
    });
    document.querySelectorAll('.chip').forEach(chip => {
      chip.onclick = () => {
        state.filter = chip.dataset.filter;
        document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        render();
      };
    });
    const saveBtn = document.getElementById("save-as-profile-btn");
    const dialog = document.getElementById("save-profile-dialog");
    const nameInput = document.getElementById("save-profile-name");

    saveBtn.onclick = () => {
      if (!state.selectedSessionId) {
        toast("Select a session first", "error");
        return;
      }
      nameInput.value = "";
      dialog.showModal();
    };

    dialog.addEventListener("close", async () => {
      if (dialog.returnValue !== "save") return;
      const name = nameInput.value.trim();
      if (!/^[a-zA-Z0-9_-]{1,64}$/.test(name)) {
        toast("Invalid profile name", "error");
        return;
      }
      try {
        await api("/sessions/" + state.selectedSessionId + "/save-as-profile",
                  { method: "POST", body: { name } });
        toast("Profile saved: " + name, "success");
        await poll();
      } catch (e) {
        toast("Save failed: " + e.message, "error");
      }
    });

    document.getElementById("profile-attach-select").onchange = async (e) => {
      const name = e.target.value;
      if (!name || !state.selectedSessionId) return;
      try {
        await api("/sessions/" + state.selectedSessionId + "/attach-profile",
                  { method: "POST", body: { name } });
        toast("Profile attached: " + name, "success");
        await poll();
      } catch (err) {
        toast("Attach failed: " + err.message, "error");
      }
    };
    poll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose for later tasks to extend
  window.codetalker = { state, render, api, toast, poll };
})();
