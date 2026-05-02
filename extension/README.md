# Claude Code Talker — VS Code Extension

Voice companion for Claude Code. Wraps the daemon (claude-code-talker
Python package) in a VS Code UI: status bar indicator, Command Palette
commands, and a workspace config editor.

## Prerequisites

- Python 3.11+
- `pip install claude-code-talker`
- Run `claude-code-talker-setup` once to configure

## Install

Install from VSIX:

    code --install-extension claude-code-talker-vscode-0.1.0.vsix

Or via Marketplace once published.

## Usage

The status bar (bottom right) shows the active mode and voice. Click to toggle mute. Open the Command Palette and search "Claude TTS" for all commands.
