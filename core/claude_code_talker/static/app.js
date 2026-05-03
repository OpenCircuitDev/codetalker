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

    renderSessions();
    renderProfiles();
    renderDetail();
  }

  function renderSessions() {
    const list = document.getElementById("session-list");
    const count = document.getElementById("session-count");
    count.textContent = "(" + state.sessions.length + ")";
    list.innerHTML = "";
    if (state.sessions.length === 0) {
      list.innerHTML = '<li class="empty-state">No sessions yet. Start a Claude Code conversation to see it here.</li>';
      return;
    }
    for (const s of state.sessions) {
      const li = document.createElement("li");
      li.className = "session-item";
      if (s.session_id === state.selectedSessionId) li.classList.add("selected");
      const title = document.createElement("div");
      title.className = "session-item-title";
      title.textContent = s.cwd ? shortName(s.cwd) : s.session_id.slice(0, 12);
      const meta = document.createElement("div");
      meta.className = "session-item-meta";
      meta.textContent = (s.attached_profile || "—") + " · " + idleAgo(s.last_hook_at);
      li.appendChild(title);
      li.appendChild(meta);
      li.onclick = () => selectSession(s.session_id);
      list.appendChild(li);
    }
  }

  function renderProfiles() {
    const list = document.getElementById("profile-list");
    list.innerHTML = "";
    for (const p of state.profiles) {
      const li = document.createElement("li");
      li.className = "profile-item";
      li.textContent = p.name;
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
    // Pane content rendering lands in tasks 26-29; this just shows the pane.
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
