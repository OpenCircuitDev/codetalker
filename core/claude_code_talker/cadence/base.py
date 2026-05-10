"""CadenceStrategy ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from claude_code_talker.event_buffer import Event


@dataclass
class Decision:
    fire_immediately: bool = False
    fire_periodic: bool = False
    events: list[Event] = field(default_factory=list)


class CadenceStrategy(ABC):
    """Abstract base for live-mode narration cadence strategies. Subclasses decide when to fire by reacting to incoming events (`on_event`) and on periodic ticks (`tick`). Each subclass must override `name` with a unique short identifier."""

    name: str = "base"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name == "base":
            raise TypeError(f"{cls.__name__} must override `name`")

    @abstractmethod
    def on_event(self, event: Event) -> Decision:
        """Return a Decision in response to `event`. Called synchronously from EventBuffer.push subscriber chain."""

    @abstractmethod
    def tick(self) -> Decision:
        """Return a Decision driven by elapsed time. Called by the live-mode periodic timer."""
