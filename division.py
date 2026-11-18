"""Division template -> stats / production cost, built on real HoI4 1.19 game data."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import gamedata
from .gamedata import GameData
from .modifiers import ModSet, build_modifiers, FLAT_STATS
from .pdx import as_list
from .tanks import default_modules, design_tank

TERRAINS = ("plains", "forest", "hills", "mountain", "marsh", "jungle", "desert", "urban")
MULT_STATS = {"soft_attack": "soft", "hard_attack": "hard", "defense": "defense", "breakthrough": "brk",
              "ap_attack": "ap", "armor_value": "armor", "air_attack": "air"}


@dataclass
class DivisionTemplate:
    name: str = "Шаблон"
    battalions: Dict[str, int] = field(default_factory=dict)
    support: List[str] = field(default_factory=list)
    regimental: List[str] = field(default_factory=list)
    tech_year: int = 1940
    equipment_overrides: Dict[str, str] = field(default_factory=dict)   # archetype -> variant id
    tank_designs: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # need key -> {chassis, modules}
    doctrine: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DivisionStats:
    name: str
    data: Dict[str, Any]


def resolve_need(gd: GameData, key: str, tpl: DivisionTemplate, cache: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Equipment stats for a unit need key (regular equipment archetype or tank design)."""
    if key in cache:
        return cache[key]
    res: Optional[Dict[str, Any]] = None
    tank = gd.parse_tank_need(key)
    if tank:
        archetype, role = tank
        user = tpl.tank_designs.get(key) or {}
        cid = user.get("chassis") or gd.pick_chassis(archetype, tpl.tech_year)
        if cid and cid in gd.equipment:
            mods = user.get("modules")
            if mods is None:
                mods = default_modules(gd, cid, role, tpl.tech_year)
            res = design_tank(gd, cid, mods, role)
            res["need_key"] = key
    else:
        vid = tpl.equipment_overrides.get(key) or gd.pick_variant(key, tpl.tech_year)
        if vid and vid in gd.equipment:
            res = gd.eq_stats(vid)
    cache[key] = res
    return res


def _num_val(v: Any, default: float = 0.0) -> float:
    if isinstance(v, list):
        v = v[-1] if v else default
    return float(v or default)


def _unit_instance(gd: GameData, uid: str, tpl: DivisionTemplate, mods: ModSet, cache: Dict[str, Any],
                   warnings: List[str]) -> Dict[str, Any]:
    u = gd.subunits[uid]
    cats = list(u.get("categories", []))
    um = mods.for_unit(uid, cats)
    inst: Dict[str, Any] = {
        "id": uid, "name": gd.name(uid), "group": u.get("group"), "categories": cats,
        "soft": 0.0, "hard": 0.0, "defense": 0.0, "brk": 0.0, "ap": 0.0, "air": 0.0,
        "armor": 0.0, "hardness": 0.0, "fuel": 0.0, "speed": 0.0, "eq": {}, "res": {}, "ic": 0.0,
    }
    speeds: List[float] = []
    vehicle_speeds: List[float] = []
    hp_mult = 1.0
    rels: List[float] = []
    for key, qty in (u.get("need") or {}).items():
        eq = resolve_need(gd, key, tpl, cache)
        if eq is None:
            warnings.append(f"Нет снаряжения «{key}» для {gd.name(uid)} — пропущено")
            continue
        for s, f in (("soft_attack", "soft"), ("hard_attack", "hard"), ("defense", "defense"),
                     ("breakthrough", "brk"), ("ap_attack", "ap"), ("air_attack", "air")):
            inst[f] += eq[s]
        inst["armor"] = max(inst["armor"], eq["armor_value"])
        inst["hardness"] = max(inst["hardness"], eq["hardness"])
        inst["fuel"] += eq["fuel_consumption"] * qty
        if eq["maximum_speed"] > 0:
            speeds.append(eq["maximum_speed"])
            if key not in ("infantry_equipment", "support_equipment"):
                vehicle_speeds.append(eq["maximum_speed"])
        rels.append(eq["reliability"])
        if eq.get("is_design"):
            hp_mult *= eq.get("hp_mult", 1.0)
            for w in eq.get("warnings", []):
                warnings.append(f"{gd.name(uid)}: {w}")
        inst["eq"][eq["id"]] = {"name": eq["name"], "count": qty, "ic": eq["build_cost_ic"],
                                "resources": eq["resources"], "key": key}
        inst["ic"] += eq["build_cost_ic"] * qty
        for r, a in eq["resources"].items():
            inst["res"][r] = inst["res"].get(r, 0) + a * qty
    inst["speed"] = min(vehicle_speeds or speeds) if (vehicle_speeds or speeds) else 4.0
    inst["reliability"] = sum(rels) / len(rels) if rels else 0.8

    # unit definition modifiers (multiplicative on equipment stats)
    for stat, f in MULT_STATS.items():
        inst[f] *= 1.0 + _num_val(u.get(stat)) + um.get(stat, 0.0)
    inst["speed"] *= 1.0 + _num_val(u.get("maximum_speed")) + um.get("maximum_speed", 0.0)

    inst["hp"] = _num_val(u.get("max_strength")) * (1.0 + um.get("max_strength", 0.0)) * hp_mult
    inst["org"] = _num_val(u.get("max_organisation")) + um.get("max_organisation", 0.0)
    inst["morale"] = _num_val(u.get("default_morale"), 0.3) + um.get("default_morale", 0.0)
    inst["width"] = max(0.0, _num_val(u.get("combat_width")) + um.get("combat_width", 0.0))
    inst["manpower"] = _num_val(u.get("manpower"))
    inst["supply"] = max(0.0, _num_val(u.get("supply_consumption")) + um.get("supply_consumption", 0.0))
    inst["suppression"] = _num_val(u.get("suppression")) + um.get("suppression", 0.0)
    inst["weight"] = _num_val(u.get("weight"))
    inst["training"] = _num_val(u.get("training_time"))
    inst["entrenchment"] = float(u.get("entrenchment", 0) or 0) + um.get("entrenchment", 0.0)
    inst["recon"] = float(u.get("recon", 0) or 0) + um.get("recon", 0.0)
    inst["initiative"] = float(u.get("initiative", 0) or 0) + um.get("initiative", 0.0)
    inst["trickleback"] = float(u.get("casualty_trickleback", 0) or 0)
    inst["xp_loss"] = float(u.get("experience_loss_factor", 0) or 0)
    inst["capture"] = float(u.get("equipment_capture_factor", 0) or 0)
    inst["supply_factor"] = float(u.get("supply_consumption_factor", 0) or 0)
    inst["fuel_factor"] = float(u.get("fuel_consumption_factor", 0) or 0)
    inst["affects_speed"] = bool(u.get("affects_speed", True))
    terr: Dict[str, Dict[str, float]] = {}
    for t in list(TERRAINS) + ["river", "fort", "amphibious", "snow"]:
        blk = u.get(t)
        if isinstance(blk, dict):
            terr[t] = {k: float(v) for k, v in blk.items() if isinstance(v, (int, float))}
    inst["terrain"] = terr
    inst["battalion_mult"] = [b for b in as_list(u.get("battalion_mult")) if isinstance(b, dict)]
    inst["same_type"] = u.get("same_support_type")
    return inst


