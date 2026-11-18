"""Aggregation of doctrine bonuses (grand doctrine, milestones, sub-doctrines, rewards)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .gamedata import GameData
from .pdx import as_list

STRUCTURAL = {"milestones", "tracks", "name", "enable_tactic", "rewards", "track", "mastery", "type",
              "__bare__", "limit"}

FLAT_STATS = {"max_organisation", "default_morale", "combat_width", "supply_consumption", "entrenchment",
              "recon", "suppression", "initiative", "reliability", "hardness"}


@dataclass
class ModSet:
    """cat[key][stat]: key is a ``category_*`` or a sub-unit id."""
    cat: Dict[str, Dict[str, float]] = field(default_factory=dict)
    scalar: Dict[str, float] = field(default_factory=dict)
    tactics: Set[str] = field(default_factory=set)
    notes: List[str] = field(default_factory=list)

    def add_block(self, gd: GameData, block: Dict[str, Any]) -> None:
        for key, val in block.items():
            if key in STRUCTURAL:
                if key == "enable_tactic":
                    self.tactics.update(x for x in as_list(val) if isinstance(x, str))
                continue
            if isinstance(val, dict) and (key.startswith("category_") or key in gd.subunits):
                bucket = self.cat.setdefault(key, {})
                for stat, v in val.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        bucket[stat] = bucket.get(stat, 0.0) + v
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                self.scalar[key] = self.scalar.get(key, 0.0) + val

    def for_unit(self, uid: str, categories: List[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for key in [uid] + list(categories):
            for stat, v in self.cat.get(key, {}).items():
                out[stat] = out.get(stat, 0.0) + v
        return out


def build_modifiers(gd: GameData, sel: Optional[Dict[str, Any]]) -> ModSet:
    """sel = {grand, milestones:[bool*4], subs:{track: sub_id}, rewards:{sub_id:[reward,...]|"all"}}"""
    ms = ModSet()
    if not sel:
        return ms
    grand = (gd.doctrines["grand"].get(sel.get("grand") or "") or None)
    if grand:
        ms.add_block(gd, grand)
        miles = as_list(grand.get("milestones"))
        flags = sel.get("milestones")
        if flags is None:
            flags = [True] * len(miles)
        for i, m in enumerate(miles):
            if i < len(flags) and flags[i] and isinstance(m, dict):
                ms.add_block(gd, m)
    for track, sid in (sel.get("subs") or {}).items():
        sub = gd.doctrines["sub"].get(sid)
        if not sub:
            continue
        ms.add_block(gd, sub)
        want = (sel.get("rewards") or {}).get(sid, "all")
        for rid, reward in (sub.get("rewards") or {}).items():
            if (want == "all" or rid in want) and isinstance(reward, dict):
                ms.add_block(gd, reward)
    return ms
