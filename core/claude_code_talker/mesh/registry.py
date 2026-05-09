"""Phase 25b — provider registry by name.

Resolves a provider class from its short name and constructs an instance with
the supplied API key.
"""
from __future__ import annotations

from .hyper3d import Hyper3DProvider
from .meshy import MeshyProvider
from .provider import Mesh3DProvider
from .tripo3d import Tripo3DProvider


PROVIDERS: dict[str, type[Mesh3DProvider]] = {
    "hyper3d": Hyper3DProvider,
    "meshy": MeshyProvider,
    "tripo3d": Tripo3DProvider,
}


def make_provider(name: str, api_key: str) -> Mesh3DProvider:
    cls = PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"unknown mesh provider: {name}")
    return cls(api_key=api_key)
