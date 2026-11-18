"""HoI4 1.19.4+ Division Template Stat & Production Cost Calculator."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..data.equipment import EQUIPMENT_DB, Equipment, get_default_equipment_for_year
from ..data.battalions import BATTALION_DB, Battalion
from ..data.support_companies import SUPPORT_DB, SupportCompany
from ..data.doctrines_terrain import DOCTRINE_DB, LandDoctrine


@dataclass
class DivisionTemplate:
    name: str
    battalions: Dict[str, int]  # battalion_id -> count (max 25 line battalions)
    support_companies: List[str] = field(default_factory=list)       # max 5 standard
    regimental_supports: List[str] = field(default_factory=list)     # 1.19+ regimental support
    tech_year: int = 1940
    support_tech_level: int = 2  # 1..4
    doctrine_id: str = "none"
    equipment_overrides: Dict[str, str] = field(default_factory=dict)  # category -> equipment_id


@dataclass
class DivisionStats:
    name: str
    battalion_count: int
    support_count: int
    regimental_count: int
    combat_width: float
    manpower: int
    hp: float
    organization: float
    recovery_rate: float
    max_speed: float
    soft_attack: float
    hard_attack: float
    defense: float
    breakthrough: float
    air_attack: float
    armor: float
    piercing: float
    hardness: float
    supply_use: float
    fuel_use: float
    weight: float
    training_time: int
    suppression: float
    entrenchment: float
    recon: float
    initiative: float
    trickleback: float
    xp_loss_reduction: float
    equipment_capture: float
    reliability_bonus: float
    total_ic_cost: float
    equipment_needs: Dict[str, Tuple[str, int, float]]  # eq_id -> (name_ru, count, total_ic)
    resources_needed: Dict[str, int]
    terrain_modifiers: Dict[str, Dict[str, float]]
    warnings: List[str] = field(default_factory=list)


def _resolve_equipment(tech_year: int, overrides: Dict[str, str]) -> Dict[str, Equipment]:
    defaults = get_default_equipment_for_year(tech_year)
    resolved: Dict[str, Equipment] = {}
    for cat, eq_id in defaults.items():
        chosen_id = overrides.get(cat, eq_id)
        if chosen_id in EQUIPMENT_DB:
            resolved[cat] = EQUIPMENT_DB[chosen_id]
        else:
            resolved[cat] = EQUIPMENT_DB[eq_id]
    return resolved


def _unit_combat_stats(
    eq_reqs: Dict[str, int],
    resolved_eq: Dict[str, Equipment],
    soft_mult: float,
    hard_mult: float,
    def_mult: float,
    brk_mult: float,
    air_mult: float,
    default_speed: float = 4.0,
) -> dict:
    """Compute one battalion/support unit's contribution from its equipment."""
    soft = 0.0
    hard = 0.0
    defense = 0.0
    breakthrough = 0.0
    air = 0.0
    armor_vals = []
    piercing_vals = []
    hardness_vals = []
    fuel = 0.0
    speed = default_speed

    for cat, count in eq_reqs.items():
        if cat == "support_eq" or count <= 0:
            continue
        eq = resolved_eq.get(cat)
        if not eq:
            continue
        soft += eq.soft_attack
        hard += eq.hard_attack
        defense += eq.defense
        breakthrough += eq.breakthrough
        air += eq.air_attack
        fuel += eq.fuel_consumption
        if eq.armor > 0:
            armor_vals.append(eq.armor)
        if eq.piercing > 0:
            piercing_vals.append(eq.piercing)
        if eq.hardness > 0 or cat in ("motorized", "mechanized", "light_tank", "medium_tank", "heavy_tank", "modern_tank"):
            hardness_vals.append(eq.hardness)
        if eq.max_speed > 0 and cat != "infantry_eq":
            speed = eq.max_speed

    return {
        "soft_attack": soft * soft_mult,
        "hard_attack": hard * hard_mult,
        "defense": defense * def_mult,
        "breakthrough": breakthrough * brk_mult,
        "air_attack": air * air_mult,
        "armor": max(armor_vals) if armor_vals else 0.0,
        "piercing": max(piercing_vals) if piercing_vals else 0.0,
        "hardness": max(hardness_vals) if hardness_vals else 0.0,
        "fuel": fuel,
        "speed": speed,
    }


