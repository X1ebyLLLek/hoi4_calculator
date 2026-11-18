"""HoI4 1.19.4+ Hourly Land Battle Simulator (Offense vs Defense)."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random

from .calculator import DivisionStats, DivisionTemplate, calculate_division_stats
from ..data.doctrines_terrain import DOCTRINE_DB, TERRAIN_DB, TACTICS_DB


@dataclass
class BattleConfig:
    terrain_id: str = "plains"
    extra_flanks: int = 0          # 0..3 extra attack directions
    river: str = "none"            # "none", "minor", "major"
    fort_level: int = 0            # 0..10
    attacker_count: int = 4
    defender_count: int = 4
    attacker_planning: float = 0.30   # 0.0..0.60
    defender_entrenchment_pct: float = 1.0  # 0.0..1.0 of max entrenchment
    attacker_general_atk: int = 3
    defender_general_def: int = 3
    attacker_xp_mod: float = 0.25     # Regular = +25%
    defender_xp_mod: float = 0.25
    air_superiority: float = 0.0      # -1.0 (full defender air) to +1.0 (full attacker air)
    attacker_cas_dmg: float = 0.0     # hourly CAS org/hp pressure (0..10)
    defender_cas_dmg: float = 0.0
    supply_penalty_atk: float = 0.0   # 0.0..0.35
    supply_penalty_def: float = 0.0
    include_night: bool = True
    max_hours: int = 720              # 30 days max
    seed: Optional[int] = 42


@dataclass
class DivisionState:
    index: int
    max_hp: float
    hp: float
    max_org: float
    org: float
    in_combat: bool = False
    retreated: bool = False


@dataclass
class HourlySnapshot:
    hour: int
    attacker_avg_org_pct: float
    attacker_avg_hp_pct: float
    defender_avg_org_pct: float
    defender_avg_hp_pct: float
    attacker_active: int
    defender_active: int
    attacker_tactic: str
    defender_tactic: str


@dataclass
class SideSummary:
    name: str
    divisions_total: int
    divisions_remaining: int
    initial_manpower: int
    manpower_lost: int
    manpower_trickleback: int
    ic_lost: float
    ic_captured: float
    armor_pierced_status: str
    width_used: float
    overwidth_penalty: float


@dataclass
class BattleResult:
    winner: str  # "attacker", "defender", "draw"
    winner_ru: str
    hours_lasted: int
    days_lasted: float
    battlefield_width: float
    attacker_stats: DivisionStats
    defender_stats: DivisionStats
    attacker_summary: SideSummary
    defender_summary: SideSummary
    timeline: List[HourlySnapshot] = field(default_factory=list)
    events: List[str] = field(default_factory=list)


def _armor_damage_mult(attacker_piercing: float, defender_armor: float) -> tuple[float, float, str]:
    """Return (hp_org_dmg_mult_to_target, bonus_org_dmg_if_unpierced, status_text)."""
    if defender_armor <= 0.5:
        return 1.0, 1.0, "Без брони"
    if attacker_piercing >= defender_armor:
        return 1.0, 1.0, f"Пробито ({attacker_piercing:.1f} >= {defender_armor:.1f})"
    ratio = attacker_piercing / max(0.01, defender_armor)
    if ratio < 0.5:
        return 0.50, 1.40, f"Не пробито! ({attacker_piercing:.1f} < {defender_armor:.1f})"
    # Partial piercing between 50% and 100%
    t = (ratio - 0.5) / 0.5
    dmg_mult = 0.50 + 0.50 * t
    org_bonus = 1.40 - 0.40 * t
    return round(dmg_mult, 3), round(org_bonus, 3), f"Частичное пробитие ({attacker_piercing:.1f} / {defender_armor:.1f})"


def _select_frontline(
    divs: List[DivisionState],
    div_width: float,
    max_width: float,
) -> tuple[List[DivisionState], float, float]:
    """Fill frontline up to max_width (allowing slight over-width up to -33% penalty)."""
    active: List[DivisionState] = []
    used = 0.0
    max_allowed = max_width * 1.22  # ~33% over-width cap
    for d in divs:
        if d.retreated or d.org <= 0 or d.hp <= 0:
            d.in_combat = False
            continue
        if used == 0 or used + div_width <= max_allowed:
            d.in_combat = True
            active.append(d)
            used += div_width
        else:
            d.in_combat = False

    penalty = 0.0
    if used > max_width and max_width > 0:
        penalty = max(-0.33, -1.5 * (used - max_width) / max_width)
    return active, round(used, 2), round(penalty, 4)


def simulate_battle(
    attacker_tpl: DivisionTemplate,
    defender_tpl: DivisionTemplate,
    config: BattleConfig,
) -> BattleResult:
    """Run an hourly HoI4 1.19.4+ land battle simulation."""
    rng = random.Random(config.seed)
    atk_stats = calculate_division_stats(attacker_tpl)
    def_stats = calculate_division_stats(defender_tpl)

    atk_doc = DOCTRINE_DB.get(attacker_tpl.doctrine_id, DOCTRINE_DB["none"])
    def_doc = DOCTRINE_DB.get(defender_tpl.doctrine_id, DOCTRINE_DB["none"])
    terrain = TERRAIN_DB.get(config.terrain_id, TERRAIN_DB["plains"])

    base_battle_width = terrain.base_width + terrain.flank_width * max(0, min(3, config.extra_flanks))

    atk_divs = [
        DivisionState(i, atk_stats.hp, atk_stats.hp, max(1.0, atk_stats.organization), max(1.0, atk_stats.organization))
        for i in range(max(1, config.attacker_count))
    ]
    def_divs = [
        DivisionState(i, def_stats.hp, def_stats.hp, max(1.0, def_stats.organization), max(1.0, def_stats.organization))
        for i in range(max(1, config.defender_count))
    ]

    # Terrain, River, Fort modifiers
    atk_ter_mods = atk_stats.terrain_modifiers.get(terrain.id, {})
    def_ter_mods = def_stats.terrain_modifiers.get(terrain.id, {})

    river_base = {"none": 0.0, "minor": -0.30, "major": -0.60}.get(config.river, 0.0)
    river_mitigation = atk_stats.terrain_modifiers.get("river", {}).get("attack", 0.0)
    river_mod = min(0.0, river_base + river_mitigation) if river_base < 0 else 0.0

    fort_mitigation = atk_stats.terrain_modifiers.get("fort", {}).get("attack", 0.0)
    effective_forts = max(0, config.fort_level - config.extra_flanks)
    fort_mod = max(-0.90, -0.15 * effective_forts + fort_mitigation) if effective_forts > 0 else 0.0

    # Air superiority penalty mitigation via AA
    atk_aa_factor = min(0.75, atk_stats.air_attack / 40.0)
    def_aa_factor = min(0.75, def_stats.air_attack / 40.0)

    # Armor vs Piercing
    atk_vs_def_dmg_mult, def_unpierced_org_bonus, def_pierce_status = _armor_damage_mult(atk_stats.piercing, def_stats.armor)
    def_vs_atk_dmg_mult, atk_unpierced_org_bonus, atk_pierce_status = _armor_damage_mult(def_stats.piercing, atk_stats.armor)

    timeline: List[HourlySnapshot] = []
    events: List[str] = []

    atk_tactic = TACTICS_DB["attack"]
    def_tactic = TACTICS_DB["defend"]
    planning_left = min(config.attacker_planning, atk_doc.max_planning_bonus)
    entrench_bonus = (def_stats.entrenchment * 0.02) * config.defender_entrenchment_pct

    atk_tactics_pool = ["attack", "assault", "breakthrough", "blitz", "encirclement"]
    def_tactics_pool = ["defend", "counterattack", "elastic_defense", "ambush", "backhand_blow", "tactical_withdrawal"]

    atk_active, atk_used_w, atk_ow_pen = _select_frontline(atk_divs, max(0.5, atk_stats.combat_width), base_battle_width)
    def_active, def_used_w, def_ow_pen = _select_frontline(def_divs, max(0.5, def_stats.combat_width), base_battle_width)

    events.append(
        f"Начало боя: {terrain.name_ru} (ширина {base_battle_width}). "
        f"Атака: {len(atk_active)}/{len(atk_divs)} див. (ширина {atk_used_w}, штраф {atk_ow_pen*100:.1f}%). "
        f"Оборона: {len(def_active)}/{len(def_divs)} див. (ширина {def_used_w}, штраф {def_ow_pen*100:.1f}%)."
    )

    hours = 0
    for hour in range(1, config.max_hours + 1):
        hours = hour

        # Update combat tactics every 12 hours
        if (hour - 1) % 12 == 0:
            atk_tactic = TACTICS_DB[rng.choice(atk_tactics_pool)]
            def_tactic = TACTICS_DB[rng.choice(def_tactics_pool)]
            # Recon check: higher recon has chance to counter enemy tactic
            if atk_stats.recon > def_stats.recon and atk_tactic.countered_by == def_tactic.id:
                if rng.random() < 0.35:
                    def_tactic = TACTICS_DB["defend"]
            elif def_stats.recon > atk_stats.recon and atk_tactic.countered_by == def_tactic.id:
                if rng.random() < 0.45:
                    events.append(f"Час {hour}: Оборона (разведка {def_stats.recon:.1f}) законтрила тактику «{atk_tactic.name_ru}»!")

        cur_width = max(20.0, base_battle_width * (1.0 + atk_tactic.combat_width_mod + def_tactic.combat_width_mod))
        atk_active, atk_used_w, atk_ow_pen = _select_frontline(atk_divs, max(0.5, atk_stats.combat_width), cur_width)
        def_active, def_used_w, def_ow_pen = _select_frontline(def_divs, max(0.5, def_stats.combat_width), cur_width)

        if not atk_active or not def_active:
            break

        night_mult = 0.50 if (config.include_night and (hour % 24 >= 19 or hour % 24 <= 5)) else 1.0

        # Calculate side multipliers
        atk_atk_mult = max(
            0.10,
            (1.0 + config.attacker_xp_mod + planning_left + config.attacker_general_atk * 0.025
             + terrain.attacker_attack_mod + atk_ter_mods.get("attack", 0.0)
             + river_mod + fort_mod + atk_ow_pen - config.supply_penalty_atk + atk_tactic.attacker_dmg_mod)
            * night_mult,
        )
        atk_brk_mult = max(
            0.10,
            (1.0 + config.attacker_xp_mod + planning_left + config.attacker_general_atk * 0.025
             + atk_ow_pen - config.supply_penalty_atk
             - max(0.0, -config.air_superiority * 0.35 * (1.0 - atk_aa_factor))),
        )

        def_atk_mult = max(
            0.10,
            (1.0 + config.defender_xp_mod + entrench_bonus + config.defender_general_def * 0.025
             + def_ter_mods.get("defense", 0.0) + def_ow_pen - config.supply_penalty_def + def_tactic.defender_dmg_mod)
            * night_mult,
        )
        def_def_mult = max(
            0.10,
            (1.0 + config.defender_xp_mod + entrench_bonus + config.defender_general_def * 0.025
             + def_ter_mods.get("defense", 0.0) + def_ow_pen - config.supply_penalty_def
             - max(0.0, config.air_superiority * 0.35 * (1.0 - def_aa_factor))),
        )

        # Attacker fires on Defender
        for a in atk_active:
            target = rng.choice(def_active)
            a_hp_ratio = a.hp / a.max_hp
            t_hp_ratio = target.hp / target.max_hp

            raw_atk = (atk_stats.soft_attack * (1.0 - def_stats.hardness) + atk_stats.hard_attack * def_stats.hardness) * atk_atk_mult * a_hp_ratio
            eff_atk = raw_atk / 10.0
            eff_def = (def_stats.defense * def_def_mult * t_hp_ratio) / 10.0

            protected = min(eff_atk, eff_def)
            unprotected = max(0.0, eff_atk - eff_def)
            hits = protected * 0.10 + unprotected * 0.40

            org_dmg = hits * 0.14 * atk_vs_def_dmg_mult * atk_unpierced_org_bonus
            hp_dmg = hits * 0.065 * atk_vs_def_dmg_mult

            target.org = max(0.0, target.org - org_dmg)
            target.hp = max(0.0, target.hp - hp_dmg)

        # Defender fires on Attacker
        for d in def_active:
            target = rng.choice(atk_active)
            d_hp_ratio = d.hp / d.max_hp
            t_hp_ratio = target.hp / target.max_hp

            raw_atk = (def_stats.soft_attack * (1.0 - atk_stats.hardness) + def_stats.hard_attack * atk_stats.hardness) * def_atk_mult * d_hp_ratio
            eff_atk = raw_atk / 10.0
            eff_brk = (atk_stats.breakthrough * atk_brk_mult * t_hp_ratio) / 10.0

            protected = min(eff_atk, eff_brk)
            unprotected = max(0.0, eff_atk - eff_brk)
            hits = protected * 0.10 + unprotected * 0.40

            org_dmg = hits * 0.14 * def_vs_atk_dmg_mult * def_unpierced_org_bonus
            hp_dmg = hits * 0.065 * def_vs_atk_dmg_mult

            target.org = max(0.0, target.org - org_dmg)
            target.hp = max(0.0, target.hp - hp_dmg)

        # CAS direct pressure
        if config.attacker_cas_dmg > 0 and def_active:
            cas_eff = config.attacker_cas_dmg * (1.0 - def_aa_factor)
            for d in def_active:
                d.org = max(0.0, d.org - cas_eff * 0.08)
                d.hp = max(0.0, d.hp - cas_eff * 0.03)
        if config.defender_cas_dmg > 0 and atk_active:
            cas_eff = config.defender_cas_dmg * (1.0 - atk_aa_factor)
            for a in atk_active:
                a.org = max(0.0, a.org - cas_eff * 0.08)
                a.hp = max(0.0, a.hp - cas_eff * 0.03)

        # Check retreats
        for d in atk_divs:
            if not d.retreated and (d.org <= 0 or d.hp <= 0):
                d.retreated = True
                d.in_combat = False
        for d in def_divs:
            if not d.retreated and (d.org <= 0 or d.hp <= 0):
                d.retreated = True
                d.in_combat = False

        # Planning decays slightly per hour
        planning_left = max(0.0, planning_left - 0.0005)

        if hour == 1 or hour % 6 == 0 or all(d.retreated for d in atk_divs) or all(d.retreated for d in def_divs):
            atk_org_pct = sum(d.org / d.max_org for d in atk_divs) / len(atk_divs) * 100.0
            atk_hp_pct = sum(d.hp / d.max_hp for d in atk_divs) / len(atk_divs) * 100.0
            def_org_pct = sum(d.org / d.max_org for d in def_divs) / len(def_divs) * 100.0
            def_hp_pct = sum(d.hp / d.max_hp for d in def_divs) / len(def_divs) * 100.0
            timeline.append(
                HourlySnapshot(
                    hour=hour,
                    attacker_avg_org_pct=round(atk_org_pct, 1),
                    attacker_avg_hp_pct=round(atk_hp_pct, 1),
                    defender_avg_org_pct=round(def_org_pct, 1),
                    defender_avg_hp_pct=round(def_hp_pct, 1),
                    attacker_active=len(atk_active),
                    defender_active=len(def_active),
                    attacker_tactic=atk_tactic.name_ru,
                    defender_tactic=def_tactic.name_ru,
                )
            )

        if all(d.retreated for d in atk_divs) or all(d.retreated for d in def_divs):
            break

    atk_alive = sum(1 for d in atk_divs if not d.retreated)
    def_alive = sum(1 for d in def_divs if not d.retreated)

    if def_alive == 0 and atk_alive > 0:
        winner = "attacker"
        winner_ru = "Победа атакующего"
    elif atk_alive == 0 and def_alive > 0:
        winner = "defender"
        winner_ru = "Победа обороняющегося"
    else:
        winner = "draw"
        winner_ru = "Ничья / Позиционный тупик"

    # Calculate casualties & IC lost
    atk_hp_lost_ratio = sum(1.0 - d.hp / d.max_hp for d in atk_divs)
    def_hp_lost_ratio = sum(1.0 - d.hp / d.max_hp for d in def_divs)

    atk_raw_mp_lost = int(atk_hp_lost_ratio * atk_stats.manpower)
    def_raw_mp_lost = int(def_hp_lost_ratio * def_stats.manpower)

    atk_trickle = int(atk_raw_mp_lost * atk_stats.trickleback)
    def_trickle = int(def_raw_mp_lost * def_stats.trickleback)

    atk_ic_lost = round(atk_hp_lost_ratio * atk_stats.total_ic_cost, 2)
    def_ic_lost = round(def_hp_lost_ratio * def_stats.total_ic_cost, 2)

    atk_ic_captured = round(def_ic_lost * atk_stats.equipment_capture, 2) if winner == "attacker" else 0.0
    def_ic_captured = round(atk_ic_lost * def_stats.equipment_capture, 2) if winner == "defender" else 0.0

    atk_summary = SideSummary(
        name=atk_stats.name,
        divisions_total=len(atk_divs),
        divisions_remaining=atk_alive,
        initial_manpower=atk_stats.manpower * len(atk_divs),
        manpower_lost=max(0, atk_raw_mp_lost - atk_trickle),
        manpower_trickleback=atk_trickle,
        ic_lost=atk_ic_lost,
        ic_captured=atk_ic_captured,
        armor_pierced_status=atk_pierce_status,
        width_used=atk_used_w,
        overwidth_penalty=atk_ow_pen,
    )
    def_summary = SideSummary(
        name=def_stats.name,
        divisions_total=len(def_divs),
        divisions_remaining=def_alive,
        initial_manpower=def_stats.manpower * len(def_divs),
        manpower_lost=max(0, def_raw_mp_lost - def_trickle),
        manpower_trickleback=def_trickle,
        ic_lost=def_ic_lost,
        ic_captured=def_ic_captured,
        armor_pierced_status=def_pierce_status,
        width_used=def_used_w,
        overwidth_penalty=def_ow_pen,
    )

    events.append(f"Итог ({hours} ч / {hours/24:.1f} дн.): {winner_ru}.")

    return BattleResult(
        winner=winner,
        winner_ru=winner_ru,
        hours_lasted=hours,
        days_lasted=round(hours / 24.0, 2),
        battlefield_width=base_battle_width,
        attacker_stats=atk_stats,
        defender_stats=def_stats,
        attacker_summary=atk_summary,
        defender_summary=def_summary,
        timeline=timeline,
        events=events,
    )
