# Phase 6 Smoke Test Checklist

Manual verification for the VS Code extension. The agentic execution
compile-checked all TypeScript and packaged the VSIX, but it could not
launch a VS Code window or click on UI. Walk this checklist once after
install to confirm the extension behaves end-to-end.

---

## 0. Pre-flight (one-time)

- [ ] Python daemon installable: `pip install -e core/`
- [ ] Daemon starts manually: `claude-code-talker serve` runs without error and prints `endpoint: http://127.0.0.1:17832/sse`
- [ ] Daemon shuts down cleanly: in another terminal, `claude-code-talker stop` reports `shutdown signal sent`, and the serve process exits
- [ ] At least one voice installed (`~/.claude/scripts/piper/voices/*.onnx` or any cloud engine env var set)

---

## 1. Install the extension

```powershell
cd c:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker
code --install-extension extension/claude-code-talker-vscode-0.1.0.vsix
```

- [ ] Install completes with `Extension 'claude-code-talker-vscode-0.1.0.vsix' was successfully installed.`
- [ ] In VS Code: `Extensions` view → "Claude Code Talker" appears as enabled

If you'd rather iterate on source: open `extension/` in VS Code, press F5 to launch a dev host. The rest of the checklist applies the same way.

---

## 2. Activation + status bar

Open any VS Code window with `autoSpawnDaemon: true` (default).

- [ ] Bottom-right status bar shows one of:
  - `🔊 TTS direct` (or `brief` / `live`) — daemon online, unmuted
  - `🔇 TTS off` — daemon online, muted
  - `⚠ TTS offline` — daemon unreachable (note: VS Code icon font renders the `$(...)` codicons; the actual visual is a small icon, not the literal `$(unmute)` text)
- [ ] No error toast on activation. (One warning toast `Claude TTS daemon not running` is acceptable on the *very first* activation if auto-spawn fired but the daemon needed >1.5s to bind — refresh the window once.)
- [ ] Hovering the status bar shows a tooltip with the full `tts_status` string (`mode=…, enabled, engines=[…], providers=[…]`)

---

## 3. Status bar interaction

- [ ] Click the status bar item once — text flips between `🔊 TTS <mode>` and `🔇 TTS off` within ~2 seconds (one poll cycle)
- [ ] Click again — flips back

If the status bar shows `⚠ TTS offline`, the auto-spawn didn't catch. Open a terminal and run `claude-code-talker serve` manually, then run `Claude TTS: Restart Daemon` from the palette.

---

## 4. Command Palette (`Ctrl+Shift+P`)

Type "Claude TTS" and confirm all 10 commands are listed:

- [ ] `Claude TTS: Toggle Mute`
- [ ] `Claude TTS: Change Mode`
- [ ] `Claude TTS: Change Voice`
- [ ] `Claude TTS: Change Cadence (Live Mode)`
- [ ] `Claude TTS: Change LLM Provider`
- [ ] `Claude TTS: Change Rate`
- [ ] `Claude TTS: Edit Workspace Config`
- [ ] `Claude TTS: Restart Daemon`
- [ ] `Claude TTS: View Daemon Log`
- [ ] `Claude TTS: Run Setup Wizard`

---

## 5. Each command end-to-end

### Toggle Mute
- [ ] Status bar text updates within 2s

### Change Mode
- [ ] Quick Pick shows `direct` / `brief` / `live` with descriptions
- [ ] Picking `live` triggers a small toast `Claude TTS mode: live`
- [ ] Status bar updates to `🔊 TTS live` within 2s
- [ ] Switch back to `direct`

### Change Voice
- [ ] Quick Pick shows installed voices (Piper voice slugs, plus any cloud voices the daemon knows about)
- [ ] Picking a voice triggers `tts_speak` — you hear the voice say "This is the ⟨name⟩ voice."
- [ ] If no voices installed, a warning toast appears

### Change Cadence (Live Mode)
- [ ] Quick Pick shows 5 strategies (periodic / per_tool_call / per_cluster / significant_only / hybrid) with descriptions
- [ ] Picking one shows an info toast pointing you at `Edit Workspace Config` (this command is V1; the actual write goes through the editor)

### Change LLM Provider
- [ ] Quick Pick shows the providers the daemon currently knows about (e.g., `ollama`, `anthropic`, `openrouter`)
- [ ] Picking shows an info toast pointing at `Edit Workspace Config`

### Change Rate
- [ ] InputBox prefilled with `1.05`
- [ ] Entering `0.4` shows the validation error "must be between 0.5 and 2.0"
- [ ] Entering `1.2` accepts and shows an info toast

### Edit Workspace Config (the big one)
- [ ] Walks through a sequence of Quick Picks: mode → voice → rate → (prose only if direct/brief) → synopsis → (cadence only if live) → code blocks → file paths → Save?
- [ ] Picking `yes` writes `<workspace>/.claude/tts_workspace.yaml`
- [ ] Open that file: it contains the values you just picked, in YAML
- [ ] After save, run `Claude TTS: Restart Daemon` — status bar reflects the new mode within ~2s

### Restart Daemon
- [ ] Status bar briefly shows `⚠ TTS offline`, then returns to `🔊 TTS <mode>` within ~3s
- [ ] Info toast `Claude TTS daemon restarted`

### View Daemon Log
- [ ] Opens `~/.claude/scripts/codetalker.log` in a new editor tab
- [ ] If no log exists yet, an error toast tells you the path

### Run Setup Wizard
- [ ] A new integrated terminal named "Claude TTS Setup" opens
- [ ] `claude-code-talker-setup` runs in it, printing the wizard sections (setup → daemon → modes → LLM providers → voice cloning → hook integration)

---

## 6. Settings round-trip

Open VS Code settings (`Ctrl+,`), search "Claude TTS":

- [ ] All 4 settings appear: `daemonHost`, `daemonPort`, `statusBarPollIntervalMs`, `autoSpawnDaemon`
- [ ] Change `statusBarPollIntervalMs` to `5000`. Reload the window. Status bar refresh feels noticeably slower (~5s)
- [ ] Set `autoSpawnDaemon` to `false`. Stop the daemon. Reload window. Status bar shows `⚠ TTS offline` (auto-spawn no longer fires)
- [ ] Reset settings to defaults

---

## 7. Failure-mode tests

- [ ] Stop the daemon while VS Code is open. Status bar transitions to `⚠ TTS offline` within ~2s. Restart Daemon command brings it back
- [ ] Run a command (e.g., Toggle Mute) while the daemon is offline. An error toast appears; nothing crashes
- [ ] Open a folder with no `.claude/` dir. Run Edit Workspace Config and pick `yes` to save — the directory is created and the YAML is written

---

## 8. Done

If all checkboxes pass: Phase 6 is verified end-to-end. Tag is already at
`v0.6.0-phase6`. Optionally publish to the Marketplace:

```powershell
cd extension
vsce login OpenCircuitDev
vsce publish
```

(Requires a publisher PAT.)

If anything fails: capture the symptom + the line that failed and file
it. The extension source is small enough (~600 LOC TS) to debug quickly
from `extension/src/`.
