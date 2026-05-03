"""SecretsStore: plaintext YAML at ~/.claude/scripts/codetalker/secrets.yaml.

Stores API keys for cloud providers (Anthropic, OpenAI, OpenRouter, ElevenLabs).
The file is gitignored and file-permission-restricted (0600 on POSIX). Env vars
always take precedence over file values, so users can override without editing
the file (e.g. for CI / one-off testing).

Schema (all keys optional):
    anthropic_api_key: str
    openai_api_key: str
    openrouter_api_key: str
    elevenlabs_api_key: str
"""
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import yaml


DEFAULT_SECRETS_PATH = Path.home() / ".claude" / "scripts" / "codetalker" / "secrets.yaml"

# Maps env var name -> secrets file key. Env value, if present, ALWAYS wins.
ENV_OVERRIDES: dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "ELEVENLABS_API_KEY": "elevenlabs_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
}

KNOWN_KEYS = list(ENV_OVERRIDES.values())


class SecretsStore:
    """Atomic file-backed plaintext secrets storage.

    Read-priority: env var > secrets.yaml > None.
    Write-target: secrets.yaml (env vars are read-only).
    """

    def __init__(self, secrets_path: Path | None = None):
        self._path = secrets_path if secrets_path is not None else DEFAULT_SECRETS_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, str]:
        """Load secrets from disk. Returns empty dict if file doesn't exist."""
        if not self._path.exists():
            return {}
        try:
            data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logging.warning("corrupted secrets file %s: %s", self._path, e)
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

    def save(self, secrets: dict[str, str]) -> Path:
        """Atomic write: serialize to .tmp, then rename to .yaml.

        Filters input to KNOWN_KEYS to avoid writing arbitrary keys.
        Sets file permissions to 0600 on POSIX after write.
        """
        filtered = {
            k: v for k, v in secrets.items()
            if k in KNOWN_KEYS and isinstance(v, str) and v
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp.write_text(yaml.safe_dump(filtered, sort_keys=True), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise
        # Best-effort restrict permissions on POSIX. No-op on Windows where
        # default ACLs already restrict to the user.
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return self._path

    def get(self, key: str) -> str | None:
        """Return effective value for ``key`` (env var wins over file).

        ``key`` must be one of KNOWN_KEYS (e.g. ``anthropic_api_key``).
        """
        # Reverse-lookup the env var name for this key.
        for env_name, file_key in ENV_OVERRIDES.items():
            if file_key == key:
                env_val = os.environ.get(env_name)
                if env_val:
                    return env_val
                break
        return self.load().get(key)

    def all_resolved(self) -> dict[str, str]:
        """Return all known keys with effective values (env > file)."""
        on_disk = self.load()
        out: dict[str, str] = {}
        for env_name, file_key in ENV_OVERRIDES.items():
            env_val = os.environ.get(env_name)
            if env_val:
                out[file_key] = env_val
            elif file_key in on_disk:
                out[file_key] = on_disk[file_key]
        return out

    def update(self, partial: dict[str, str]) -> Path:
        """Merge ``partial`` into existing on-disk secrets and save.

        Empty-string values DELETE the key from disk (so users can clear a key
        from the UI by submitting "" without deleting other keys).
        """
        current = self.load()
        for k, v in partial.items():
            if k not in KNOWN_KEYS:
                continue
            if v == "":
                current.pop(k, None)
            elif isinstance(v, str):
                current[k] = v
        return self.save(current)

    @staticmethod
    def redact(value: str | None) -> str | None:
        """Mask all but the last 4 chars of a secret. None -> None."""
        if value is None:
            return None
        if len(value) <= 4:
            return "*" * len(value)
        return "*" * (len(value) - 4) + value[-4:]
