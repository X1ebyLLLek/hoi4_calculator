"""Zero-dependency HTTP server for HoI4 1.19.5.0+ Calculator & Battle Simulator."""

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, Dict

from . import gamedata
from .arena import ArenaConfig, run_arena, run_fullslot_and_upgrade_study
from .budget_curve import BudgetCurveConfig, run_budget_curve
from .evolution import EvolutionConfig, run_evolution
from .division import DivisionTemplate, calculate_division
from .battle import BattleConfig, simulate_battle
from .presets import PRESETS
from .tanks import default_modules, design_tank

WEB_DIR = Path(__file__).parent / "web"
LAND_TERRAINS = ("plains", "forest", "hills", "mountain", "marsh", "jungle", "desert", "urban")


def _parse_template(payload: Dict[str, Any]) -> DivisionTemplate:
    return DivisionTemplate(
        name=str(payload.get("name", "Шаблон")),
        battalions={str(k): int(v) for k, v in payload.get("battalions", {}).items() if int(v) > 0},
        support=[str(x) for x in payload.get("support", [])],
        regimental=[str(x) for x in payload.get("regimental", [])],
        tech_year=int(payload.get("tech_year", 1940)),
        equipment_overrides={str(k): str(v) for k, v in payload.get("equipment_overrides", {}).items()},
        tank_designs=dict(payload.get("tank_designs", {})),
        doctrine=dict(payload.get("doctrine", {})),
    )


def _parse_battle_config(payload: Dict[str, Any]) -> BattleConfig:
    return BattleConfig(
        terrain=str(payload.get("terrain", "plains")),
        extra_flanks=int(payload.get("extra_flanks", 0)),
        river=str(payload.get("river", "none")),
        fort_level=int(payload.get("fort_level", 0)),
        attacker_count=int(payload.get("attacker_count", 4)),
        defender_count=int(payload.get("defender_count", 4)),
        attacker_planning=float(payload.get("attacker_planning", 0.30)),
        defender_entrenchment_pct=float(payload.get("defender_entrenchment_pct", 1.0)),
        attacker_general_skill=int(payload.get("attacker_general_skill", 3)),
        attacker_general_atk=int(payload.get("attacker_general_atk", 3)),
        defender_general_skill=int(payload.get("defender_general_skill", 3)),
        defender_general_def=int(payload.get("defender_general_def", 3)),
        attacker_xp_mod=float(payload.get("attacker_xp_mod", 0.25)),
        defender_xp_mod=float(payload.get("defender_xp_mod", 0.25)),
        air_superiority=float(payload.get("air_superiority", 0.0)),
        attacker_cas_dmg=float(payload.get("attacker_cas_dmg", 0.0)),
        defender_cas_dmg=float(payload.get("defender_cas_dmg", 0.0)),
        supply_lack_atk=float(payload.get("supply_lack_atk", 0.0)),
        supply_lack_def=float(payload.get("supply_lack_def", 0.0)),
        include_night=bool(payload.get("include_night", True)),
        max_hours=int(payload.get("max_hours", 720)),
        seed=int(payload["seed"]) if payload.get("seed") is not None else 42,
    )


def _build_catalog() -> Dict[str, Any]:
    gd = gamedata.load()

    def unit_info(uid: str) -> Dict[str, Any]:
        u = gd.subunits[uid]
        return {
            "id": uid,
            "name": gd.name(uid),
            "group": u.get("group"),
            "combat_width": float(u.get("combat_width", 0)),
            "manpower": int(u.get("manpower", 0)),
            "max_organisation": float(u.get("max_organisation", 0)),
            "max_strength": float(u.get("max_strength", 0)),
            "need": u.get("need") or {},
            "year": gd.sub_year(uid),
            "allowed_battalion_groups": u.get("allowed_battalion_groups"),
            "same_support_type": u.get("same_support_type"),
        }

    equipment_list = []
    for eid, eq in gd.equipment.items():
        if eq.get("_is_archetype"):
            continue
        st = gd.eq_stats(eid)
        equipment_list.append(st)
    equipment_list.sort(key=lambda x: (x["archetype"], x["year"], x["id"]))

    terrains = {}
    for tid in LAND_TERRAINS:
        t = gd.terrain.get(tid, {})
        terrains[tid] = {
            "id": tid,
            "name": gd.name(tid),
            "combat_width": t.get("combat_width", 70),
            "combat_support_width": t.get("combat_support_width", 35),
            "attack_mod": (t.get("units") or {}).get("attack", 0.0),
            "movement_cost": t.get("movement_cost", 1.0),
        }

    grand_docs = {
        k: {"id": k, "name": gd.name(v.get("name", k))}
        for k, v in gd.doctrines["grand"].items()
    }
    sub_docs = {
        k: {"id": k, "name": gd.name(v.get("name", k)), "track": v.get("track", "")}
        for k, v in gd.doctrines["sub"].items()
    }

    tank_chassis = [
        {"id": k, "name": gd.name(k), "archetype": v.get("archetype", k), "year": v.get("year", 1936)}
        for k, v in gd.equipment.items()
        if v.get("_file") == "tank_chassis.txt" and not k.endswith("_chassis") and k[-1].isdigit()
    ]
    tank_modules = [
        {"id": k, "name": gd.name(k), "category": v.get("category"), "year": gd.module_year(k),
         "allow_equipment_type": v.get("allow_equipment_type")}
        for k, v in gd.modules.items()
    ]

    return {
        "version": gd.version,
        "line_units": sorted([unit_info(u) for u in gd.line_units()], key=lambda x: (x["group"], x["name"])),
        "support_units": sorted([unit_info(u) for u in gd.support_units()], key=lambda x: x["name"]),
        "regimental_units": sorted([unit_info(u) for u in gd.regimental_units()], key=lambda x: x["name"]),
        "equipment": equipment_list,
        "terrains": terrains,
        "doctrines": {"grand": grand_docs, "sub": sub_docs},
        "tank_chassis": tank_chassis,
        "tank_modules": tank_modules,
        "presets": {k: asdict(v) for k, v in PRESETS.items()},
    }


