# Claude Code Talker — Voice Cloner

Installs as the `claude-code-talker-voice-cloner` command.

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

## Legal

Voice cloning of real people or copyrighted characters: use for personal
listening only. Distribution, public release, or commercial use of cloned
voices may infringe on personality rights, copyright on the source recording,
or platform Terms of Service. This tool is provided as-is; you are responsible
for the audio you generate.
