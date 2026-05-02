"""Mode strategy registry."""
from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.modes.direct import DirectMode

__all__ = ["ModeStrategy", "DirectMode"]
