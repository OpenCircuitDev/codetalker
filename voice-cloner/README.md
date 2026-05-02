# Claude Code Talker — Voice Cloner

Standalone CLI that downloads audio from YouTube, extracts a clean segment,
and saves it as a reference WAV in `~/.claude/scripts/voice-cloner/references/`.
The XTTSEngine in claude-code-talker core consumes these reference WAVs to
clone voices.

Requires: ffmpeg on PATH.

## Install

    pip install -e .[dev]

## Usage

    claude-code-talker-voice-cloner from-youtube --url <YT URL> --start 1:23 --duration 15 --name marvin
    claude-code-talker-voice-cloner list
    claude-code-talker-voice-cloner remove --name marvin
