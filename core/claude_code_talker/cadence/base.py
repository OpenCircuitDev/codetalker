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
    name: str = "base"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name == "base":
            raise TypeError(f"{cls.__name__} must override `name`")

    @abstractmethod
    def on_event(self, event: Event) -> Decision: ...

    @abstractmethod
    def tick(self) -> Decision: ...
