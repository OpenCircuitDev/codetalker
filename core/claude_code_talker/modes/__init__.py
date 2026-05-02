"""Mode strategy registry."""
from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.modes.direct import DirectMode
from claude_code_talker.modes.brief import BriefMode

__all__ = ["ModeStrategy", "DirectMode", "BriefMode"]