class HoI4RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/api/catalog":
            self._send_json(_build_catalog())
            return

        if self.path in ("/", "/index.html"):
            index_file = WEB_DIR / "index.html"
            if not index_file.exists():
                self._send_json({"error": "index.html not found"}, status=404)
                return
            html = index_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        try:
            data = self._read_json()
            gd = gamedata.load()
            if self.path == "/api/calculate":
                tpl = _parse_template(data)
                self._send_json(calculate_division(tpl, gd))
                return

            if self.path == "/api/simulate":
                atk_tpl = _parse_template(data.get("attacker", {}))
                def_tpl = _parse_template(data.get("defender", {}))
                cfg = _parse_battle_config(data.get("config", {}))
                self._send_json(simulate_battle(atk_tpl, def_tpl, cfg, gd))
                return

            if self.path == "/api/tank_design":
                cid = str(data.get("chassis", "medium_tank_chassis_2"))
                role = str(data.get("role", "armor"))
                year = int(data.get("year", 1942))
                mods = data.get("modules") or default_modules(gd, cid, role, year)
                self._send_json(design_tank(gd, cid, mods, role))
                return

            if self.path == "/api/arena":
                acfg = ArenaConfig(
                    tech_year=int(data.get("tech_year", 1940)),
                    terrain=str(data.get("terrain", "plains")),
                    river=str(data.get("river", "none")),
                    fort_level=int(data.get("fort_level", 0)),
                    balance_mode=str(data.get("balance_mode", "width")),
                    ic_budget=float(data.get("ic_budget", 10000.0)),
                    max_hours=int(data.get("max_hours", 480)),
                    include_tanks=bool(data.get("include_tanks", True)),
                    include_special=bool(data.get("include_special", True)),
                    seed=int(data.get("seed", 42)),
                )
                self._send_json(run_arena(acfg, gd))
                return

            if self.path == "/api/upgrade_study":
                self._send_json(run_fullslot_and_upgrade_study(
                    tech_year=int(data.get("tech_year", 1942)),
                    terrain=str(data.get("terrain", "plains")),
                    gd=gd,
                ))
                return

            if self.path == "/api/evolution":
                ecfg = EvolutionConfig(
                    tech_year=int(data.get("tech_year", 1942)),
                    terrain=str(data.get("terrain", "plains")),
                    doctrine=str(data.get("doctrine", "grand_battleplan")),
                    factories=int(data.get("factories", 15)),
                    ic_per_factory_day=float(data.get("ic_per_factory_day", 3.6)),
                    goal=str(data.get("goal", "mp_saver")),
                    max_steps=int(data.get("max_steps", 22)),
                    beam_width=int(data.get("beam_width", 2)),
                )
                self._send_json(run_evolution(ecfg, gd))
                return

            if self.path == "/api/budget_curve":
                bcfg = BudgetCurveConfig(
                    tech_year=int(data.get("tech_year", 1942)),
                    terrain=str(data.get("terrain", "plains")),
                    doctrine=str(data.get("doctrine", "grand_battleplan")),
                    start_ic=int(data.get("start_ic", 600)),
                    end_ic=int(data.get("end_ic", 5600)),
                    step_ic=int(data.get("step_ic", 200)),
                    enemy_mult=float(data.get("enemy_mult", 1.5)),
                )
                self._send_json(run_budget_curve(bcfg, gd))
                return

            self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)


def run_server(host: str = "127.0.0.1", port: int = 8094) -> None:
    gamedata.load()
    server = ThreadingHTTPServer((host, port), HoI4RequestHandler)
    print(f"HoI4 1.19.5.0+ Calculator & Simulator running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