def calculate_division(tpl: DivisionTemplate, gd: Optional[GameData] = None) -> Dict[str, Any]:
    gd = gd or gamedata.load()
    warnings: List[str] = []
    mods = build_modifiers(gd, tpl.doctrine)
    cache: Dict[str, Any] = {}

    lines: List[Dict[str, Any]] = []
    for uid, n in tpl.battalions.items():
        if n <= 0:
            continue
        if uid not in gd.subunits:
            warnings.append(f"Неизвестный батальон: {uid}")
            continue
        inst = _unit_instance(gd, uid, tpl, mods, cache, warnings)
        lines += [dict(inst) for _ in range(int(n))]
    supports: List[Dict[str, Any]] = []
    seen_types = set()
    for uid in list(tpl.support) + list(tpl.regimental):
        if uid not in gd.subunits:
            warnings.append(f"Неизвестная рота: {uid}")
            continue
        inst = _unit_instance(gd, uid, tpl, mods, cache, warnings)
        st = inst["same_type"]
        if st and st in seen_types and uid in tpl.support:
            warnings.append(f"Две роты одного типа ({gd.name(uid)}) — в игре так нельзя")
        seen_types.add(st)
        inst["regimental"] = uid in tpl.regimental
        supports.append(inst)

    if len(lines) > 25:
        warnings.append(f"Превышен лимит линейных батальонов: {len(lines)}/25")
    if not lines:
        warnings.append("В шаблоне нет линейных батальонов")
    if len(tpl.support) > 5:
        warnings.append(f"Превышен лимит рот поддержки: {len(tpl.support)}/5")
    if len(tpl.regimental) > 5:
        warnings.append(f"Превышен лимит полковой поддержки: {len(tpl.regimental)}/5")
    groups = {l["group"] for l in lines}
    for s in supports:
        if s["regimental"]:
            allowed = gd.subunits[s["id"]].get("allowed_battalion_groups")
            if allowed and groups and not (groups & set(as_list(allowed))):
                warnings.append(f"{s['name']}: не подходит к группам батальонов шаблона")

    # support companies' battalion_mult bonuses for the line battalions
    for s in supports:
        for bm in s["battalion_mult"]:
            cat = bm.get("category")
            for l in lines:
                if cat in l["categories"]:
                    for stat, f in MULT_STATS.items():
                        if stat in bm:
                            l[f] *= 1.0 + bm[stat]
                    if "max_strength" in bm:
                        l["hp"] *= 1.0 + bm["max_strength"]
                    if "max_organisation" in bm:
                        l["org"] += bm["max_organisation"]
                    if "entrenchment" in bm:
                        l["entrenchment"] += bm["entrenchment"]

    allu = lines + supports
    n_l = max(1, len(lines))
    width = sum(l["width"] for l in lines)
    hp = sum(u["hp"] for u in allu)
    org = sum(l["org"] for l in lines) / n_l
    morale = sum(l["morale"] for l in lines) / n_l
    spd = [l["speed"] for l in lines if l["affects_speed"]]
    speed = min(spd) if spd else 0.0
    sums = {k: sum(u[k] for u in allu) for k in ("soft", "hard", "defense", "brk", "air", "manpower", "weight", "fuel")}
    mp = sum(l["manpower"] for l in lines) or 1.0
    hardness = sum(l["hardness"] * l["manpower"] for l in lines) / mp

    avs = gd.d("ARMOR_VS_AVERAGE", 0.4)
    n_all = max(1, len(allu))
    armor = avs * max([u["armor"] for u in allu] or [0]) + (1 - avs) * sum(u["armor"] for u in allu) / n_all
    pierce = avs * max([u["ap"] for u in allu] or [0]) + (1 - avs) * sum(u["ap"] for u in allu) / n_all

    sc = mods.scalar
    supply_f = sum(s["supply_factor"] for s in supports) + sc.get("supply_consumption_factor", 0.0)
    supply = sum(u["supply"] for u in allu) * max(0.0, 1.0 + supply_f)
    fuel_f = sum(s["fuel_factor"] for s in supports)
    fuel = sums["fuel"] * max(0.0, 1.0 + fuel_f)

    # equipment table & IC / resources
    eq_table: Dict[str, Dict[str, Any]] = {}
    resources: Dict[str, float] = {}
    for u in allu:
        for eid, e in u["eq"].items():
            row = eq_table.setdefault(eid, {"id": eid, "name": e["name"], "count": 0, "ic_each": e["ic"],
                                            "resources_each": e["resources"]})
            row["count"] += e["count"]
    ic_total = 0.0
    for row in eq_table.values():
        row["ic_total"] = round(row["count"] * row["ic_each"], 2)
        ic_total += row["count"] * row["ic_each"]
        for r, a in row["resources_each"].items():
            resources[r] = resources.get(r, 0) + a * row["count"]

    # terrain modifiers: line = width-weighted average, supports additive
    terr: Dict[str, Dict[str, float]] = {}
    keys = set()
    for u in allu:
        keys |= set(u["terrain"])
    wsum = sum(l["width"] for l in lines) or 1.0
    for t in keys:
        merged: Dict[str, float] = {}
        for l in lines:
            for k, v in l["terrain"].get(t, {}).items():
                merged[k] = merged.get(k, 0.0) + v * l["width"] / wsum
        for s in supports:
            for k, v in s["terrain"].get(t, {}).items():
                merged[k] = merged.get(k, 0.0) + v
        terr[t] = {k: round(v, 4) for k, v in merged.items()}

    arty_w = sum(l["width"] for l in lines if any("artillery" in c for c in l["categories"]))
    data = {
        "name": tpl.name,
        "line_count": len(lines), "support_count": len(tpl.support), "regimental_count": len(tpl.regimental),
        "width": round(width, 2), "hp": round(hp, 2), "org": round(org, 2), "morale": round(morale, 3),
        "speed": round(speed, 2), "soft": round(sums["soft"], 2), "hard": round(sums["hard"], 2),
        "defense": round(sums["defense"], 2), "brk": round(sums["brk"], 2), "air": round(sums["air"], 2),
        "armor": round(armor, 2), "pierce": round(pierce, 2), "hardness": round(hardness, 3),
        "manpower": int(sums["manpower"]), "supply": round(supply, 3), "fuel": round(fuel, 2),
        "weight": round(sums["weight"], 2),
        "training": int(max([u["training"] for u in allu] or [0])),
        "suppression": round(sum(l["suppression"] for l in lines), 2),
        "entrenchment": round(sum(u["entrenchment"] for u in supports) + sum(l["entrenchment"] for l in lines), 2),
        "recon": round(sum(u["recon"] for u in allu), 2),
        "initiative": round(sum(u["initiative"] for u in allu), 3),
        "trickleback": round(min(gd.d("MAX_CASUALTY_TRICKLEBACK", 0.95), sum(u["trickleback"] for u in supports)), 3),
        "xp_loss": round(sum(u["xp_loss"] for u in supports), 3),
        "capture": round(sum(u["capture"] for u in supports), 3),
        "artillery_ratio": round(arty_w / width, 3) if width else 0.0,
        "ic_cost": round(ic_total, 2),
        "equipment": sorted(eq_table.values(), key=lambda r: -r["ic_total"]),
        "resources": {k: round(v, 1) for k, v in sorted(resources.items())},
        "terrain": terr,
        "tactics": sorted(mods.tactics),
        "scalar": mods.scalar,
        "battalion_groups": sorted(groups),
        "units": [{"id": u["id"], "name": u["name"], "soft": round(u["soft"], 2), "hard": round(u["hard"], 2),
                   "defense": round(u["defense"], 2), "brk": round(u["brk"], 2), "armor": round(u["armor"], 1),
                   "ap": round(u["ap"], 1), "hp": round(u["hp"], 2), "org": round(u["org"], 1),
                   "width": round(u["width"], 2), "speed": round(u["speed"], 2)}
                  for u in allu],
        "warnings": warnings,
    }
    return data
