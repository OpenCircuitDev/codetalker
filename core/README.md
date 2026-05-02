# claude_code_talker (core)

Python MCP server providing TTS for Claude Code. Part of Claude Code Talker.
Phase 1 supports Piper TTS, Ollama LLM, and Modes A (direct read) and B (turn-end brief).

Built on the CodeTalker core (engine-neutral abstractions: engines, providers, modes, MCP server shell).

## Install

    pip install -e .[dev]

## Run server

    claude-code-talker

## Run tests

    pytest core/tests
