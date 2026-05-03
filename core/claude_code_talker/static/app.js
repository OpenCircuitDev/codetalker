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
      const titleRow = document.createElement("div");
      titleRow.className = "session-item-row";
      const title = document.createElement("div");
      title.className = "session-item-title";
      const fullName = s.display_name || s.project_slug || s.session_id.slice(0, 12);
      title.textContent = truncateName(fullName, 22);
      title.title = fullName;
      const enableBtn = document.createElement("button");
      enableBtn.className = "session-enable-btn";
      enableBtn.textContent = s.enabled === false ? "🔇" : "🔊";
      enableBtn.title = s.enabled === false
        ? "Currently muted — click to enable narration"
        : "Currently enabled — click to mute";
      enableBtn.onclick = (e) => {
        e.stopPropagation();
        toggleSessionEnabled(s);
      };
      const renameBtn = document.createElement("button");
      renameBtn.className = "session-rename-btn";
      renameBtn.textContent = "✎";
      renameBtn.title = "Rename this session";
      renameBtn.onclick = (e) => {
        e.stopPropagation();
        renameSession(s);
      };
      titleRow.appendChild(title);
      titleRow.appendChild(enableBtn);
      titleRow.appendChild(renameBtn);
      const meta = document.createElement("div");
      meta.className = "session-item-meta";
      meta.textContent = (s.attached_profile || "—") + " · " + idleAgo(s.last_modified);
      li.appendChild(titleRow);
      li.appendChild(meta);
      li.onclick = () => selectSession(s.session_id);
      list.appendChild(li);
    }
  }

  function truncateName(name, max) {
    if (!name) return "";
    if (name.length <= max) return name;
    return name.slice(0, max - 1) + "…";
  }

  async function toggleSessionEnabled(s) {
    try {
      let payload = await api("/persistent-sessions/" + s.session_id).catch(() => null);
      if (!payload) {
        payload = {
          live_overlay: {}, attached_profile: s.attached_profile,
          enabled: true, display_name: null, last_modified: 0.0,
        };
      }
      const newEnabled = s.enabled === false;  // currently disabled → enable
      payload.enabled = newEnabled;
      await api("/persistent-sessions/" + s.session_id, { method: "PUT", body: payload });
      toast(newEnabled ? "Session enabled" : "Session muted", "success");
      await poll();
    } catch (e) {
      toast("Toggle failed: " + e.message, "error");
    }
  }

  async function renameSession(s) {
    const current = (s.display_name && s.display_name !== s.project_slug) ? s.display_name : "";
    const next = prompt("Rename session:", current);
    if (next === null) return;  // cancelled
    const trimmed = next.trim();
    try {
      let payload = await api("/persistent-sessions/" + s.session_id).catch(() => null);
      if (!payload) {
        payload = {
          live_overlay: {},
          attached_profile: s.attached_profile,
          enabled: true,
          display_name: null,
          last_modified: 0.0,
        };
      }
      payload.display_name = trimmed || null;
      await api("/persistent-sessions/" + s.session_id, { method: "PUT", body: payload });
      toast(trimmed ? "Renamed: " + trimmed : "Name cleared", "success");
      await poll();
    } catch (e) {
      toast("Rename failed: " + e.message, "error");
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

    // Per-session Enable/Disable toggle
    let toggleBtn = document.getElementById("session-toggle");
    if (!toggleBtn) {
      toggleBtn = document.createElement("button");
      toggleBtn.id = "session-toggle";
      const selectEl = document.getElementById("profile-attach-select");
      selectEl.parentNode.insertBefore(toggleBtn, selectEl);
    }
    const sessionInList = state.sessions.find(x => x.session_id === s.session_id);
    const isDisabled = sessionInList && sessionInList.enabled === false;
    toggleBtn.textContent = isDisabled ? "🔇 Enable" : "🔊 Disable";
    toggleBtn.title = isDisabled
      ? "Currently disabled — click to enable narration for this session"
      : "Currently enabled — click to mute narration for this session";
    toggleBtn.onclick = async () => {
      try {
        let payload = await api("/persistent-sessions/" + s.session_id).catch(() => null);
        if (!payload) {
          payload = {
            live_overlay: {},
            attached_profile: s.attached_profile,
            enabled: true,
            display_name: null,
            last_modified: 0.0,
          };
        }
        payload.enabled = isDisabled ? true : false;
        await api("/persistent-sessions/" + s.session_id, { method: "PUT", body: payload });
        toast(payload.enabled ? "Session enabled" : "Session disabled", "success");
        await poll();
      } catch (e) {
        toast("Toggle failed: " + e.message, "error");
      }
    };

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

  TAB_RENDERERS.teacher = function(pane, s, cfg) {
    const t = (cfg.teacher_mode || {});
    pane.innerHTML = `
      <p class="muted">Reshape narration for the listener. Per-session overrides the global setting.</p>
      <label class="checkbox-row"><input type="checkbox" id="t-enabled" ${t.enabled ? 'checked' : ''}> Enable teacher mode</label>
      <label>Depth (1=expert ↔ 5=full beginner): <span id="t-depth-display">${t.depth_level || 3}</span></label>
      <input type="range" id="t-depth" min="1" max="5" step="1" value="${t.depth_level || 3}">
      <label class="checkbox-row"><input type="checkbox" id="t-substitution" ${t.substitution ? 'checked' : ''}> Substitute jargon</label>
      <label class="checkbox-row"><input type="checkbox" id="t-glossary" ${t.glossary ? 'checked' : ''}> Inline glossary</label>
      <label class="checkbox-row"><input type="checkbox" id="t-reframe" ${t.reframe ? 'checked' : ''}> Reframe as teaching moments</label>
    `;
    const persistTeacher = async () => {
      const overlay = {
        teacher_mode: {
          enabled: document.getElementById('t-enabled').checked,
          depth_level: parseInt(document.getElementById('t-depth').value, 10),
          substitution: document.getElementById('t-substitution').checked,
          glossary: document.getElementById('t-glossary').checked,
          reframe: document.getElementById('t-reframe').checked,
        }
      };
      try {
        await api("/sessions/" + s.session_id + "/overlay",
                  { method: "PUT", body: overlay }).catch(() => {});
        let payload = await api("/persistent-sessions/" + s.session_id).catch(() => null);
        if (!payload) {
          payload = { live_overlay: {}, attached_profile: null, enabled: true, display_name: null, last_modified: 0.0 };
        }
        _mergeNested(payload.live_overlay, overlay);
        await api("/persistent-sessions/" + s.session_id, { method: "PUT", body: payload });
        toast("Teacher settings saved", "success");
        await poll();
      } catch (e) { toast("Save failed: " + e.message, "error"); }
    };
    pane.querySelectorAll('input').forEach(el => {
      el.onchange = persistTeacher;
      if (el.id === 't-depth') {
        el.oninput = () => { document.getElementById('t-depth-display').textContent = el.value; };
      }
    });
  };

  TAB_RENDERERS.chat = function(pane, s, cfg) {
    pane.innerHTML = `
      <p class="muted">Ask questions about this session. Live narrations from this session also stream into this transcript.</p>
      <div class="chat-pane">
        <div class="chat-history" id="chat-history"></div>
        <div class="chat-input-row">
          <input type="text" id="chat-input" placeholder="Ask about this session...">
          <label class="checkbox-row"><input type="checkbox" id="chat-narrate" checked> Narrate</label>
          <button id="chat-send" class="primary-btn">Send</button>
        </div>
        <div class="muted" style="font-size:11px;margin-top:6px;">
          Provider: <span id="chat-provider-info">…</span>
        </div>
      </div>
    `;
    const history = pane.querySelector('#chat-history');
    const input = pane.querySelector('#chat-input');
    // Show what provider chat will use
    api("/status").then(st => {
      const liveProv = (cfg.modes?.live?.provider) || (st.providers?.[0]) || 'unknown';
      pane.querySelector('#chat-provider-info').textContent = liveProv;
    }).catch(() => {});

    // Load recent narrations for this session (so the chat panel shows the
    // same audio history the user has been hearing — Phase 11 audit log).
    const renderNarrations = async () => {
      try {
        const entries = await api("/narration-log?limit=50&session_id=" + encodeURIComponent(s.session_id));
        for (const e of entries) {
          const div = document.createElement('div');
          div.className = 'chat-message narration';
          const ts = new Date((e.timestamp || 0) * 1000).toLocaleTimeString();
          div.innerHTML = `<div class="chat-msg-meta">🔊 narrated · ${ts}</div><div>${escapeHtml(e.text || '')}</div>`;
          history.appendChild(div);
        }
        history.scrollTop = history.scrollHeight;
      } catch (e) { /* silent */ }
    };
    renderNarrations();

    const send = async () => {
      const q = input.value.trim();
      if (!q) return;
      const userMsg = document.createElement('div');
      userMsg.className = 'chat-message user';
      userMsg.textContent = q;
      history.appendChild(userMsg);
      input.value = '';
      const pending = document.createElement('div');
      pending.className = 'chat-message assistant';
      pending.textContent = '…';
      history.appendChild(pending);
      history.scrollTop = history.scrollHeight;
      try {
        const narrate = pane.querySelector('#chat-narrate').checked;
        const r = await api("/sessions/" + s.session_id + "/chat",
                            { method: "POST", body: { question: q, narrate } });
        pending.textContent = r.answer || '(no response)';
        if (narrate && r.narrated) {
          pending.innerHTML += ' <span class="muted" style="font-size:10px;">🔊 narrated</span>';
        }
      } catch (e) {
        pending.textContent = 'Error: ' + e.message;
      }
      history.scrollTop = history.scrollHeight;
    };
    pane.querySelector('#chat-send').onclick = send;
    input.onkeydown = (e) => { if (e.key === 'Enter') send(); };
  };

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
      // 1. Update live overlay (only meaningful if session is currently live)
      await api("/sessions/" + sessionId + "/overlay",
                { method: "PUT", body: partial }).catch(() => {});
      // 2. Persist for next time the session fires hooks
      let payload = await api("/persistent-sessions/" + sessionId).catch(() => null);
      if (!payload) {
        payload = {
          live_overlay: {},
          attached_profile: null,
          enabled: true,
          display_name: null,
          last_modified: 0.0,
        };
      }
      _mergeNested(payload.live_overlay, partial);
      await api("/persistent-sessions/" + sessionId, { method: "PUT", body: payload });
      await poll();
    } catch (e) {
      toast("Save failed: " + e.message, "error");
    }
  }

  // ---- Settings dialog ----

  async function openSettings() {
    const dlg = document.getElementById("settings-dialog");
    if (!dlg) return;
    // Wire tab switching
    dlg.querySelectorAll('.settings-tab').forEach(tab => {
      tab.onclick = () => {
        dlg.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
        dlg.querySelectorAll('.settings-pane').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        dlg.querySelector(`.settings-pane[data-spane="${tab.dataset.stab}"]`).classList.add('active');
        loadSettingsPane(tab.dataset.stab);
      };
    });
    await loadSettingsPane('keys');
    dlg.showModal();
  }

  async function loadSettingsPane(name) {
    if (name === 'keys') return loadKeysPane();
    if (name === 'provider') return loadProviderPane();
    if (name === 'teacher') return loadTeacherPane();
    if (name === 'usage') return loadUsagePane();
    if (name === 'cache') return loadCachePane();
    if (name === 'audit') return loadAuditPane();
  }

  async function loadKeysPane() {
    try {
      const data = await api("/secrets");
      for (const row of document.querySelectorAll('.key-row')) {
        const k = row.dataset.keyname;
        const info = data[k] || { set: false, redacted: null, source: null };
        const input = row.querySelector('input');
        input.placeholder = info.set ? `${info.redacted}` : 'not set';
        input.value = '';
        const src = row.querySelector('.key-source');
        src.textContent = info.set ? `(${info.source})` : '';
        row.querySelector('.key-clear').onclick = async () => {
          if (!confirm(`Clear ${k}? Daemon restart required.`)) return;
          const body = {}; body[k] = '';
          await api("/secrets", { method: "PUT", body });
          toast("Cleared " + k, "success");
          await loadKeysPane();
        };
      }
      document.getElementById('save-keys-btn').onclick = async () => {
        const body = {};
        for (const row of document.querySelectorAll('.key-row')) {
          const v = row.querySelector('input').value.trim();
          if (v) body[row.dataset.keyname] = v;
        }
        if (Object.keys(body).length === 0) {
          toast("No keys to save", "info");
          return;
        }
        try {
          const r = await api("/secrets", { method: "PUT", body: body });
          toast("Saved " + Object.keys(body).length + " key(s) — " + (r.note || ""), "success");
          await loadKeysPane();
        } catch (e) { toast("Save failed: " + e.message, "error"); }
      };
    } catch (e) { toast("Load keys failed: " + e.message, "error"); }
  }

  async function loadProviderPane() {
    try {
      const data = await api("/llm-models");
      const provSel = document.getElementById('provider-select');
      provSel.innerHTML = '';
      for (const provider of Object.keys(data)) {
        const opt = document.createElement('option');
        opt.value = provider;
        const av = data[provider].available ? '' : ' (key not set)';
        opt.textContent = provider + av;
        provSel.appendChild(opt);
      }
      const fillModels = () => {
        const provider = provSel.value;
        const modelSel = document.getElementById('model-select');
        modelSel.innerHTML = '';
        for (const m of (data[provider]?.models || [])) {
          const opt = document.createElement('option');
          opt.value = m.id;
          opt.textContent = m.label + (m.tier ? ` [${m.tier}]` : '');
          if (m.id === data[provider].default) opt.selected = true;
          modelSel.appendChild(opt);
        }
        document.getElementById('model-tier-hint').textContent =
          'Default: ' + (data[provider]?.default || '(unset)');
      };
      provSel.onchange = fillModels;
      fillModels();
      document.getElementById('save-llm-default-btn').onclick = async () => {
        const provider = provSel.value;
        const model = document.getElementById('model-select').value;
        if (!provider || !model) {
          toast("Pick a provider and model first", "error");
          return;
        }
        try {
          await api("/llm-models/default", { method: "PUT", body: { provider, model } });
          toast(`Default set: ${provider} → ${model}`, "success");
          await loadProviderPane();
        } catch (e) { toast("Save failed: " + e.message, "error"); }
      };
      document.getElementById('refresh-openrouter-btn').onclick = async () => {
        try {
          const r = await api("/llm-models/openrouter/refresh", { method: "POST" });
          toast(`Refreshed ${r.model_count} OpenRouter models`, "success");
          await loadProviderPane();
        } catch (e) { toast("Refresh failed: " + e.message, "error"); }
      };
    } catch (e) { toast("Load providers failed: " + e.message, "error"); }
  }

  async function loadTeacherPane() {
    try {
      const t = await api("/teacher");
      document.getElementById('teacher-enabled').checked = !!t.enabled;
      document.getElementById('teacher-depth').value = t.depth_level || 3;
      document.getElementById('teacher-depth-display').textContent = t.depth_level || 3;
      document.getElementById('teacher-substitution').checked = !!t.substitution;
      document.getElementById('teacher-glossary').checked = !!t.glossary;
      document.getElementById('teacher-reframe').checked = !!t.reframe;
      document.getElementById('teacher-depth').oninput = (e) => {
        document.getElementById('teacher-depth-display').textContent = e.target.value;
      };
      document.getElementById('save-teacher-btn').onclick = async () => {
        const body = {
          enabled: document.getElementById('teacher-enabled').checked,
          depth_level: parseInt(document.getElementById('teacher-depth').value, 10),
          substitution: document.getElementById('teacher-substitution').checked,
          glossary: document.getElementById('teacher-glossary').checked,
          reframe: document.getElementById('teacher-reframe').checked,
        };
        try {
          await api("/teacher", { method: "PUT", body });
          toast("Teacher mode saved", "success");
        } catch (e) { toast("Save failed: " + e.message, "error"); }
      };
    } catch (e) { toast("Load teacher failed: " + e.message, "error"); }
  }

  async function loadUsagePane() {
    try {
      const r = await api("/usage");
      const el = document.getElementById('usage-summary');
      el.innerHTML = `
        <div class="usage-row"><span>Total cost</span><span>$${(r.total_cost_usd || 0).toFixed(4)}</span></div>
        <div class="usage-row"><span>Total tokens</span><span>${r.total_tokens || 0}</span></div>
        <div class="usage-row"><span>Events tracked</span><span>${r.event_count || 0}</span></div>
        <h4>By session</h4>
        ${Object.entries(r.by_session || {}).map(([sid, v]) => `<div class="usage-row"><span>${sid.slice(0,12)}</span><span>$${v.cost.toFixed(4)} · ${v.tokens} tok</span></div>`).join('') || '<p class="muted">No usage yet</p>'}
        <h4>By model</h4>
        ${Object.entries(r.by_model || {}).map(([m, v]) => `<div class="usage-row"><span>${m}</span><span>$${v.cost.toFixed(4)} · ${v.tokens} tok</span></div>`).join('') || ''}
      `;
    } catch (e) { toast("Load usage failed: " + e.message, "error"); }
  }

  async function loadCachePane() {
    try {
      const r = await api("/tts-cache");
      const el = document.getElementById('cache-stats');
      el.innerHTML = `
        <div class="cache-row"><span>Entries</span><span>${r.entries || 0}</span></div>
        <div class="cache-row"><span>Bytes</span><span>${(r.bytes || 0).toLocaleString()} / ${(r.max_bytes || 0).toLocaleString()}</span></div>
        <div class="cache-row"><span>Hits</span><span>${r.hits || 0}</span></div>
        <div class="cache-row"><span>Misses</span><span>${r.misses || 0}</span></div>
        <div class="cache-row"><span>Hit ratio</span><span>${((r.hit_ratio || 0) * 100).toFixed(1)}%</span></div>
      `;
      document.getElementById('clear-cache-btn').onclick = async () => {
        if (!confirm("Clear TTS cache?")) return;
        const r = await api("/tts-cache", { method: "DELETE" });
        toast(`Cleared ${r.deleted} cached entries`, "success");
        await loadCachePane();
      };
    } catch (e) { toast("Load cache failed: " + e.message, "error"); }
  }

  async function loadAuditPane() {
    try {
      const entries = await api("/narration-log?limit=100");
      const ul = document.getElementById('audit-list');
      ul.innerHTML = '';
      for (const e of entries.slice().reverse()) {
        const li = document.createElement('li');
        const ts = new Date((e.timestamp || 0) * 1000).toLocaleString();
        li.innerHTML = `<div>${escapeHtml(e.text || '')}</div><div class="meta">${ts} · ${e.session_id || '?'} · ${e.engine || '?'}/${e.voice || '?'}</div>`;
        ul.appendChild(li);
      }
      if (entries.length === 0) ul.innerHTML = '<li class="muted">Audit log is empty.</li>';
      document.getElementById('reload-audit-btn').onclick = loadAuditPane;
    } catch (e) { toast("Load audit failed: " + e.message, "error"); }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  }

  function _mergeNested(target, partial) {
    for (const k in partial) {
      if (partial[k] && typeof partial[k] === 'object' && !Array.isArray(partial[k])) {
        if (!target[k] || typeof target[k] !== 'object') target[k] = {};
        _mergeNested(target[k], partial[k]);
      } else {
        target[k] = partial[k];
      }
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
    document.getElementById("settings-btn").onclick = () => openSettings();
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
