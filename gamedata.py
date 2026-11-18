"""Loader and query helpers for the extracted HoI4 game data (generated/game_data.json)."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from .extract import OUT_FILE, find_game_dir, extract_all

LINE_GROUPS = {"infantry", "mobile", "armor", "combat_support", "mobile_combat_support", "armor_combat_support"}
EQ_STAT_KEYS = ("soft_attack", "hard_attack", "defense", "breakthrough", "ap_attack", "armor_value",
                "hardness", "air_attack", "maximum_speed", "reliability", "build_cost_ic", "fuel_consumption")
SKIP_SUBUNIT_PREFIXES = ("hq_", "fake_")
SKIP_SUBUNITS = {"bus", "elephantry", "camelry", "helicopter_transport", "land_cruiser"}

TANK_CLASSES = ("light", "medium", "heavy", "super_heavy", "modern")
_TANK_NEED = re.compile(r"^(light|medium|heavy|super_heavy|modern)_tank_(?:(destroyer|artillery|aa|flame|amphibious)_)?chassis$")


class GameData:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.version: str = raw.get("game_version", "?")
        self.defines: Dict[str, Any] = raw["defines"]
        self.subunits: Dict[str, dict] = raw["subunits"]
        self.equipment: Dict[str, dict] = raw["equipment"]
        self.modules: Dict[str, dict] = raw["modules"]
        self.tactics: Dict[str, dict] = raw["tactics"]
        self.terrain: Dict[str, dict] = raw["terrain"]
        self.doctrines: Dict[str, Any] = raw["doctrines"]
        self.techs: Dict[str, dict] = raw["techs"]
        self.loc: Dict[str, str] = raw.get("loc", {})
        self.unlock_sub: Dict[str, int] = raw["unlocks"]["subunits"]
        self.unlock_mod: Dict[str, int] = raw["unlocks"]["modules"]

    # ----------------------------------------------------------- misc
    def d(self, key: str, default: float = 0.0) -> float:
        return self.defines.get(key, default)

    def name(self, key: str) -> str:
        return self.loc.get(key) or self.loc.get(key.upper()) or key.replace("_", " ").title()

    # ----------------------------------------------------------- sub units
    def sub_year(self, uid: str) -> int:
        if uid in self.unlock_sub:
            return self.unlock_sub[uid]
        return 1936 if self.subunits[uid].get("active", False) else 1936

    def _usable(self, uid: str, u: dict) -> bool:
        return not (uid.startswith(SKIP_SUBUNIT_PREFIXES) or uid in SKIP_SUBUNITS)

    def is_regimental(self, u: dict) -> bool:
        return "category_regimental_support_battalions" in u.get("categories", [])

    def is_division_support(self, u: dict) -> bool:
        return u.get("group") == "support" and "category_divisional_support_battalions" in u.get("categories", [])

    def line_units(self) -> List[str]:
        return [k for k, u in self.subunits.items()
                if u.get("group") in LINE_GROUPS and self._usable(k, u) and not self.is_regimental(u)
                and not self.is_division_support(u)]

    def support_units(self) -> List[str]:
        return [k for k, u in self.subunits.items() if self.is_division_support(u) and self._usable(k, u)]

    def regimental_units(self) -> List[str]:
        return [k for k, u in self.subunits.items() if self.is_regimental(u) and self._usable(k, u)]

    # ----------------------------------------------------------- equipment
    def variants(self, archetype: str) -> List[str]:
        res = [k for k, e in self.equipment.items() if e.get("archetype") == archetype and k != archetype]
        return sorted(res, key=lambda k: (self.equipment[k].get("year", 1936), k))

    def pick_variant(self, archetype: str, year: int) -> Optional[str]:
        vs = self.variants(archetype)
        ok = [v for v in vs if self.equipment[v].get("year", 1936) <= year]
        if ok:
            return ok[-1]
        if vs:
            return vs[0]
        return archetype if archetype in self.equipment else None

    def eq_stats(self, eid: str) -> Dict[str, Any]:
        e = self.equipment[eid]
        out = {k: float(e.get(k, 0) or 0) for k in EQ_STAT_KEYS}
        out["resources"] = dict(e.get("resources") or {})
        out["id"] = eid
        out["name"] = self.name(eid)
        out["year"] = e.get("year", 1936)
        out["archetype"] = e.get("archetype", eid)
        return out

    # ----------------------------------------------------------- tank chassis
    def parse_tank_need(self, key: str):
        """'medium_tank_destroyer_chassis' -> ('medium_tank_chassis', 'anti_tank')."""
        m = _TANK_NEED.match(key)
        if not m:
            return None
        cls, role = m.group(1), m.group(2)
        role_map = {None: "armor", "destroyer": "anti_tank", "artillery": "artillery", "aa": "anti_air",
                    "flame": "flamethrower", "amphibious": "armor"}
        archetype = f"{cls}_tank_chassis"
        if role == "amphibious":
            archetype = "amphibious_tank_chassis"
        return archetype, role_map[role]

    def chassis_slots(self, cid: str) -> Dict[str, dict]:
        seen = set()
        cur = cid
        while cur and cur not in seen:
            seen.add(cur)
            e = self.equipment.get(cur, {})
            slots = e.get("module_slots")
            if isinstance(slots, dict):
                return slots
            cur = e.get("archetype") or e.get("parent")
        return {}

    def chassis_list(self, archetype: str) -> List[str]:
        pat = re.compile(rf"^{re.escape(archetype)}_\d+$")
        res = [k for k in self.equipment if pat.match(k)]
        return sorted(res, key=lambda k: (self.equipment[k].get("year", 1936), k))

    def pick_chassis(self, archetype: str, year: int) -> Optional[str]:
        vs = self.chassis_list(archetype)
        ok = [v for v in vs if self.equipment[v].get("year", 1936) <= year]
        return (ok[-1] if ok else (vs[0] if vs else (archetype if archetype in self.equipment else None)))

    def module_year(self, mid: str) -> int:
        return self.unlock_mod.get(mid, 1936)

    def modules_for_slot(self, slot: dict) -> List[str]:
        cats = set(slot.get("allowed_module_categories") or [])
        return [m for m, v in self.modules.items() if v.get("category") in cats]


_instance: Optional[GameData] = None


def load(refresh: bool = False, game_dir: Optional[str] = None) -> GameData:
    """Load game data; extract from the installed game when no cache exists."""
    global _instance
    if _instance is not None and not refresh:
        return _instance
    if refresh or not OUT_FILE.exists():
        data = extract_all(find_game_dir(game_dir))
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    _instance = GameData(json.loads(OUT_FILE.read_text(encoding="utf-8")))
    return _instance
