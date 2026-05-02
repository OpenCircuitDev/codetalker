"""Cadence strategy registry."""
from claude_code_talker.cadence.base import CadenceStrategy, Decision
from claude_code_talker.cadence.periodic import PeriodicCadence
from claude_code_talker.cadence.per_tool_call import PerToolCallCadence
from claude_code_talker.cadence.per_cluster import PerClusterCadence
from claude_code_talker.cadence.significant_only import SignificantOnlyCadence
from claude_code_talker.cadence.hybrid import HybridCadence

__all__ = ["CadenceStrategy", "Decision", "PeriodicCadence", "PerToolCallCadence", "PerClusterCadence", "SignificantOnlyCadence", "HybridCadence", "make_cadence"]


def make_cadence(name: str, cfg: dict) -> CadenceStrategy:
    """Construct a CadenceStrategy from its name and the live config dict.

    cfg is expected to be cfg["live"] (or {} fallback).
    """
    if name == "periodic":
        return PeriodicCadence(period_seconds=float((cfg.get("periodic") or {}).get("period_seconds", 12.0)))
    if name == "per_tool_call":
        return PerToolCallCadence()
    if name == "per_cluster":
        pc = cfg.get("per_cluster") or {}
        return PerClusterCadence(
            cluster_gap_seconds=float(pc.get("cluster_gap_seconds", 4.0)),
            max_cluster_size=int(pc.get("max_cluster_size", 8)),
        )
    if name == "significant_only":
        return SignificantOnlyCadence(threshold=float(cfg.get("significance_threshold", 0.5)))
    if name == "hybrid":
        h = cfg.get("hybrid") or {}
        return HybridCadence(
            threshold=float(cfg.get("significance_threshold", 0.5)),
            period_seconds=float(h.get("period_seconds", 15.0)),
        )
    raise ValueError(f"unknown cadence: {name}")
