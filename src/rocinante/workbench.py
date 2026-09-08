"""Local refit workbench: propose, inspect, decide, repeat.

Fixture proposals exercise the same validation, diff and physics as model
proposals. Kord sharing is an explicit action separate from local approval.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from rocinante.agent.refit import RefitAgent, RefitModelError, RefitResult, model_name
from rocinante.blend import launch_live_ship
from rocinante.demo import Bounds, open_openrocket
from rocinante.diff import diff_ships, ship_geometry_parts
from rocinante.flight import plan
from rocinante.handoff import export_baseline, export_pair, share_url, verified_pair
from rocinante.kord import KordClient
from rocinante.ork import write_ork
from rocinante.samples import ROCINANTE
from rocinante.ship import ShipSpec
from rocinante.spec import RocketSpec

PRESETS = {
    "torpedoes": "Carry eight more torpedoes without losing cruise burn time",
    "armor": "Add 2 cm of hull armor and show the performance cost",
    "drive": "Lengthen the drive cone by 4 m; keep engine performance unchanged",
    "fins": "Give the torpedoes larger, swept fins for a stable launch",
    "bow": "Move the launch tubes forward to the bow",
}

# What the demo suggests typing. Each one is a torpedo-equipping ask Astra can
# answer inside the ShipSpec contract.
SAMPLE_ASKS = [
    ("Carry eight more torpedoes by adding two launch tubes and six magazine slots, "
     "without losing cruise burn time"),
    "Move the launch tubes forward to the bow and add two more",
    "Give the torpedoes four larger swept fins and a longer nose for a stable launch",
    "Switch the torpedo motor to a 29 mm F-class and lengthen the booster tube to fit it",
    "Add 2 cm of hull armor and show the performance cost",
]


TORPEDO_PRESETS = {
    "fins": "Give the torpedo larger swept fins",
    "nose": "Lengthen the torpedo nose by 5 cm",
    "four_fins": "Use four fins on the torpedo",
}
TORPEDO_ASKS = [
    "Give the torpedo four larger swept fins for a stable launch",
    "Lengthen the torpedo nose by 5 cm",
    "Switch the torpedo motor to a 29 mm F-class and lengthen the booster tube to fit it",
]


def validate_static_ship(before: ShipSpec, after: ShipSpec):
    """Demo edits are limited to the torpedo, enforced before any revision write."""
    if before.model_dump(exclude={"torpedo", "rationale"}) != after.model_dump(exclude={"torpedo", "rationale"}):
        raise ValueError("The Roci is static in this demo. Only the torpedo can be redesigned; the ship is preserved.")


def fixture_proposal(ship: ShipSpec, preset: str) -> ShipSpec:
    after = ship.model_copy(deep=True)
    if preset == "torpedoes":
        after.weapons.torpedo_tubes += 2
        after.weapons.magazine_m3 += 6 * after.weapons.torpedo_volume_m3
        # Preserve propellant/dry-mass ratio, hence cruise endurance and delta-v.
        after.drive.propellant_t *= after.dry_mass_t / ship.dry_mass_t
        after.rationale = (
            "Fixture: add two tubes and six magazine slots. Increase propellant in "
            "proportion to dry mass to preserve cruise endurance and delta-v. "
            "Tank packaging is not modeled in this skeleton."
        )
    elif preset == "armor":
        after.hull.armor_cm += 2
        after.rationale = (
            "Fixture: add 2 cm of armor. Higher dry mass reduces delta-v and acceleration. "
            "The exterior shape is unchanged; the hull highlight identifies the affected part."
        )
    elif preset == "drive":
        after.drive.cone_length_m += 4
        after.rationale = (
            "Fixture: extend the cone by 4 m. This geometry-only change does not alter "
            "thrust or exhaust velocity in the current engineering model."
        )
    elif preset == "bow":
        after.weapons.tube_station = 0.88
        after.rationale = (
            "Fixture: mount the launch tubes at the bow. Placement only; mass and "
            "performance are unchanged, and Blender moves the tube cassettes."
        )
    elif preset == "nose":
        after.torpedo.nose.length_m += 0.05
        after.rationale = "Fixture: lengthen the torpedo nose by 5 cm; keep the Roci fixed."
    elif preset == "four_fins":
        after.torpedo.fins.count = 4 if after.torpedo.fins.count != 4 else 3
        after.rationale = f"Fixture: use {after.torpedo.fins.count} fins on the torpedo; keep the Roci fixed."
    elif preset == "fins":
        fins = after.torpedo.fins
        fins.root_chord_m += 0.02
        fins.tip_chord_m += 0.01
        fins.height_m += 0.02
        fins.sweep_m += 0.01
        after.rationale = (
            "Fixture: enlarge and sweep the torpedo fin set to move its centre of pressure "
            "aft. The ship's mass and performance are unchanged; OpenRocket shows the new fins."
        )
    else:
        raise ValueError("Choose a supported fixture preset")
    return ShipSpec.model_validate(after.model_dump())


def torpedo_summary(ship: ShipSpec, changed: bool = False) -> dict:
    """What the review panel says about the torpedo, beside the ship's numbers."""
    t = ship.torpedo
    return {
        "length_m": t.total_length_m, "diameter_m": t.caliber_m, "fins": t.fins.count,
        "fin_span_m": t.fins.height_m, "motor": f"{t.motor.manufacturer} {t.motor.designation}",
        "changed": changed,
    }


