from hoi4_calculator.gamedata import load
from hoi4_calculator.division import DivisionTemplate, calculate_division
from hoi4_calculator.battle import BattleConfig, simulate_battle
from hoi4_calculator.arena import ArenaConfig, run_arena, run_fullslot_and_upgrade_study
from hoi4_calculator.budget_curve import BudgetCurveConfig, run_budget_curve
from hoi4_calculator.evolution import EvolutionConfig, run_evolution
from hoi4_calculator.presets import PRESETS
from hoi4_calculator.tanks import default_modules, design_tank


def test_real_gamedata_loaded():
    gd = load()
    assert len(gd.subunits) >= 100
    assert len(gd.equipment) >= 100
    assert gd.d("COMBAT_OVER_WIDTH_PENALTY_MAX") == -0.33
    assert gd.defines["PIERCING_THRESHOLDS"] == [1.0, 0.75, 0.5, 0.0]


def test_width_and_mass_assault():
    s1 = calculate_division(DivisionTemplate("t", {"infantry": 10}))
    assert s1["width"] == 20.0
    s2 = calculate_division(DivisionTemplate("t", {"infantry": 10}, doctrine={"grand": "mass_assault", "milestones": [True, False, False, False]}))
    assert abs(s2["width"] - 18.0) < 1e-6


def test_support_and_regimental_zero_width():
    base = calculate_division(DivisionTemplate("t", {"infantry": 9}))
    full = calculate_division(DivisionTemplate("t", {"infantry": 9}, support=["engineer", "artillery"], regimental=["fire_support"]))
    assert base["width"] == full["width"] == 18.0
    assert full["soft"] > base["soft"]
    assert full["entrenchment"] > base["entrenchment"]
    assert full["ic_cost"] > base["ic_cost"]


def test_tank_designer_and_presets():
    gd = load()
    mods = default_modules(gd, "medium_tank_chassis_2", "armor", 1941)
    tk = design_tank(gd, "medium_tank_chassis_2", mods, "armor")
    assert tk["armor_value"] > 0 and tk["build_cost_ic"] > 0 and not tk["warnings"]
    for name, tpl in PRESETS.items():
        st = calculate_division(tpl, gd)
        assert st["width"] > 0 and st["ic_cost"] > 0, name


def test_battle_deterministic_and_terrain_effect():
    atk = PRESETS["tank_30w_med"]
    dfn = PRESETS["inf_18w_hold"]
    r1 = simulate_battle(atk, dfn, BattleConfig(attacker_count=4, defender_count=4, seed=7))
    r2 = simulate_battle(atk, dfn, BattleConfig(attacker_count=4, defender_count=4, seed=7))
    assert r1["hours_lasted"] == r2["hours_lasted"]
    assert r1["winner"] == r2["winner"]
    assert len(r1["timeline"]) > 0

    hard = simulate_battle(atk, dfn, BattleConfig(attacker_count=4, defender_count=4, terrain="mountain", fort_level=5, river="major", seed=7))
    assert hard["attacker_summary"]["manpower_lost"] >= r1["attacker_summary"]["manpower_lost"] or hard["winner"] != "attacker"


def test_arena_runs_and_ranks():
    res = run_arena(ArenaConfig(tech_year=1940, terrain="plains", balance_mode="width", include_special=False, max_hours=120))
    assert res["templates_count"] >= 20
    assert res["total_battles"] == res["templates_count"] * (res["templates_count"] - 1)
    assert res["best_defense"][0]["defense_kpd"] >= res["best_defense"][-1]["defense_kpd"]
    assert res["best_universal"][0]["universal_kpd"] >= res["best_universal"][-1]["universal_kpd"]


def test_fullslot_and_upgrade_study():
    res = run_fullslot_and_upgrade_study(tech_year=1942, terrain="plains")
    assert len(res["fullslot_ranking"]) >= 10
    assert len(res["upgrade_curve"]) == 8
    assert res["upgrade_curve"][-1]["mp_ratio"] > res["upgrade_curve"][0]["mp_ratio"]


def test_evolution_optimizer():
    res = run_evolution(EvolutionConfig(tech_year=1942, terrain="plains", max_steps=4, beam_width=1))
    assert len(res["steps"]) >= 3
    assert res["steps"][-1]["mp_ratio"] > res["steps"][0]["mp_ratio"]
    assert res["candidates_tested"] > 20


def test_budget_curve():
    res = run_budget_curve(BudgetCurveConfig(tech_year=1942, terrain="plains", start_ic=600, end_ic=1400, step_ic=400))
    assert len(res["steps"]) == 3
    assert res["steps"][-1]["mp_ratio"] >= res["steps"][0]["mp_ratio"]




