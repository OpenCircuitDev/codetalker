# Phase 7 Slim Extension Smoke Test

Manual verification for the slimmed-down VS Code extension. The extension is now an in-editor anchor: status bar + "Open Web UI" command. The full configurability lives in the web UI (see `core/SMOKE_TEST.md`).

---

## §0 Pre-flight

- [ ] `pip install -e core/` succeeds (daemon installable)
- [ ] `claude-code-talker serve &` binds to `127.0.0.1:17832`
- [ ] `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:17832/api/health` returns `200`

---

## §1 Install the extension

```powershell
cd c:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker
code --install-extension extension/claude-code-talker-vscode-0.2.0.vsix
```

- [ ] Install completes with "successfully installed"
- [ ] Reload VS Code window (Ctrl+Shift+P → "Developer: Reload Window")

---

## §2 Activation + status bar

- [ ] Bottom-right status bar shows `🔊 TTS (N)` (where N = active session count) or `🔇 TTS off` if muted
- [ ] If daemon isn't running: `⚠ TTS offline` with tooltip showing the URL it tried
- [ ] Hovering shows tooltip with engine list and active session count

---

## §3 Status bar interaction

- [ ] Click the status bar item — flips between `🔊 TTS (N)` and `🔇 TTS off` within ~2s
- [ ] Click again — flips back

---

## §4 Command Palette (only 2 commands now)

- [ ] `Ctrl+Shift+P` → type "Claude TTS"
- [ ] Exactly 2 commands appear:
  - `Claude TTS: Toggle Mute`
  - `Claude TTS: Open Web UI`

---

## §5 Open Web UI command

- [ ] Run "Claude TTS: Open Web UI" from palette
- [ ] Default browser opens to `http://127.0.0.1:17832/ui/`
- [ ] Web UI loads (proceed to `core/SMOKE_TEST.md` for the rich workflow)

---

## §6 Settings round-trip

- [ ] Open VS Code settings (Ctrl+,) → search "Claude TTS"
- [ ] 4 settings visible: `daemonHost`, `daemonPort`, `statusBarPollIntervalMs`, `autoSpawnDaemon`
- [ ] Change `statusBarPollIntervalMs` to 5000 → reload window → status bar refresh feels slower
- [ ] Reset to defaults

---

## §7 Failure-mode tests

- [ ] Stop daemon → status bar transitions to `⚠ TTS offline` within ~2s
- [ ] Click status bar (toggle command) → error toast; nothing crashes
- [ ] Restart daemon → status bar recovers within ~2s

---

## §8 Done

If all checkboxes pass, the slim extension is verified. The Phase 6 icon-not-showing bug should be gone — the activation path no longer touches the MCP SDK.

If the icon still doesn't show, check:
- Help menu → Toggle Developer Tools → Console for activation errors
- Help menu → Show Logs → Extension Host for activation errors

Report any failures.