class Workbench:
    def __init__(
        self,
        out: Path,
        live: bool = False,
        show_blender: bool = False,
        show_openrocket: bool = False,
        auto_export: bool = False,
        auto_accept: bool = False,
        auto_share: bool = False,
        torpedo_only: bool = False,
        # Called with a revision's comparison link and its index. The index is
        # what lets a viewer ignore a link that arrives after a newer one.
        on_share_url: Callable[[str, int], None] | None = None,
        blender_geometry: list[str] | None = None,
        openrocket_bounds: Bounds | None = None,
    ):
        self.out = out
        self.live = live
        self.torpedo_only = torpedo_only
        self.show_blender = show_blender
        self.show_openrocket = show_openrocket
        # Regenerate real Blender geometry for every revision so the viewer
        # never has to fall back to its schematic. Under a second per hull.
        self.auto_export = auto_export
        # The demo has no review step: every proposal becomes the ship.
        self.auto_accept = auto_accept
        # Upload each revision's comparison to Kord in the background.
        self.auto_share = auto_share and auto_export
        self.on_share_url = on_share_url
        self.blender_geometry = blender_geometry
        self.openrocket_bounds = openrocket_bounds
        # The share thread and the HTTP handler both touch `state`.
        self.lock = threading.RLock()
        self.path = out / "workbench.json"
        self.blender_spec_path = out / "blender-current.json"
        self.selection_path = out / "selection.json"
        self.integration_status = {}
        self.torpedo_dir = out / "torpedo"
        self.torpedo_path: Path | None = None
        self._torpedo_shown: str | None = None
        out.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            for entry in self.state["iterations"]:
                if "torpedo" not in entry:
                    entry["torpedo"] = torpedo_summary(ShipSpec.model_validate(entry["spec"]))
                if "geometry_changed_parts" not in entry:
                    parent = entry.get("parent")
                    entry["geometry_changed_parts"] = ship_geometry_parts(
                        ShipSpec.model_validate(self.state["iterations"][parent]["spec"]),
                        ShipSpec.model_validate(entry["spec"]),
                    ) if parent is not None else []
                handoff = entry.get("handoff", {})
                if handoff.get("status") in ("exporting", "sharing"):
                    stage = handoff["status"]
                    handoff.update(
                        status="share_failed" if stage == "sharing" else "export_failed",
                        error="Operation interrupted. Retry explicitly; a share may already exist at Kord.",
                    )
            self.save()
        else:
            self.state = {"accepted": 0, "iterations": [self.entry(ROCINANTE, 0, "approved")]}
            self.save()
        if self.auto_export:
            self.export_baseline()
        self.publish_current()
        if self.show_blender:
            launch_live_ship(self.blender_spec_path, self.blender_geometry)

    def publish_current(self):
        """Push the design under review to Blender and OpenRocket."""
        current = self.state["iterations"][-1]
        if current["status"] == "rejected":
            current = self.state["iterations"][self.state["accepted"]]
        temporary = self.blender_spec_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current["spec"], indent=2))
        temporary.replace(self.blender_spec_path)
        self.publish_torpedo(ShipSpec.model_validate(current["spec"]), current["index"])
        self.publish_selection(current)

    # Blender watches the spec file itself; the old name survives for callers.
    refresh_blender = publish_current

    def displayed(self):
        current = self.state["iterations"][-1]
        return self.state["iterations"][self.state["accepted"]] if current["status"] == "rejected" else current

    def target_ship(self, current, torpedo_id=None):
        ship = ShipSpec.model_validate(current["spec"])
        if torpedo_id:
            ship.torpedo = RocketSpec.model_validate(current.get("torpedoes", {}).get(torpedo_id, ship.torpedo.model_dump()))
        return ship

    def validate_target(self, torpedo_id, current):
        valid = {f"torpedo_{i+1:02d}" for i in range(current["spec"]["weapons"]["torpedo_tubes"])}
        if torpedo_id is not None and (not isinstance(torpedo_id, str) or torpedo_id not in valid):
            raise ValueError("That torpedo is no longer aboard this revision")
        return torpedo_id

    def select(self, payload):
        current = self.displayed()
        target = self.validate_target(payload.get("torpedo_id"), current)
        self.state["selected_torpedo"] = target
        self.save()
        self.publish_selection(current)
        return self.snapshot()

    def publish_selection(self, current):
        target = self.state.get("selected_torpedo")
        try:
            self.validate_target(target, current)
        except ValueError:
            target = self.state["selected_torpedo"] = None
            self.save()
        ship = self.target_ship(current, target)
        path = self.torpedo_dir / (f"v{current['index']:04d}-{target}.ork" if target else f"v{current['index']:04d}.ork")
        name = f"{ship.name} {target.replace('_', ' ') if target else 'general torpedo'} v{current['index']}"
        write_ork(ship.torpedo.model_copy(update={"name": name}), path)
        self.torpedo_path = path
        command = {"request_id": time.time_ns(), "torpedo_id": target, "revision": current["index"],
                   "torpedoes": current.get("torpedoes", {}), "file": str(path.resolve()), "name": name}
        temporary = self.selection_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(command))
        temporary.replace(self.selection_path)
        if self.show_openrocket:
            from rocinante.openrocket_live import show_in_openrocket
            try:
                self.integration_status["openrocket"] = show_in_openrocket(path, self.selection_path, self.openrocket_bounds)
            except Exception as exc:
                logging.getLogger(__name__).exception("OpenRocket live update failed")
                self.integration_status["openrocket"] = {"status": "error", "message": str(exc)}
        if self.show_blender:
            self.integration_status["blender"] = {"status": "pending", "request_id": command["request_id"]}

    def publish_torpedo(self, ship: ShipSpec, index: int):
        """Keep the general design's immutable artifact beside each revision."""
        name = f"{ship.name} torpedo v{index}"
        self.torpedo_path = write_ork(
            ship.torpedo.model_copy(update={"name": name}), self.torpedo_dir / f"v{index:04d}.ork"
        )

    def export_baseline(self):
        base = self.state["iterations"][0]
        if base.get("handoff", {}).get("artifacts"):
            return
        try:
            base["handoff"] = {"status": "baseline", "artifacts": export_baseline(self.out, base)}
        except Exception:
            logging.getLogger(__name__).exception("Baseline export failed; viewer uses the schematic")
            return
        self.save()

    @staticmethod
    def entry(ship: ShipSpec, index: int, status: str, result: RefitResult | None = None):
        burn = plan(ship, "Tycho", "Ceres")
        return {
            "index": index, "name": ship.name, "status": status,
            "spec": ship.model_dump(mode="json"), "derived": ship.derived(),
            "mission": burn.model_dump(mode="json"),
            "delta_v_margin": ship.delta_v_km_s - burn.delta_v_km_s,
            "rationale": ship.rationale or "Baseline design. Ready for a refit.",
            "torpedo": torpedo_summary(
                ship, bool(result) and any(c.path.startswith("torpedo") for c in result.diff.changes)
            ),
            "changed_parts": result.diff.changed_parts if result else [],
            "geometry_changed_parts": ship_geometry_parts(result.before, ship) if result else [],
            "changes": [c.human() for c in result.diff.changes] if result else [],
        }

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, allow_nan=False))
        temporary.replace(self.path)

    def snapshot(self):
        target = self.state.get("selected_torpedo")
        scoped = bool(target) or self.torpedo_only
        integrations = dict(self.integration_status)
        for app in ("blender", "openrocket"):
            try:
                reply = json.loads(self.selection_path.with_name(f"{app}-selection-status.json").read_text())
                command = json.loads(self.selection_path.read_text())
                if reply.get("request_id") == command["request_id"]:
                    integrations[app] = reply
            except (OSError, ValueError):
                pass
        return {**self.state, "mode": "live" if self.live else "fixture", "presets": TORPEDO_PRESETS if scoped else PRESETS,
                "model": model_name() if self.live else None,
                "kord_base": KordClient().base_url,
                "openrocket": self.show_openrocket, "blender": self.show_blender,
                "auto_accept": self.auto_accept, "auto_share": self.auto_share,
                "sample_asks": TORPEDO_ASKS if scoped else SAMPLE_ASKS,
                "torpedo_only": self.torpedo_only,
                "selected_torpedo": target, "integrations": integrations,
                "workshop_torpedo": torpedo_summary(self.target_ship(self.displayed(), target)),
                "torpedo_file": str(self.torpedo_path) if self.torpedo_path else None}

    def revision(self, payload: dict):
        index = payload.get("index")
        if type(index) is not int or not 0 < index < len(self.state["iterations"]):
            raise ValueError("Select a proposal revision to export or share")
        return self.state["iterations"][index]

    def export(self, payload: dict):
        current = self.revision(payload)
        handoff = current.setdefault("handoff", {})
        if handoff.get("share_url"):
            return self.snapshot()  # Preserve the exact pair already shared.
        handoff.update(status="exporting", error=None)
        self.save()
        try:
            parent = self.state["iterations"][current["parent"]]
            handoff["artifacts"] = export_pair(self.out, current, parent)
            handoff["status"] = "exported"
        except Exception:
            handoff.update(status="export_failed", error="Blender export failed. Check server logs and retry.")
            logging.getLogger(__name__).exception("Comparison export failed")
        self.save()
        return self.snapshot()

    def share(self, payload: dict):
        current = self.revision(payload)
        handoff = current.setdefault("handoff", {})
        if handoff.get("share_url"):
            return self.snapshot()  # Repeated clicks do not create another share.
        if handoff.get("status") not in ("exported", "share_failed"):
            raise ValueError("Export the comparison before sharing it")
        parent = self.state["iterations"][current["parent"]]
        if current.get("geometry_changed_parts") or not current["torpedo"].get("changed"):
            before, after = verified_pair(self.out, handoff["artifacts"])
            what = "ship"
        else:
            # Only the torpedo moved: compare the torpedoes themselves.
            target = current.get("target_torpedo")
            suffix = f"-{target}" if target else ""
            before = self.torpedo_dir / f"v{parent['index']:04d}{suffix}.ork"
            after = self.torpedo_dir / f"v{current['index']:04d}{suffix}.ork"
            write_ork(self.target_ship(parent, target).torpedo, before)
            write_ork(self.target_ship(current, target).torpedo, after)
            what = "torpedo"
        handoff.update(status="sharing", error=None, compared=what)
        self.save()
        kord = KordClient()
        try:
            result = kord.share_diff(
                before, after,
                title=f"{current['name']} {what} v{current['parent']} → v{current['index']} ({current.get('source', 'proposal')})",
            )
            handoff.update(status="shared", share_url=share_url(kord.base_url, result.get("url", "")),
                           expires_at=result.get("expiresAt"))
            if self.on_share_url:
                try:
                    self.on_share_url(handoff["share_url"], current["index"])
                except Exception:
                    logging.getLogger(__name__).exception("Kord window navigation failed")
        except Exception:
            handoff.update(status="share_failed", error=(
                "Kord sharing failed. Your export and proposal are saved. "
                "Retry may create another link if the previous upload reached Kord."
            ))
            logging.getLogger(__name__).exception("Kord sharing failed")
        finally:
            kord.close()
        self.save()
        return self.snapshot()

    def propose(self, payload: dict):
        if self.state["iterations"][-1]["status"] == "pending":
            raise ValueError("Approve or reject the pending proposal first")
        parent = self.state["accepted"]
        previous = self.state["iterations"][parent]
        target = self.validate_target(payload.get("torpedo_id", self.state.get("selected_torpedo")), previous)
        ship = self.target_ship(previous, target)
        scoped = bool(target) or self.torpedo_only
        if self.live:
            ask = payload.get("ask", "")
            if not isinstance(ask, str) or not ask.strip() or len(ask) > 2000:
                raise ValueError("Enter a refit request of 1–2000 characters")
            after = RefitAgent(build_meshes=False, torpedo_only=scoped).propose(ship, ask)
        else:
            presets = TORPEDO_PRESETS if scoped else PRESETS
            preset = payload.get("preset", "fins" if scoped else "torpedoes")
            if not isinstance(preset, str) or preset not in presets:
                raise ValueError("Choose a supported fixture preset")
            ask = presets[preset]
            after = fixture_proposal(ship, preset)
        if scoped:
            validate_static_ship(ship, after)
        result = RefitResult(ask=ask, before=ship, after=after, diff=diff_ships(ship, after))
        index = len(self.state["iterations"])
        entry = self.entry(after, index, "approved" if self.auto_accept else "pending", result)
        overrides = dict(previous.get("torpedoes", {}))
        if target:
            overrides[target] = after.torpedo.model_dump(mode="json")
            # The shared design stays intact; only this loaded round owns the edit.
            entry["spec"] = {**previous["spec"], "rationale": after.rationale}
            entry["changes"] = [f"{target}: {change}" for change in entry["changes"]]
        valid_ids = {f"torpedo_{i+1:02d}" for i in range(entry["spec"]["weapons"]["torpedo_tubes"])}
        entry.update(torpedoes={k: v for k, v in overrides.items() if k in valid_ids},
                     target_torpedo=target, parent=parent, ask=ask, source="live" if self.live else "fixture")
        if self.live:
            entry["model"] = model_name()
        self.state["iterations"].append(entry)
        if self.auto_accept:
            self.state["accepted"] = index
        self.save()
        self.publish_current()
        if self.auto_export:
            self.export({"index": index})
            if self.auto_share and entry.get("handoff", {}).get("status") == "exported":
                threading.Thread(target=self._share_in_background, args=(index,),
                                 name=f"kord-share-v{index}", daemon=True).start()
        return self.snapshot()

    def _share_in_background(self, index: int):
        with self.lock:
            try:
                self.share({"index": index})
            except Exception:
                logging.getLogger(__name__).exception("Background Kord share failed")

    def decide(self, payload: dict):
        current = self.state["iterations"][-1]
        verdict = payload.get("verdict")
        if current["status"] != "pending" or payload.get("index") != current["index"]:
            raise ValueError("This proposal is no longer pending; refresh the workbench")
        if verdict not in ("approved", "rejected"):
            raise ValueError("Verdict must be approved or rejected")
        current["status"] = verdict
        if verdict == "approved":
            self.state["accepted"] = current["index"]
        self.save()
        if verdict == "rejected":
            self.publish_current()
        return self.snapshot()


