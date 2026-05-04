# Codetalker Extension — Known Limitations

## v0.3.0 (current)

- **Python prerequisite.** The daemon is a Python package. You must run
  `pip install claude-code-talker` before the extension can spawn it.
  The extension surfaces a warning notification if the binary is missing.
- **Piper TTS not bundled.** Default offline TTS engine requires Piper to be
  installed separately. See https://github.com/rhasspy/piper for downloads.
- **No Marketplace listing yet.** v0.3.0 ships via GitHub Releases.
  Marketplace publish is targeted for v0.4.0.
- **No bundled icon.** Extension shows the default VS Code extension icon.
  Custom icon is part of v0.4.0 polish.
- **Cloud narration data flow.** Narration text is sent to whichever LLM
  provider you select. If you need local-only operation, configure
  the `ollama` provider and a local TTS engine (Piper, XTTS).

## Coming in v0.4.0

- Marketplace listing with publisher verification
- Custom icon and gallery banner
- Bundled Piper download
- PRIVACY.md and full disclosure form
- Possibly: VS Code webview embedding for the Web UI (works in remote/SSH/web VS Code contexts)
