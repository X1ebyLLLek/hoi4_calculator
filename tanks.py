"""Modular tank designer (chassis + modules) built on extracted HoI4 data."""

from typing import Any, Dict, List, Optional

from .gamedata import GameData, EQ_STAT_KEYS
from .pdx import as_list

ROLE_ALLOW = {"armor": {None, "anti_tank"}, "anti_tank": {"anti_tank"}, "artillery": {"artillery"},
              "anti_air": {"anti_air"}, "flamethrower": {"flame"}}


def _num(d: Any, key: str) -> float:
    if isinstance(d, dict):
        v = d.get(key, 0)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _allowed_armament_categories(gd: GameData, modules: Dict[str, str]) -> Optional[set]:
    turret = gd.modules.get(modules.get("turret_type_slot", ""), {})
    allowed = turret.get("allowed_module_categories")
    if isinstance(allowed, dict):
        cats = allowed.get("main_armament_slot")
        if cats:
            return set(as_list(cats))
    return None


def _role_of_module(mod: dict) -> Optional[str]:
    a = mod.get("allow_equipment_type")
    if isinstance(a, list):
        a = a[0]
    return a if isinstance(a, str) else None


def _slot_candidates(gd: GameData, slot_name: str, slot: dict, chosen: Dict[str, str],
                     role: str, year: int) -> List[str]:
    cands = [m for m in gd.modules_for_slot(slot) if gd.module_year(m) <= year]
    if slot_name == "main_armament_slot":
        turret_cats = _allowed_armament_categories(gd, chosen)
        if turret_cats:
            cands = [m for m in cands if gd.modules[m].get("category") in turret_cats]
        allow = ROLE_ALLOW[role]
        cands = [m for m in cands if _role_of_module(gd.modules[m]) in allow]
    return cands


def _score_module(gd: GameData, mid: str, slot_name: str, role: str) -> float:
    m = gd.modules[mid]
    add, mul = m.get("add_stats") or {}, m.get("multiply_stats") or {}
    if slot_name == "main_armament_slot":
        if role == "anti_air":
            return _num(add, "air_attack") * 3 + _num(add, "soft_attack")
        if role == "artillery" or role == "flamethrower":
            return _num(add, "soft_attack") * 2 + _num(add, "breakthrough") * 0.5 - _num(add, "build_cost_ic")
        # tank gun & tank destroyer: favour piercing and hard attack
        return _num(add, "ap_attack") * 1.0 + _num(add, "hard_attack") * 2.0 + _num(add, "soft_attack") * 0.8 \
            - _num(add, "build_cost_ic") * 0.5
    if slot_name == "turret_type_slot":
        return _num(add, "breakthrough") * 0.5 - _num(add, "build_cost_ic") * 0.5 + gd.module_year(mid) * 0.01
    if slot_name == "armor_type_slot":
        return (_num(mul, "armor_value") * 100 + _num(add, "defense") + _num(add, "breakthrough")
                - _num(add, "build_cost_ic") * 2)
    if slot_name == "engine_type_slot":
        return (_num(mul, "maximum_speed") * 20 + _num(add, "maximum_speed") * 4 + _num(add, "reliability") * 15
                - _num(add, "fuel_consumption") * 0.5 - _num(add, "build_cost_ic") * 0.5)
    if slot_name == "suspension_type_slot":
        return (_num(add, "maximum_speed") * 4 + _num(mul, "maximum_speed") * 20 + _num(add, "reliability") * 15
                + _num(add, "breakthrough") * 0.2 - _num(add, "build_cost_ic") * 0.5 + gd.module_year(mid) * 0.01)
    return 0.0


def default_modules(gd: GameData, chassis_id: str, role: str = "armor", year: int = 1944) -> Dict[str, str]:
    """Heuristic 'meta' design: best unlocked module for every required slot."""
    slots = gd.chassis_slots(chassis_id)
    chosen: Dict[str, str] = {}
    for slot_name, slot in slots.items():
        if not isinstance(slot, dict):
            continue
        if not slot.get("required") and slot_name != "main_armament_slot":
            continue
        cands = _slot_candidates(gd, slot_name, slot, chosen, role, year)
        if not cands:
            continue
        if slot_name == "turret_type_slot" and "main_armament_slot" in slots:
            arm_slot = slots["main_armament_slot"]

            def turret_value(t: str) -> float:
                trial = dict(chosen)
                trial[slot_name] = t
                arms = _slot_candidates(gd, "main_armament_slot", arm_slot, trial, role, year)
                best = max((_score_module(gd, a, "main_armament_slot", role) for a in arms), default=-1e6)
                return best + _score_module(gd, t, slot_name, role)

            chosen[slot_name] = max(cands, key=turret_value)
            continue
        chosen[slot_name] = max(cands, key=lambda m: _score_module(gd, m, slot_name, role))
    return chosen


