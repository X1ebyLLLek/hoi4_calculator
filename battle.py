"""HoI4 1.19.5.0+ Exact Defines-Driven Land Battle Simulator."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import random

from . import gamedata
from .gamedata import GameData
from .division import DivisionTemplate, calculate_division
from .pdx import as_list


@dataclass
class BattleConfig:
    terrain: str = "plains"
    extra_flanks: int = 0          # 0..3 extra attack directions
    river: str = "none"            # "none", "minor", "major"
    fort_level: int = 0            # 0..10
    attacker_count: int = 4
    defender_count: int = 4
    attacker_planning: float = 0.30
    defender_entrenchment_pct: float = 1.0
    attacker_general_skill: int = 3
    attacker_general_atk: int = 3
    defender_general_skill: int = 3
    defender_general_def: int = 3
    attacker_traits: List[str] = field(default_factory=list)
    defender_traits: List[str] = field(default_factory=list)
    attacker_tag: str = ""
    defender_tag: str = ""
    province_vp: int = 0
    attacker_xp_mod: float = 0.25     # Regular = +0.25
    defender_xp_mod: float = 0.25
    air_superiority: float = 0.0      # -1.0 (full defender air) to +1.0 (full attacker air)
    attacker_cas_dmg: float = 0.0     # hourly CAS pressure (0..20)
    defender_cas_dmg: float = 0.0
    supply_lack_atk: float = 0.0      # 0.0..1.0 (0 = full supply, 1 = no supply)
    supply_lack_def: float = 0.0
    include_night: bool = True
    roll_dice: bool = False           # True = exact hit/damage dice rolls; False = expected values
    max_hours: int = 720
    seed: Optional[int] = 42


@dataclass
class _DivState:
    index: int
    max_hp: float
    hp: float
    max_org: float
    org: float
    in_combat: bool = False
    retreated: bool = False


def _piercing_damage_mult(gd: GameData, piercing: float, armor: float) -> Tuple[float, bool, str]:
    """Use exact 1.19.5.0 PIERCING_THRESHOLDS & PIERCING_THRESHOLD_DAMAGE_VALUES."""
    if armor <= 0.01:
        return 1.0, False, "Без брони"
    thresholds = gd.defines.get("PIERCING_THRESHOLDS", [1.0, 0.75, 0.5, 0.0])
    values = gd.defines.get("PIERCING_THRESHOLD_DAMAGE_VALUES", [1.0, 0.8, 0.65, 0.5])
    ratio = piercing / armor
    dmg_mult = values[-1]
    for thr, val in zip(thresholds, values):
        if ratio >= thr:
            dmg_mult = val
            break
    unpierced = ratio < 1.0
    if ratio >= 1.0:
        status = f"Пробито ({piercing:.1f} >= {armor:.1f})"
    elif ratio >= 0.5:
        status = f"Частично ({piercing:.1f} / {armor:.1f}, урон {int(dmg_mult*100)}%)"
    else:
        status = f"Не пробито! ({piercing:.1f} < {armor:.1f}, урон {int(dmg_mult*100)}%)"
    return dmg_mult, unpierced, status


def _eval_cmp(actual: float, spec: Any) -> bool:
    """Evaluate a Paradox numeric comparison (e.g. ``{"op": ">", "value": 2}``)."""
    if isinstance(spec, dict) and "op" in spec and "value" in spec:
        op = spec["op"]
        target = float(spec["value"])
        if op == ">":
            return actual > target
        if op == "<":
            return actual < target
        if op == ">=":
            return actual >= target
        if op == "<=":
            return actual <= target
        if op in ("=", "=="):
            return actual == target
        if op == "!=":
            return actual != target
        return False
    return actual == float(spec)


def _eval_trigger_item(key: str, val: Any, ctx: Dict[str, Any], gd: GameData) -> bool:
    if key == "AND":
        return _eval_trigger_block(val, ctx, gd, mode="AND")
    if key == "OR":
        return _eval_trigger_block(val, ctx, gd, mode="OR")
    if key == "NOT":
        # Paradox NOT = { A B } is NOR (true iff none of the conditions hold).
        return not _eval_trigger_block(val, ctx, gd, mode="OR")
    if key in ("OWNER", "custom_trigger_tooltip"):
        return _eval_trigger_block(val, ctx, gd, mode="AND")
    if key == "tooltip":
        return True
    if key == "is_attacker":
        return bool(val) == ctx["is_attacker"]
    if key == "phase":
        if val in (False, "no"):
            return ctx["phase"] == "no"
        return ctx["phase"] == str(val)
    if key == "skill":
        return _eval_cmp(ctx["skill"], val)
    if key == "skill_advantage":
        return _eval_cmp(ctx["skill_adv"], val)
    if key == "frontage_full":
        return bool(val) == ctx["frontage_full"]
    if key == "has_reserves":
        return bool(val) == ctx["has_reserves"]
    if key == "hardness":
        return _eval_cmp(ctx["hardness"], val)
    if key == "has_artillery_ratio":
        return _eval_cmp(ctx["arty_ratio"], val)
    if key == "is_fighting_in_terrain":
        return str(val) == ctx["terrain_id"]
    if key == "has_combat_modifier":
        if val == "river_crossing":
            return bool(ctx["has_river"])
        return False
    if key == "has_trait":
        return str(val) in ctx["traits"]
    if key == "tag":
        return bool(ctx["tag"]) and ctx["tag"].upper() == str(val).upper()
    if key == "has_tactic":
        tid = str(val)
        return tid in ctx["unlocked"] or bool(gd.tactics.get(tid, {}).get("active", False))
    if key == "has_unit_type":
        return str(val) in ctx["unit_types"]
    if key == "province_vp":
        return _eval_cmp(ctx["province_vp"], val)
    return False


def _eval_trigger_block(block: Any, ctx: Dict[str, Any], gd: GameData, mode: str = "AND") -> bool:
    if not block:
        return True if mode == "AND" else False
    if isinstance(block, list):
        results = [_eval_trigger_block(sub, ctx, gd, mode="AND") for sub in block]
        return all(results) if mode == "AND" else any(results)
    if not isinstance(block, dict):
        return False

    results: List[bool] = []
    for key, val in block.items():
        if key == "tooltip":
            continue
        if isinstance(val, list):
            for item in val:
                results.append(_eval_trigger_item(key, item, ctx, gd))
        else:
            results.append(_eval_trigger_item(key, val, ctx, gd))

    if not results:
        return True if mode == "AND" else False
    return all(results) if mode == "AND" else any(results)


def _eval_tactic_weight(base: Any, ctx: Dict[str, Any], gd: GameData) -> float:
    if not isinstance(base, dict):
        return 1.0
    w = float(base.get("factor", 1.0))
    for mod in as_list(base.get("modifier")):
        if not isinstance(mod, dict):
            continue
        cond = {k: v for k, v in mod.items() if k not in ("add", "factor")}
        if _eval_trigger_block(cond, ctx, gd, mode="AND"):
            if "add" in mod:
                w += float(mod["add"])
            if "factor" in mod:
                w *= float(mod["factor"])
    return max(0.0, w)


def _aa_air_sup_reduction(aa: float, max_red: float, steepness: float) -> float:
    """Exact HoI4 diminishing-returns curve from 00_defines.lua: a * (xp / (xp + b)), xp = aa^1.5."""
    if aa <= 0.0 or max_red <= 0.0:
        return 0.0
    xp = aa ** 1.5
    return max_red * (xp / (xp + max(1e-6, steepness)))


def _roll_hits(n_attacks: float, hit_chance: float, rng: random.Random) -> int:
    """Resolve fractional attack count into exact Bernoulli hit rolls."""
    if n_attacks <= 0.0 or hit_chance <= 0.0:
        return 0
    trials = int(n_attacks)
    if rng.random() < (n_attacks - trials):
        trials += 1
    if hit_chance >= 1.0:
        return trials
    return sum(1 for _ in range(trials) if rng.random() < hit_chance)


def _resolve_damage(
    t_atk: float,
    t_def: float,
    hit_prot: float,
    hit_unprot: float,
    org_dice_size: float,
    str_dice_size: float,
    org_mod: float,
    str_mod: float,
    dmg_mult: float,
    rng: random.Random,
    roll_dice: bool,
) -> Tuple[float, float]:
    """Compute (org_dmg, str_dmg) using either expected values or exact game dice rolls."""
    prot_atk = min(t_atk, t_def)
    unprot_atk = max(0.0, t_atk - t_def)
    if not roll_dice:
        hits = prot_atk * hit_prot + unprot_atk * hit_unprot
        o_avg = (1.0 + org_dice_size) / 2.0
        s_avg = (1.0 + str_dice_size) / 2.0
        return hits * org_mod * o_avg * dmg_mult, hits * str_mod * s_avg * dmg_mult

    hits = _roll_hits(prot_atk, hit_prot, rng) + _roll_hits(unprot_atk, hit_unprot, rng)
    if hits <= 0:
        return 0.0, 0.0
    o_sides = max(1, int(round(org_dice_size)))
    s_sides = max(1, int(round(str_dice_size)))
    o_pips = sum(rng.randint(1, o_sides) for _ in range(hits))
    s_pips = sum(rng.randint(1, s_sides) for _ in range(hits))
    return o_pips * org_mod * dmg_mult, s_pips * str_mod * dmg_mult


def _pick_tactic(
    gd: GameData,
    rng: random.Random,
    is_attacker: bool,
    phase: str,
    unlocked: set,
    hardness: float,
    arty_ratio: float,
    skill: int,
    skill_adv: int,
    frontage_full: bool,
    has_reserves: bool,
    terrain_id: str,
    *,
    has_river: bool = False,
    traits: Optional[Iterable[str]] = None,
    tag: str = "",
    unit_types: Optional[Iterable[str]] = None,
    province_vp: int = 0,
) -> Tuple[str, dict]:
    """Pick an eligible combat tactic from extracted 1.19.5.0 tactics using full trigger evaluation."""
    ctx: Dict[str, Any] = {
        "is_attacker": is_attacker,
        "phase": phase,
        "unlocked": set(unlocked),
        "hardness": hardness,
        "arty_ratio": arty_ratio,
        "skill": float(skill),
        "skill_adv": float(skill_adv),
        "frontage_full": frontage_full,
        "has_reserves": has_reserves,
        "terrain_id": terrain_id,
        "has_river": has_river,
        "traits": set(traits or ()),
        "tag": tag or "",
        "unit_types": set(unit_types or ()),
        "province_vp": float(province_vp),
    }

    cands: List[Tuple[str, dict, float]] = []
    for tid, t in gd.tactics.items():
        if bool(t.get("is_attacker")) != is_attacker:
            continue
        if not t.get("active", True) and tid not in unlocked:
            continue
        trig = t.get("trigger") or {}
        if not _eval_trigger_block(trig, ctx, gd, mode="AND"):
            continue
        w = _eval_tactic_weight(t.get("base"), ctx, gd)
        if w > 0:
            cands.append((tid, t, w))

    if not cands:
        fallback = "tactic_basic_attack" if is_attacker else "tactic_basic_defend"
        return fallback, gd.tactics.get(fallback, {})

    total_w = sum(w for _, _, w in cands)
    r = rng.random() * total_w
    acc = 0.0
    for tid, t, w in cands:
        acc += w
        if r <= acc:
            return tid, t
    return cands[-1][0], cands[-1][1]


def _select_frontline(
    gd: GameData,
    divs: List[_DivState],
    div_width: float,
    max_width: float,
    extra_flanks: int,
    reinforce_chance: float,
    rng: random.Random,
    initial: bool = False,
) -> Tuple[List[_DivState], float, float, float]:
    """Fill frontline up to max_width; reserves enter via reinforce_chance."""
    max_ow = abs(gd.d("COMBAT_OVER_WIDTH_PENALTY_MAX", -0.33))
    ow_slope = abs(gd.d("COMBAT_OVER_WIDTH_PENALTY", -1.0))
    max_allowed = max_width * (1.0 + max_ow / max(0.01, ow_slope))

    active = [d for d in divs if d.in_combat and not d.retreated and d.org > 0 and d.hp > 0]
    used = len(active) * div_width

    for d in divs:
        if d.in_combat or d.retreated or d.org <= 0 or d.hp <= 0:
            continue
        if used == 0 or used + div_width <= max_allowed:
            if initial or used == 0 or rng.random() < reinforce_chance:
                d.in_combat = True
                active.append(d)
                used += div_width

    ow_pen = 0.0
    if used > max_width and max_width > 0:
        ow_pen = max(-max_ow, -ow_slope * (used - max_width) / max_width)

    stack_start = gd.d("COMBAT_STACKING_START", 5) + gd.d("COMBAT_STACKING_EXTRA", 3) * extra_flanks
    stack_pen = 0.0
    if len(active) > stack_start:
        stack_pen = (len(active) - stack_start) * gd.d("COMBAT_STACKING_PENALTY", -0.02)

    return active, round(used, 2), round(ow_pen, 4), round(stack_pen, 4)


def simulate_battle(
    attacker_tpl: DivisionTemplate,
    defender_tpl: DivisionTemplate,
    config: BattleConfig,
    gd: Optional[GameData] = None,
) -> Dict[str, Any]:
    """Run an hourly HoI4 1.19.5.0+ land battle simulation."""
    gd = gd or gamedata.load()
    atk_stats = calculate_division(attacker_tpl, gd)
    def_stats = calculate_division(defender_tpl, gd)
    return simulate_battle_stats(atk_stats, def_stats, config, gd, record_timeline=True)


def simulate_battle_stats(
    atk_stats: Dict[str, Any],
    def_stats: Dict[str, Any],
    config: BattleConfig,
    gd: Optional[GameData] = None,
    record_timeline: bool = True,
) -> Dict[str, Any]:
    """Run an hourly HoI4 1.19.5.0+ land battle using precalculated division stats."""
    gd = gd or gamedata.load()
    rng = random.Random(config.seed)

    ter = gd.terrain.get(config.terrain, gd.terrain.get("plains", {}))
    base_w = float(ter.get("combat_width", 70))
    flank_w = float(ter.get("combat_support_width", 35))
    battle_w = base_w + flank_w * max(0, min(3, config.extra_flanks))
    ter_atk_mod = float((ter.get("units") or {}).get("attack", 0.0))

    atk_divs = [
        _DivState(i, max(1.0, atk_stats["hp"]), max(1.0, atk_stats["hp"]),
                  max(1.0, atk_stats["org"]), max(1.0, atk_stats["org"]))
        for i in range(max(1, config.attacker_count))
    ]
    def_divs = [
        _DivState(i, max(1.0, def_stats["hp"]), max(1.0, def_stats["hp"]),
                  max(1.0, def_stats["org"]), max(1.0, def_stats["org"]))
        for i in range(max(1, config.defender_count))
    ]

    # Terrain & Fort & River modifiers
    atk_tmods = atk_stats["terrain"].get(config.terrain, {})
    def_tmods = def_stats["terrain"].get(config.terrain, {})

    river_pen = 0.0
    if config.river == "minor":
        river_pen = gd.d("RIVER_CROSSING_PENALTY", -0.3)
    elif config.river == "major":
        river_pen = gd.d("RIVER_CROSSING_PENALTY_LARGE", -0.6)
    if river_pen < 0:
        river_pen = min(0.0, river_pen + atk_stats["terrain"].get("river", {}).get("attack", 0.0))

    fort_pen = 0.0
    eff_forts = max(0, config.fort_level - config.extra_flanks)
    if eff_forts > 0:
        fort_pen = max(-0.90, gd.d("BASE_FORT_PENALTY", -0.15) * eff_forts
                       + atk_stats["terrain"].get("fort", {}).get("attack", 0.0))

    # Entrenchment & Planning
    dig_in_cap = gd.d("UNIT_DIGIN_CAP", 5.0) + def_stats["entrenchment"]
    dig_in_bonus = dig_in_cap * gd.d("DIG_IN_FACTOR", 0.02) * max(0.0, min(1.0, config.defender_entrenchment_pct))
    max_plan = gd.d("PLANNING_MAX", 0.30) + atk_stats["scalar"].get("max_planning", 0.0)
    planning_left = min(config.attacker_planning, max_plan)
    planning_decay_hr = gd.d("PLANNING_DECAY", 0.01) / 24.0 * (1.0 + atk_stats["scalar"].get("planning_decay_rate_factor", 0.0))

    # Leader attack / defense skill bonuses from common/unit_leader/
    atk_gen_bonus = gd.leader_skill_bonus("attack", config.attacker_general_atk)
    def_gen_bonus = gd.leader_skill_bonus("defense", config.defender_general_def)

    # Air superiority & AA mitigation from 00_defines.lua
    air_sup_impact = abs(gd.d("ENEMY_AIR_SUPERIORITY_IMPACT", -0.35))
    aa_sup_max = gd.d("ENEMY_AIR_SUPERIORITY_DEFENSE", 0.75)
    aa_sup_steep = gd.d("ENEMY_AIR_SUPERIORITY_DEFENSE_STEEPNESS", 625.0)
    atk_air_sup_aa_red = _aa_air_sup_reduction(atk_stats["air"], aa_sup_max, aa_sup_steep)
    def_air_sup_aa_red = _aa_air_sup_reduction(def_stats["air"], aa_sup_max, aa_sup_steep)

    aa_cas_max = gd.d(
        "ANTI_AIR_MAXIMUM_DAMAGE_REDUCTION_FACTOR",
        gd.d("MAX_ANTI_AIR_REDUCTION_EFFECT_ON_INCOMING_AIR_DAMAGE", 0.75),
    )
    aa_cas_factor = gd.d("ANTI_AIR_ATTACK_TO_DAMAGE_REDUCTION_FACTOR", 2.5) / 100.0
    atk_cas_aa_red = min(aa_cas_max, atk_stats["air"] * aa_cas_factor)
    def_cas_aa_red = min(aa_cas_max, def_stats["air"] * aa_cas_factor)
    air_ter_factor = 1.0 + float(ter.get("enemy_army_bonus_air_superiority_factor", 0.0))

    # Armor vs Piercing
    atk_vs_def_dmg_mult, def_unpierced, def_pierce_status = _piercing_damage_mult(gd, atk_stats["pierce"], def_stats["armor"])
    def_vs_atk_dmg_mult, atk_unpierced, atk_pierce_status = _piercing_damage_mult(gd, def_stats["pierce"], atk_stats["armor"])

    # Reinforce rates
    base_reinf = gd.d("REINFORCE_CHANCE", 0.02)
    init_factor = gd.d("ARMY_INITIATIVE_REINFORCE_FACTOR", 0.25)
    atk_reinf = base_reinf + atk_stats["scalar"].get("land_reinforce_rate", 0.0) + atk_stats["initiative"] * init_factor
    def_reinf = base_reinf + def_stats["scalar"].get("land_reinforce_rate", 0.0) + def_stats["initiative"] * init_factor

    # Defines for damage resolution
    str_mod = gd.d("LAND_COMBAT_STR_DAMAGE_MODIFIER", 0.060)
    org_mod = gd.d("LAND_COMBAT_ORG_DAMAGE_MODIFIER", 0.053)
    str_dice_size = gd.d("LAND_COMBAT_STR_DICE_SIZE", 2.0)
    org_dice_size = gd.d("LAND_COMBAT_ORG_DICE_SIZE", 4.0)
    org_armor_dice_size = gd.d("LAND_COMBAT_ORG_ARMOR_ON_SOFT_DICE_SIZE", 6.0)
    str_armor_dice_size = gd.d("LAND_COMBAT_STR_ARMOR_ON_SOFT_DICE_SIZE", 2.0)
    cas_org_dmg_mod = gd.d("LAND_AIR_COMBAT_ORG_DAMAGE_MODIFIER", 0.035)
    cas_str_dmg_mod = gd.d("LAND_AIR_COMBAT_STR_DAMAGE_MODIFIER", 0.035)
    cas_org_dice_size = gd.d("LAND_AIR_COMBAT_ORG_DICE_SIZE", 5.0)
    cas_str_dice_size = gd.d("LAND_AIR_COMBAT_STR_DICE_SIZE", 2.0)

    hit_prot = (100.0 - gd.d("BASE_CHANCE_TO_AVOID_HIT", 90.0)) / 100.0
    hit_unprot = (100.0 - gd.d("CHANCE_TO_AVOID_HIT_AT_NO_DEF", 60.0)) / 100.0
    night_pen = gd.d("BASE_NIGHT_ATTACK_PENALTY", -0.50)
    tactic_swap_hrs = int(gd.d("TACTIC_SWAP_FREQUENCEY", 12))
    recon_impact = gd.d("RECON_SKILL_IMPACT", 5.0)
    first_split = gd.d("DAMAGE_SPLIT_ON_FIRST_TARGET", 0.35)

    atk_unlocked = set(atk_stats["tactics"])
    def_unlocked = set(def_stats["tactics"])
    atk_unit_types: Set[str] = {u["id"] for u in atk_stats.get("units", []) if isinstance(u, dict) and "id" in u}
    def_unit_types: Set[str] = {u["id"] for u in def_stats.get("units", []) if isinstance(u, dict) and "id" in u}
    has_river = config.river != "none"

    atk_active, atk_used_w, atk_ow_pen, atk_stk_pen = _select_frontline(
        gd, atk_divs, max(0.5, atk_stats["width"]), battle_w, config.extra_flanks, 1.0, rng, initial=True
    )
    def_active, def_used_w, def_ow_pen, def_stk_pen = _select_frontline(
        gd, def_divs, max(0.5, def_stats["width"]), battle_w, config.extra_flanks, 1.0, rng, initial=True
    )

    events = [
        f"Начало боя: {gd.name(config.terrain)} (ширина {battle_w}). "
        f"Атака: {len(atk_active)}/{len(atk_divs)} див. (шир. {atk_used_w}, переполн. {atk_ow_pen*100:.1f}%). "
        f"Оборона: {len(def_active)}/{len(def_divs)} див. (шир. {def_used_w}, переполн. {def_ow_pen*100:.1f}%)."
    ]
    timeline: List[Dict[str, Any]] = []

    phase = "no"
    atk_tid, atk_tac = "tactic_basic_attack", gd.tactics.get("tactic_basic_attack", {})
    def_tid, def_tac = "tactic_basic_defend", gd.tactics.get("tactic_basic_defend", {})
    atk_countered = False
    def_countered = False

    hours = 0
    for hour in range(1, config.max_hours + 1):
        hours = hour

        # Swap tactics every TACTIC_SWAP_FREQUENCEY hours
        if (hour - 1) % tactic_swap_hrs == 0:
            atk_eff_skill = config.attacker_general_skill + (recon_impact if atk_stats["recon"] > def_stats["recon"] else 0)
            def_eff_skill = config.defender_general_skill + (recon_impact if def_stats["recon"] > atk_stats["recon"] else 0)
            atk_tid, atk_tac = _pick_tactic(
                gd, rng, True, phase, atk_unlocked, atk_stats["hardness"], atk_stats["artillery_ratio"],
                int(atk_eff_skill), int(atk_eff_skill - def_eff_skill),
                atk_used_w >= battle_w * 0.9, len(atk_divs) > len(atk_active), config.terrain,
                has_river=has_river, traits=config.attacker_traits, tag=config.attacker_tag,
                unit_types=atk_unit_types, province_vp=config.province_vp,
            )
            def_tid, def_tac = _pick_tactic(
                gd, rng, False, phase, def_unlocked, def_stats["hardness"], def_stats["artillery_ratio"],
                int(def_eff_skill), int(def_eff_skill - atk_eff_skill),
                def_used_w >= battle_w * 0.9, len(def_divs) > len(def_active), config.terrain,
                has_river=has_river, traits=config.defender_traits, tag=config.defender_tag,
                unit_types=def_unit_types, province_vp=config.province_vp,
            )
            if atk_tac.get("phase"):
                phase = "no" if atk_tac["phase"] is False else str(atk_tac["phase"])
            elif def_tac.get("phase"):
                phase = "no" if def_tac["phase"] is False else str(def_tac["phase"])
            atk_countered = (atk_tac.get("countered_by") == def_tid)
            def_countered = (def_tac.get("countered_by") == atk_tid)

        cur_w = max(20.0, battle_w * (1.0 + float(atk_tac.get("combat_width", 0.0)) + float(def_tac.get("combat_width", 0.0))))
        atk_active, atk_used_w, atk_ow_pen, atk_stk_pen = _select_frontline(
            gd, atk_divs, max(0.5, atk_stats["width"]), cur_w, config.extra_flanks, atk_reinf, rng
        )
        def_active, def_used_w, def_ow_pen, def_stk_pen = _select_frontline(
            gd, def_divs, max(0.5, def_stats["width"]), cur_w, config.extra_flanks, def_reinf, rng
        )
        if not atk_active or not def_active:
            break

        is_night = config.include_night and (hour % 24 >= 19 or hour % 24 <= 5)
        night_mult = (1.0 + night_pen) if is_night else 1.0

        atk_tac_mod = 0.0 if atk_countered else float(atk_tac.get("attacker", 0.0))
        def_tac_mod = 0.0 if def_countered else float(def_tac.get("defender", 0.0))

        # Supply penalties
        sup_atk_a = config.supply_lack_atk * gd.d("COMBAT_SUPPLY_LACK_ATTACKER_ATTACK", -0.25)
        sup_atk_d = config.supply_lack_atk * gd.d("COMBAT_SUPPLY_LACK_ATTACKER_DEFEND", -0.65)
        sup_def_a = config.supply_lack_def * gd.d("COMBAT_SUPPLY_LACK_DEFENDER_ATTACK", -0.35)
        sup_def_d = config.supply_lack_def * gd.d("COMBAT_SUPPLY_LACK_DEFENDER_DEFEND", -0.15)

        atk_atk_mult = max(0.10, (
            1.0 + config.attacker_xp_mod + planning_left + atk_gen_bonus
            + ter_atk_mod + atk_tmods.get("attack", 0.0) + river_pen + fort_pen
            + atk_ow_pen + atk_stk_pen + sup_atk_a + atk_tac_mod
        ) * night_mult)

        atk_brk_mult = max(0.10, (
            1.0 + config.attacker_xp_mod + planning_left + atk_gen_bonus
            + atk_ow_pen + atk_stk_pen + sup_atk_d
            - max(0.0, -config.air_superiority * air_sup_impact * air_ter_factor * (1.0 - atk_air_sup_aa_red))
        ))

        def_atk_mult = max(0.10, (
            1.0 + config.defender_xp_mod + dig_in_bonus + def_gen_bonus
            + def_tmods.get("defence", 0.0) + def_ow_pen + def_stk_pen + sup_def_a + def_tac_mod
        ) * night_mult)

        def_def_mult = max(0.10, (
            1.0 + config.defender_xp_mod + dig_in_bonus + def_gen_bonus
            + def_tmods.get("defence", 0.0) + def_ow_pen + def_stk_pen + sup_def_d
            - max(0.0, config.air_superiority * air_sup_impact * air_ter_factor * (1.0 - def_air_sup_aa_red))
        ))

        # Attacker fires on Defender (spread with DAMAGE_SPLIT_ON_FIRST_TARGET)
        for a in atk_active:
            a_hp_r = a.hp / a.max_hp
            raw_atk = (atk_stats["soft"] * (1.0 - def_stats["hardness"]) + atk_stats["hard"] * def_stats["hardness"]) * atk_atk_mult * a_hp_r
            eff_atk = raw_atk / 10.0

            primary = rng.choice(def_active)
            targets = [(primary, first_split if len(def_active) > 1 else 1.0)]
            if len(def_active) > 1:
                rest_share = (1.0 - first_split) / (len(def_active) - 1)
                for other in def_active:
                    if other is not primary:
                        targets.append((other, rest_share))

            o_size = org_armor_dice_size if atk_unpierced else org_dice_size
            s_size = str_armor_dice_size if atk_unpierced else str_dice_size
            for tgt, share in targets:
                t_atk = eff_atk * share
                t_def = (def_stats["defense"] * def_def_mult * (tgt.hp / tgt.max_hp)) / 10.0 * share
                org_dmg, str_dmg = _resolve_damage(
                    t_atk, t_def, hit_prot, hit_unprot, o_size, s_size,
                    org_mod, str_mod, atk_vs_def_dmg_mult, rng, config.roll_dice,
                )
                tgt.org = max(0.0, tgt.org - org_dmg)
                tgt.hp = max(0.0, tgt.hp - str_dmg)

        # Defender fires on Attacker
        for d in def_active:
            d_hp_r = d.hp / d.max_hp
            raw_atk = (def_stats["soft"] * (1.0 - atk_stats["hardness"]) + def_stats["hard"] * atk_stats["hardness"]) * def_atk_mult * d_hp_r
            eff_atk = raw_atk / 10.0

            primary = rng.choice(atk_active)
            targets = [(primary, first_split if len(atk_active) > 1 else 1.0)]
            if len(atk_active) > 1:
                rest_share = (1.0 - first_split) / (len(atk_active) - 1)
                for other in atk_active:
                    if other is not primary:
                        targets.append((other, rest_share))

            o_size = org_armor_dice_size if def_unpierced else org_dice_size
            s_size = str_armor_dice_size if def_unpierced else str_dice_size
            for tgt, share in targets:
                t_atk = eff_atk * share
                t_brk = (atk_stats["brk"] * atk_brk_mult * (tgt.hp / tgt.max_hp)) / 10.0 * share
                org_dmg, str_dmg = _resolve_damage(
                    t_atk, t_brk, hit_prot, hit_unprot, o_size, s_size,
                    org_mod, str_mod, def_vs_atk_dmg_mult, rng, config.roll_dice,
                )
                tgt.org = max(0.0, tgt.org - org_dmg)
                tgt.hp = max(0.0, tgt.hp - str_dmg)

        # CAS pressure
        cas_night = gd.d("CAS_NIGHT_ATTACK_FACTOR", 0.1) if is_night else 1.0
        if config.attacker_cas_dmg > 0 and def_active:
            eff_cas = config.attacker_cas_dmg * cas_night * (1.0 - def_cas_aa_red)
            for d in def_active:
                o_roll = rng.randint(1, max(1, int(round(cas_org_dice_size)))) if config.roll_dice else (1.0 + cas_org_dice_size) / 2.0
                s_roll = rng.randint(1, max(1, int(round(cas_str_dice_size)))) if config.roll_dice else (1.0 + cas_str_dice_size) / 2.0
                d.org = max(0.0, d.org - eff_cas * cas_org_dmg_mod * o_roll)
                d.hp = max(0.0, d.hp - eff_cas * cas_str_dmg_mod * s_roll)
        if config.defender_cas_dmg > 0 and atk_active:
            eff_cas = config.defender_cas_dmg * cas_night * (1.0 - atk_cas_aa_red)
            for a in atk_active:
                o_roll = rng.randint(1, max(1, int(round(cas_org_dice_size)))) if config.roll_dice else (1.0 + cas_org_dice_size) / 2.0
                s_roll = rng.randint(1, max(1, int(round(cas_str_dice_size)))) if config.roll_dice else (1.0 + cas_str_dice_size) / 2.0
                a.org = max(0.0, a.org - eff_cas * cas_org_dmg_mod * o_roll)
                a.hp = max(0.0, a.hp - eff_cas * cas_str_dmg_mod * s_roll)

        for d in atk_divs:
            if not d.retreated and (d.org <= 0 or d.hp <= 0):
                d.retreated = True
                d.in_combat = False
        for d in def_divs:
            if not d.retreated and (d.org <= 0 or d.hp <= 0):
                d.retreated = True
                d.in_combat = False

        planning_left = max(0.0, planning_left - planning_decay_hr)

        if record_timeline and (hour == 1 or hour % 6 == 0 or all(d.retreated for d in atk_divs) or all(d.retreated for d in def_divs)):
            timeline.append({
                "hour": hour,
                "attacker_avg_org_pct": round(sum(d.org / d.max_org for d in atk_divs) / len(atk_divs) * 100.0, 1),
                "attacker_avg_hp_pct": round(sum(d.hp / d.max_hp for d in atk_divs) / len(atk_divs) * 100.0, 1),
                "defender_avg_org_pct": round(sum(d.org / d.max_org for d in def_divs) / len(def_divs) * 100.0, 1),
                "defender_avg_hp_pct": round(sum(d.hp / d.max_hp for d in def_divs) / len(def_divs) * 100.0, 1),
                "attacker_active": len(atk_active),
                "defender_active": len(def_active),
                "attacker_tactic": gd.name(atk_tid),
                "defender_tactic": gd.name(def_tid),
            })

        if all(d.retreated for d in atk_divs) or all(d.retreated for d in def_divs):
            break

    atk_alive = sum(1 for d in atk_divs if not d.retreated)
    def_alive = sum(1 for d in def_divs if not d.retreated)
    if def_alive == 0 and atk_alive > 0:
        winner, winner_ru = "attacker", "Победа атакующего"
    elif atk_alive == 0 and def_alive > 0:
        winner, winner_ru = "defender", "Победа обороняющегося"
    else:
        winner, winner_ru = "draw", "Ничья / Позиционный тупик"

    eq_loss_factor = gd.d("EQUIPMENT_COMBAT_LOSS_FACTOR", 0.70)
    atk_hp_lost = sum(1.0 - d.hp / d.max_hp for d in atk_divs)
    def_hp_lost = sum(1.0 - d.hp / d.max_hp for d in def_divs)

    atk_mp_raw = int(atk_hp_lost * atk_stats["manpower"])
    def_mp_raw = int(def_hp_lost * def_stats["manpower"])
    atk_trickle = int(atk_mp_raw * atk_stats["trickleback"])
    def_trickle = int(def_mp_raw * def_stats["trickleback"])

    atk_ic_lost = round(atk_hp_lost * atk_stats["ic_cost"] * eq_loss_factor, 2)
    def_ic_lost = round(def_hp_lost * def_stats["ic_cost"] * eq_loss_factor, 2)

    atk_ic_cap = round(def_ic_lost * atk_stats["capture"], 2) if winner == "attacker" else 0.0
    def_ic_cap = round(atk_ic_lost * def_stats["capture"], 2) if winner == "defender" else 0.0

    events.append(f"Итог ({hours} ч / {hours / 24:.1f} дн.): {winner_ru}.")

    return {
        "winner": winner,
        "winner_ru": winner_ru,
        "hours_lasted": hours,
        "days_lasted": round(hours / 24.0, 2),
        "battlefield_width": battle_w,
        "attacker_stats": atk_stats,
        "defender_stats": def_stats,
        "attacker_summary": {
            "name": atk_stats["name"],
            "divisions_total": len(atk_divs),
            "divisions_remaining": atk_alive,
            "manpower_lost": max(0, atk_mp_raw - atk_trickle),
            "manpower_trickleback": atk_trickle,
            "ic_lost": atk_ic_lost,
            "ic_captured": atk_ic_cap,
            "armor_pierced_status": atk_pierce_status,
            "width_used": atk_used_w,
            "overwidth_penalty": atk_ow_pen,
        },
        "defender_summary": {
            "name": def_stats["name"],
            "divisions_total": len(def_divs),
            "divisions_remaining": def_alive,
            "manpower_lost": max(0, def_mp_raw - def_trickle),
            "manpower_trickleback": def_trickle,
            "ic_lost": def_ic_lost,
            "ic_captured": def_ic_cap,
            "armor_pierced_status": def_pierce_status,
            "width_used": def_used_w,
            "overwidth_penalty": def_ow_pen,
        },
        "timeline": timeline,
        "events": events,
    }