def make_server(workbench: Workbench, port: int) -> HTTPServer:
    web = Path(__file__).resolve().parents[2] / "web"

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json"):
            data = json.dumps(body).encode() if content_type == "application/json" else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            if not args or not str(args[0]).startswith("GET /api/state"):
                super().log_message(format, *args)

        def do_GET(self):
            if self.path == "/api/state":
                with workbench.lock:
                    return self.reply(200, workbench.snapshot())
            if self.path.startswith("/exports/"):
                # Only generated, known artifacts; never expose the workspace.
                parts = self.path.split("/")
                allowed = {"before.glb", "after.glb", "before.json", "after.json", "comparison.json"}
                if len(parts) == 4 and parts[2].startswith("v") and parts[2][1:].isdigit() and parts[3] in allowed:
                    path = workbench.out / "exports" / parts[2] / parts[3]
                    if path.is_file() and path.resolve().is_relative_to((workbench.out / "exports").resolve()):
                        mime = "model/gltf-binary" if path.suffix == ".glb" else "application/octet-stream"
                        return self.reply(200, path.read_bytes(), mime)
                return self.reply(404, {"error": "Export not found"})
            assets = {"/": ("loop.html", "text/html; charset=utf-8"),
                      "/loop.js": ("loop.js", "text/javascript"),
                      "/loop.css": ("loop.css", "text/css"),
                      "/primitives.js": ("primitives.js", "text/javascript"),
                      "/assembly.js": ("assembly.js", "text/javascript"),
                      "/rocinante.glb": ("rocinante.glb", "model/gltf-binary"),
                      "/interior-references": ("interior-references.html", "text/html; charset=utf-8")}
            if self.path not in assets:
                return self.reply(404, {"error": "Not found"})
            name, mime = assets[self.path]
            self.reply(200, (web / name).read_bytes(), mime)

        def do_POST(self):
            # Local-only API; require same-origin JSON to prevent cross-site forms.
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                return self.reply(403, {"error": "Cross-origin writes are not allowed"})
            if self.headers.get("Content-Type") != "application/json":
                return self.reply(415, {"error": "Send application/json"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise TypeError("Expected a JSON object")
                with workbench.lock:
                    if self.path == "/api/propose":
                        state = workbench.propose(payload)
                    elif self.path == "/api/select":
                        state = workbench.select(payload)
                    elif self.path == "/api/decide":
                        state = workbench.decide(payload)
                    elif self.path == "/api/export":
                        state = workbench.export(payload)
                    elif self.path == "/api/share":
                        state = workbench.share(payload)
                    else:
                        return self.reply(404, {"error": "Not found"})
                self.reply(200, state)
            except RefitModelError as exc:
                self.reply(502, {"error": f"{exc}. The accepted design is preserved."})
            except (ValueError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception:
                logging.getLogger(__name__).exception("Workbench request failed")
                self.reply(502, {"error": "Request failed. Check server logs; the accepted design is preserved."})

    return HTTPServer(("127.0.0.1", port), Handler)