def design_tank(gd: GameData, chassis_id: str, modules: Dict[str, str], role: str = "armor") -> Dict[str, Any]:
    """Compute final equipment stats of a tank design."""
    e = gd.equipment[chassis_id]
    stats = {k: float(e.get(k, 0) or 0) for k in EQ_STAT_KEYS}
    resources = dict(e.get("resources") or {})
    warnings: List[str] = []
    slots = gd.chassis_slots(chassis_id)

    add: Dict[str, float] = {}
    mul: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    cat_counts: Dict[str, int] = {}
    for slot_name, mid in modules.items():
        if not mid or mid == "empty":
            continue
        m = gd.modules.get(mid)
        if m is None:
            warnings.append(f"Неизвестный модуль {mid}")
            continue
        slot = slots.get(slot_name)
        if isinstance(slot, dict):
            if m.get("category") not in (slot.get("allowed_module_categories") or []):
                warnings.append(f"Модуль «{gd.name(mid)}» не подходит в слот {slot_name}")
        for k, v in (m.get("add_stats") or {}).items():
            if isinstance(v, (int, float)):
                add[k] = add.get(k, 0.0) + v
        for k, v in (m.get("multiply_stats") or {}).items():
            if isinstance(v, (int, float)):
                mul[k] = mul.get(k, 0.0) + v
        for r, a in (m.get("build_cost_resources") or {}).items():
            resources[r] = resources.get(r, 0) + a
        counts[mid] = counts.get(mid, 0) + 1
        cat_counts[m.get("category", "")] = cat_counts.get(m.get("category", ""), 0) + 1

    for lim in as_list(e.get("module_count_limit")) or as_list(gd.equipment.get(e.get("archetype", ""), {}).get("module_count_limit")):
        if not isinstance(lim, dict):
            continue
        cnt = lim.get("count") or {}
        cap = cnt.get("value", 99) if isinstance(cnt, dict) else 99
        used = counts.get(lim.get("module"), 0) if "module" in lim else cat_counts.get(lim.get("category"), 0)
        if used >= cap:
            warnings.append(f"Превышен лимит модулей: {lim.get('module') or lim.get('category')} (<{cap})")

    for k in EQ_STAT_KEYS:
        stats[k] = (stats[k] + add.get(k, 0.0)) * (1.0 + mul.get(k, 0.0))
    stats["hardness"] = min(1.0, max(0.0, stats["hardness"]))

    scaled = e.get("scaled_by_reliability")
    hp_mult = 1.0 + mul.get("max_strength", 0.0)
    if isinstance(scaled, dict) and "max_strength" in scaled:
        hp_mult *= 1.0 - scaled["max_strength"] * (1.0 - min(1.0, stats["reliability"]))
    # armament decides the final role
    arm = gd.modules.get(modules.get("main_armament_slot", ""), {})
    arm_type = _role_of_module(arm)
    real_role = {"flame": "flamethrower", "artillery": "artillery", "anti_air": "anti_air"}.get(arm_type, "armor")
    if arm_type == "anti_tank":
        real_role = role if role in ("armor", "anti_tank") else "armor"
    if role != real_role:
        warnings.append(f"Вооружение даёт роль «{real_role}», а слот требует «{role}»")

    stats.update({
        "resources": resources,
        "hp_mult": hp_mult,
        "id": chassis_id,
        "name": gd.name(chassis_id),
        "year": e.get("year", 1936),
        "archetype": e.get("archetype", chassis_id),
        "modules": {k: v for k, v in modules.items() if v and v != "empty"},
        "role": real_role,
        "warnings": warnings,
        "is_design": True,
    })
    return stats