def calculate_division_stats(template: DivisionTemplate) -> DivisionStats:
    """Calculate complete HoI4 1.19.4+ division stats and IC production costs."""
    warnings: List[str] = []
    resolved_eq = _resolve_equipment(template.tech_year, template.equipment_overrides)
    doctrine: LandDoctrine = DOCTRINE_DB.get(template.doctrine_id, DOCTRINE_DB["none"])
    lvl_idx = max(0, min(3, template.support_tech_level - 1))

    total_battalions = sum(template.battalions.values())
    if total_battalions > 25:
        warnings.append(f"Превышен лимит линейных батальонов: {total_battalions}/25.")
    if total_battalions == 0:
        warnings.append("В шаблоне нет ни одного линейного батальона.")
    if len(template.support_companies) > 5:
        warnings.append(f"Превышен лимит стандартных рот поддержки: {len(template.support_companies)}/5.")

    manpower = 0
    hp = 0.0
    combat_width = 0.0
    supply_use = 0.0
    fuel_use = 0.0
    weight = 0.0
    training_time = 0
    suppression = 0.0

    org_list: List[float] = []
    recovery_list: List[float] = []
    speed_list: List[float] = []
    armor_list: List[float] = []
    piercing_list: List[float] = []
    hardness_list: List[float] = []

    line_soft = 0.0
    line_hard = 0.0
    line_def = 0.0
    line_brk = 0.0
    line_air = 0.0

    sup_soft = 0.0
    sup_hard = 0.0
    sup_def = 0.0
    sup_brk = 0.0
    sup_air = 0.0

    eq_counts: Dict[str, int] = {}
    terrain_line_sums: Dict[str, Dict[str, float]] = {}

    # 1. Process Line Battalions
    for bat_id, count in template.battalions.items():
        if count <= 0:
            continue
        bat: Optional[Battalion] = BATTALION_DB.get(bat_id)
        if not bat:
            warnings.append(f"Неизвестный батальон: {bat_id}")
            continue

        unit_stats = _unit_combat_stats(
            bat.equipment,
            resolved_eq,
            bat.soft_attack_mult,
            bat.hard_attack_mult,
            bat.defense_mult,
            bat.breakthrough_mult,
            bat.air_attack_mult,
            bat.default_speed,
        )

        bat_width = bat.combat_width
        if bat.is_infantry_type:
            bat_width = max(0.5, bat_width + doctrine.infantry_width_delta)

        bat_org = bat.organization
        if bat.is_infantry_type or bat_id in ("motorized", "mechanized"):
            bat_org += doctrine.infantry_org_bonus
        if bat.group == "armor":
            bat_org += doctrine.armor_org_bonus

        for _ in range(count):
            manpower += bat.manpower
            hp += bat.hp
            combat_width += bat_width
            supply_use += bat.supply_use
            fuel_use += unit_stats["fuel"]
            weight += bat.weight
            training_time = max(training_time, bat.training_time)
            suppression += bat.suppression

            org_list.append(bat_org)
            recovery_list.append(bat.recovery_rate + doctrine.recovery_rate_bonus)
            speed_list.append(unit_stats["speed"])
            armor_list.append(unit_stats["armor"])
            piercing_list.append(unit_stats["piercing"])
            hardness_list.append(unit_stats["hardness"])

            line_soft += unit_stats["soft_attack"]
            line_hard += unit_stats["hard_attack"]
            line_def += unit_stats["defense"]
            line_brk += unit_stats["breakthrough"]
            line_air += unit_stats["air_attack"]

            for t_id, mods in bat.terrain_modifiers.items():
                bucket = terrain_line_sums.setdefault(t_id, {})
                for k, v in mods.items():
                    bucket[k] = bucket.get(k, 0.0) + v

            for cat, qty in bat.equipment.items():
                eq = resolved_eq.get(cat)
                if eq:
                    eq_counts[eq.id] = eq_counts.get(eq.id, 0) + qty

    # 2. Process Standard + Regimental Support Companies
    entrenchment = 5.0 + doctrine.max_entrenchment_bonus  # base 5.0 entrenchment
    recon = 0.0
    initiative = 0.0
    supply_reduction = 0.0
    fuel_reduction = 0.0
    trickleback = 0.0
    xp_loss_red = 0.0
    eq_capture = 0.0
    rel_bonus = 0.0
    suppression_mult = 1.0
    div_brk_pct = 0.0
    div_def_pct = 0.0
    div_soft_pct = 0.0

    terrain_sup_sums: Dict[str, Dict[str, float]] = {}

    all_supports = list(template.support_companies) + list(template.regimental_supports)
    for sup_id in all_supports:
        sup: Optional[SupportCompany] = SUPPORT_DB.get(sup_id)
        if not sup:
            warnings.append(f"Неизвестная рота поддержки: {sup_id}")
            continue

        unit_stats = _unit_combat_stats(
            sup.equipment,
            resolved_eq,
            sup.soft_attack_mult,
            sup.hard_attack_mult,
            sup.defense_mult,
            sup.breakthrough_mult,
            sup.air_attack_mult,
        )

        manpower += sup.manpower
        hp += sup.hp
        supply_use += sup.supply_use
        fuel_use += unit_stats["fuel"]
        weight += sup.weight
        training_time = max(training_time, sup.training_time)

        org_list.append(sup.organization)
        recovery_list.append(sup.recovery_rate)
        armor_list.append(unit_stats["armor"])
        piercing_list.append(unit_stats["piercing"])

        sup_soft += unit_stats["soft_attack"]
        sup_hard += unit_stats["hard_attack"]
        sup_def += unit_stats["defense"]
        sup_brk += unit_stats["breakthrough"]
        sup_air += unit_stats["air_attack"]

        entrenchment += sup.entrenchment_base + sup.entrenchment_per_lvl * lvl_idx
        recon += sup.recon_base + sup.recon_per_lvl * lvl_idx
        initiative += sup.initiative_base + sup.initiative_per_lvl * lvl_idx
        supply_reduction += sup.supply_reduction_base + sup.supply_reduction_per_lvl * lvl_idx
        fuel_reduction += sup.fuel_reduction_base + sup.fuel_reduction_per_lvl * lvl_idx
        trickleback += sup.trickleback_base + sup.trickleback_per_lvl * lvl_idx
        xp_loss_red += sup.xp_loss_reduction_base + sup.xp_loss_reduction_per_lvl * lvl_idx
        eq_capture += sup.equipment_capture_base + sup.equipment_capture_per_lvl * lvl_idx
        rel_bonus += sup.reliability_bonus_base + sup.reliability_bonus_per_lvl * lvl_idx
        suppression_mult += sup.suppression_mult_base + sup.suppression_mult_per_lvl * lvl_idx

        div_brk_pct += sup.div_breakthrough_pct
        div_def_pct += sup.div_defense_pct
        div_soft_pct += sup.div_soft_attack_pct

        for t_id, mods in sup.terrain_modifiers.items():
            bucket = terrain_sup_sums.setdefault(t_id, {})
            for k, v in mods.items():
                bucket[k] = bucket.get(k, 0.0) + v

        for cat, qty in sup.equipment.items():
            eq = resolved_eq.get(cat)
            if eq:
                eq_counts[eq.id] = eq_counts.get(eq.id, 0) + qty

    # 3. Aggregate Division-wide Stats
    avg_org = sum(org_list) / len(org_list) if org_list else 0.0
    avg_recovery = sum(recovery_list) / len(recovery_list) if recovery_list else 0.0
    max_speed = min(speed_list) if speed_list else 4.0
    hardness = sum(hardness_list) / len(hardness_list) if hardness_list else 0.0

    # Armor & Piercing: 40% highest + 60% average across all battalions & companies
    max_armor = max(armor_list) if armor_list else 0.0
    avg_armor = sum(armor_list) / len(armor_list) if armor_list else 0.0
    armor = 0.40 * max_armor + 0.60 * avg_armor

    max_piercing = max(piercing_list) if piercing_list else 0.0
    avg_piercing = sum(piercing_list) / len(piercing_list) if piercing_list else 0.0
    piercing = 0.40 * max_piercing + 0.60 * avg_piercing

    # Apply doctrine & support % modifiers
    total_soft = (
        line_soft * (1.0 + doctrine.soft_attack_pct + div_soft_pct)
        + sup_soft * (1.0 + doctrine.soft_attack_pct + doctrine.support_soft_attack_pct + div_soft_pct)
    )
    total_hard = (line_hard + sup_hard) * (1.0 + doctrine.hard_attack_pct)
    total_def = (line_def + sup_def) * (1.0 + doctrine.defense_pct + div_def_pct)
    total_brk = (line_brk + sup_brk) * (1.0 + doctrine.breakthrough_pct + div_brk_pct)
    total_air = line_air + sup_air

    # Supply & Fuel reductions
    supply_use = max(0.02, supply_use * (1.0 - min(0.50, supply_reduction)) * (1.0 + doctrine.supply_consumption_pct))
    fuel_use = max(0.0, fuel_use * (1.0 - min(0.50, fuel_reduction)))
    suppression = suppression * suppression_mult

    # Terrain modifiers: average over line battalions + sum of support company modifiers
    terrain_modifiers: Dict[str, Dict[str, float]] = {}
    all_terrains = set(terrain_line_sums.keys()) | set(terrain_sup_sums.keys())
    denom = max(1, total_battalions)
    for t_id in all_terrains:
        merged: Dict[str, float] = {}
        for k, v in terrain_line_sums.get(t_id, {}).items():
            merged[k] = round(v / denom, 4)
        for k, v in terrain_sup_sums.get(t_id, {}).items():
            merged[k] = round(merged.get(k, 0.0) + v, 4)
        terrain_modifiers[t_id] = merged

    # IC Cost & Resources
    equipment_needs: Dict[str, Tuple[str, int, float]] = {}
    resources_needed: Dict[str, int] = {}
    total_ic = 0.0
    for eq_id, qty in sorted(eq_counts.items()):
        eq = EQUIPMENT_DB[eq_id]
        ic = round(qty * eq.ic_cost, 2)
        total_ic += ic
        equipment_needs[eq_id] = (eq.name_ru, qty, ic)
        for res_name, res_amt in eq.resources.items():
            resources_needed[res_name] = max(resources_needed.get(res_name, 0), res_amt)

    return DivisionStats(
        name=template.name,
        battalion_count=total_battalions,
        support_count=len(template.support_companies),
        regimental_count=len(template.regimental_supports),
        combat_width=round(combat_width, 2),
        manpower=manpower,
        hp=round(hp, 1),
        organization=round(avg_org, 2),
        recovery_rate=round(avg_recovery, 3),
        max_speed=round(max_speed, 2),
        soft_attack=round(total_soft, 2),
        hard_attack=round(total_hard, 2),
        defense=round(total_def, 2),
        breakthrough=round(total_brk, 2),
        air_attack=round(total_air, 2),
        armor=round(armor, 2),
        piercing=round(piercing, 2),
        hardness=round(hardness, 3),
        supply_use=round(supply_use, 3),
        fuel_use=round(fuel_use, 2),
        weight=round(weight, 2),
        training_time=training_time,
        suppression=round(suppression, 2),
        entrenchment=round(entrenchment, 1),
        recon=round(recon, 2),
        initiative=round(initiative, 2),
        trickleback=round(trickleback, 2),
        xp_loss_reduction=round(xp_loss_red, 2),
        equipment_capture=round(eq_capture, 2),
        reliability_bonus=round(rel_bonus, 2),
        total_ic_cost=round(total_ic, 2),
        equipment_needs=equipment_needs,
        resources_needed=resources_needed,
        terrain_modifiers=terrain_modifiers,
        warnings=warnings,
    )
