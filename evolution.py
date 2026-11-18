"""Unbiased evolutionary optimizer: discovers the optimal upgrade path from 6/0 to max-slot monster
by testing ALL valid battalion/support/regimental additions and replacements in real simulated battles.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import time

from . import gamedata
from .gamedata import GameData
from .division import DivisionTemplate, calculate_division
from .battle import BattleConfig, simulate_battle_stats
from .arena import generate_arena_templates

CANDIDATE_LINE_UNITS = [
    "infantry", "mountaineers", "artillery_brigade", "anti_tank_brigade", "anti_air_brigade",
    "motorized", "mechanized", "light_armor", "medium_armor", "heavy_armor",
    "medium_sp_artillery_brigade", "heavy_sp_artillery_brigade", "heavy_tank_destroyer_brigade",
]

CANDIDATE_SUPPORTS = [
    "engineer", "assault_engineer", "armored_engineer", "artillery", "rocket_artillery",
    "anti_air", "anti_tank", "recon", "light_tank_recon", "field_hospital",
    "logistics_company", "signal_company", "maintenance_company", "medium_flame_tank",
]

CANDIDATE_REGIMENTALS = [
    "fire_support", "mot_fire_support", "field_guns", "rocket_battery",
    "anti_air_battery", "anti_tank_battery", "medium_tank_destroyer_support",
    "heavy_tank_destroyer_support", "medium_sp_anti_air_support", "heavy_sp_anti_air_support",
]


@dataclass
class EvolutionConfig:
    tech_year: int = 1942
    terrain: str = "plains"
    doctrine: str = "grand_battleplan"
    factories: int = 15
    ic_per_factory_day: float = 3.6  # ~4.5 base * 80% average production efficiency
    goal: str = "mp_saver"  # "mp_saver" or "ic_efficient"
    max_steps: int = 28
    beam_width: int = 2
    seed: int = 42


def _tpl_key(tpl: DivisionTemplate) -> Tuple:
    return (
        tuple(sorted((k, v) for k, v in tpl.battalions.items() if v > 0)),
        tuple(sorted(tpl.support)),
        tuple(sorted(tpl.regimental)),
    )


def _clone_tpl(tpl: DivisionTemplate, name: str) -> DivisionTemplate:
    return DivisionTemplate(
        name=name,
        battalions=dict(tpl.battalions),
        support=list(tpl.support),
        regimental=list(tpl.regimental),
        tech_year=tpl.tech_year,
        doctrine=dict(tpl.doctrine),
    )


def _generate_mutations(gd: GameData, tpl: DivisionTemplate) -> List[Tuple[str, DivisionTemplate]]:
    """Generate all valid single-step mutations: add/replace battalion, add/replace support, add regimental."""
    muts: List[Tuple[str, DivisionTemplate]] = []
    line_total = sum(tpl.battalions.values())
    year = tpl.tech_year

    # 1. Add +1 line battalion
    if line_total < 25:
        for uid in CANDIDATE_LINE_UNITS:
            if uid not in gd.subunits or gd.sub_year(uid) > year:
                continue
            nt = _clone_tpl(tpl, tpl.name)
            nt.battalions[uid] = nt.battalions.get(uid, 0) + 1
            muts.append((f"+1 {gd.name(uid)}", nt))

    # 2. Replace 1 existing line battalion with another (key for upgrading without bloating width!)
    for old_uid, cnt in tpl.battalions.items():
        if cnt <= 0:
            continue
        for new_uid in CANDIDATE_LINE_UNITS:
            if new_uid == old_uid or new_uid not in gd.subunits or gd.sub_year(new_uid) > year:
                continue
            nt = _clone_tpl(tpl, tpl.name)
            nt.battalions[old_uid] -= 1
            if nt.battalions[old_uid] <= 0:
                del nt.battalions[old_uid]
            nt.battalions[new_uid] = nt.battalions.get(new_uid, 0) + 1
            muts.append((f"Замена {gd.name(old_uid)} → {gd.name(new_uid)}", nt))

    # 3. Add or upgrade standard support company (max 5, unique same_support_type)
    used_types = {
        gd.subunits[s].get("same_support_type")
        for s in tpl.support if s in gd.subunits and gd.subunits[s].get("same_support_type")
    }
    for sid in CANDIDATE_SUPPORTS:
        if sid in tpl.support or sid not in gd.subunits or gd.sub_year(sid) > year:
            continue
        stype = gd.subunits[sid].get("same_support_type")
        if stype and stype in used_types:
            # Replace existing support of the same type (e.g. engineer -> armored_engineer)
            old_sid = next(s for s in tpl.support if gd.subunits[s].get("same_support_type") == stype)
            nt = _clone_tpl(tpl, tpl.name)
            nt.support = [sid if s == old_sid else s for s in nt.support]
            muts.append((f"Апгрейд подд.: {gd.name(old_sid)} → {gd.name(sid)}", nt))
        elif len(tpl.support) < 5:
            nt = _clone_tpl(tpl, tpl.name)
            nt.support.append(sid)
            muts.append((f"+Рота: {gd.name(sid)}", nt))

    # 4. Add compatible 1.19+ regimental support (max 5)
    groups = {gd.subunits[u]["group"] for u, c in tpl.battalions.items() if c > 0 and u in gd.subunits}
    if len(tpl.regimental) < 5:
        for rid in CANDIDATE_REGIMENTALS:
            if rid in tpl.regimental or rid not in gd.subunits or gd.sub_year(rid) > year:
                continue
            allowed = gd.subunits[rid].get("allowed_battalion_groups")
            if allowed and not (groups & set(allowed if isinstance(allowed, list) else [allowed])):
                continue
            nt = _clone_tpl(tpl, tpl.name)
            nt.regimental.append(rid)
            muts.append((f"+Полковая 1.19: {gd.name(rid)}", nt))

    return muts


def _evaluate_candidate(
    gd: GameData,
    tpl: DivisionTemplate,
    atk_prepared: List[Tuple[Dict[str, Any], int]],
    terrain: str,
    battle_w: float,
    goal: str,
    seed: int,
) -> Dict[str, Any]:
    st = calculate_division(tpl, gd)
    def_cnt = max(1, round(battle_w / max(1.0, st["width"]))) + 2
    own_mp, enemy_mp, own_ic, enemy_ic, holds, wins = 0, 0, 0.0, 0.0, 0, 0
    for ast, acnt in atk_prepared:
        res = simulate_battle_stats(
            ast, st,
            BattleConfig(terrain=terrain, attacker_count=acnt, defender_count=def_cnt, max_hours=240, seed=seed),
            gd, record_timeline=False,
        )
        own_mp += res["defender_summary"]["manpower_lost"]
        enemy_mp += res["attacker_summary"]["manpower_lost"]
        own_ic += res["defender_summary"]["ic_lost"]
        enemy_ic += res["attacker_summary"]["ic_lost"]
        if res["winner"] in ("defender", "draw"):
            holds += 1
        if res["winner"] == "defender":
            wins += 1

    n = len(atk_prepared)
    mp_ratio = enemy_mp / max(1.0, own_mp)
    ic_ratio = enemy_ic / max(1.0, own_ic)
    hold_pct = holds / n * 100.0
    win_pct = wins / n * 100.0
    avg_own_mp = own_mp / n
    avg_enemy_mp = enemy_mp / n

    if goal == "ic_efficient":
        score = hold_pct * 0.7 + win_pct * 0.2 + min(6.0, ic_ratio) * 10.0 + min(5.0, mp_ratio) * 3.0
    else:  # "mp_saver": minimize own MP lost, maximize enemy MP lost, must hold!
        score = hold_pct * 0.65 + min(10.0, mp_ratio) * 14.0 + (avg_enemy_mp - avg_own_mp) / 600.0

    return {
        "stats": st,
        "def_count": def_cnt,
        "hold_pct": round(hold_pct, 1),
        "win_pct": round(win_pct, 1),
        "avg_own_mp": round(avg_own_mp, 0),
        "avg_enemy_mp": round(avg_enemy_mp, 0),
        "mp_ratio": round(mp_ratio, 2),
        "ic_ratio": round(ic_ratio, 2),
        "score": round(score, 3),
    }


def run_evolution(config: EvolutionConfig, gd: Optional[GameData] = None) -> Dict[str, Any]:
    """Run unbiased greedy/beam search from 6/0 infantry up to max-slot monster."""
    t0 = time.perf_counter()
    gd = gd or gamedata.load()
    ter = gd.terrain.get(config.terrain, gd.terrain.get("plains", {}))
    battle_w = float(ter.get("combat_width", 70))

    # Representative diverse enemy pool (infantry, arty-infantry, space marine, mobile, medium & heavy tanks)
    raw_pool = generate_arena_templates(config.tech_year, include_tanks=True, include_special=False)
    want_ids = {
        "inf_9_grand_battleplan", "inf_9_3_superior_firepower", "inf_7_2_superior_firepower",
        "sm_inf8_hvy1", "mot_9_0", "med_8_7", "hvy_8_7", "hvy_10_8",
    }
    atk_tpls = [tpl for tid, tpl, _ in raw_pool if tid in want_ids]
    if not atk_tpls:
        atk_tpls = [tpl for _, tpl, _ in raw_pool[:8]]
    atk_prepared = [
        (calculate_division(tpl, gd), max(1, round(battle_w / max(1.0, calculate_division(tpl, gd)["width"]))) + 2)
        for tpl in atk_tpls
    ]

    start_tpl = DivisionTemplate(
        name="Старт: 6/0 Пехота",
        battalions={"infantry": 6},
        support=[],
        regimental=[],
        tech_year=config.tech_year,
        doctrine={"grand": config.doctrine, "milestones": [True, True, True, True]} if config.doctrine else {},
    )

    eval_cache: Dict[Tuple, Dict[str, Any]] = {}

    def get_eval(tpl: DivisionTemplate) -> Dict[str, Any]:
        k = _tpl_key(tpl)
        if k not in eval_cache:
            eval_cache[k] = _evaluate_candidate(gd, tpl, atk_prepared, config.terrain, battle_w, config.goal, config.seed)
        return eval_cache[k]

    daily_ic = max(1.0, config.factories * config.ic_per_factory_day)

    def pack_step(step_idx: int, action: str, tpl: DivisionTemplate, ev: Dict[str, Any]) -> Dict[str, Any]:
        st = ev["stats"]
        return {
            "step": step_idx,
            "action": action,
            "width": st["width"],
            "ic_cost": st["ic_cost"],
            "factory_days_1div": round(st["ic_cost"] / daily_ic, 1),
            "factory_days_front": round(st["ic_cost"] * ev["def_count"] / daily_ic, 1),
            "hardness": round(st["hardness"] * 100, 1),
            "armor": st["armor"],
            "pierce": st["pierce"],
            "soft": st["soft"],
            "defense": st["defense"],
            "hp": st["hp"],
            "hold_pct": ev["hold_pct"],
            "avg_own_mp": ev["avg_own_mp"],
            "avg_enemy_mp": ev["avg_enemy_mp"],
            "mp_ratio": ev["mp_ratio"],
            "ic_ratio": ev["ic_ratio"],
            "score": ev["score"],
            "battalions": dict(tpl.battalions),
            "support": list(tpl.support),
            "regimental": list(tpl.regimental),
            "doctrine": config.doctrine,
        }

    start_ev = get_eval(start_tpl)
    beam: List[Tuple[DivisionTemplate, Dict[str, Any], List[Dict[str, Any]]]] = [
        (start_tpl, start_ev, [pack_step(0, "Старт: голая пехота 6/0", start_tpl, start_ev)])
    ]

    best_overall = (start_tpl, start_ev, beam[0][2])
    total_evals = 1

    for step in range(1, config.max_steps + 1):
        candidates: List[Tuple[float, str, DivisionTemplate, Dict[str, Any], List[Dict[str, Any]]]] = []
        seen_keys = set()

        for cur_tpl, cur_ev, cur_hist in beam:
            cur_score = cur_ev["score"]
            cur_ic = cur_ev["stats"]["ic_cost"]
            for action, mut_tpl in _generate_mutations(gd, cur_tpl):
                k = _tpl_key(mut_tpl)
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                ev = get_eval(mut_tpl)
                total_evals += 1
                delta_s = ev["score"] - cur_score
                if delta_s <= 0.05:
                    continue
                delta_ic = max(50.0, ev["stats"]["ic_cost"] - cur_ic)
                # Early steps favour gain per IC; later steps favour absolute combat gain toward the "monster"
                weight_ic = max(0.0, 1.0 - step / (config.max_steps * 0.7))
                rank_val = (delta_s / (delta_ic / 300.0)) * weight_ic + delta_s * (1.0 - weight_ic)
                new_hist = cur_hist + [pack_step(step, action, mut_tpl, ev)]
                candidates.append((rank_val, action, mut_tpl, ev, new_hist))

        if not candidates:
            break

        candidates.sort(key=lambda x: -x[0])
        beam = [(c[2], c[3], c[4]) for c in candidates[:config.beam_width]]
        for tpl, ev, hist in beam:
            if ev["score"] > best_overall[1]["score"]:
                best_overall = (tpl, ev, hist)

    final_tpl, final_ev, final_hist = best_overall
    return {
        "tech_year": config.tech_year,
        "terrain": gd.name(config.terrain),
        "doctrine": config.doctrine,
        "factories": config.factories,
        "ic_per_factory_day": config.ic_per_factory_day,
        "daily_ic": round(daily_ic, 1),
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "candidates_tested": total_evals,
        "steps": final_hist,
        "final_monster": final_hist[-1] if final_hist else None,
    }
