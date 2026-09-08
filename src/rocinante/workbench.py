"""Local refit workbench: propose, inspect, decide, repeat.

Fixture proposals exercise the same validation, diff and physics as model
proposals. Kord sharing is an explicit action separate from local approval.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from rocinante.agent.refit import RefitAgent, RefitModelError, RefitResult, model_name
from rocinante.blend import launch_live_ship
from rocinante.diff import diff_ships
from rocinante.flight import plan
from rocinante.handoff import export_pair, share_url, verified_pair
from rocinante.kord import KordClient
from rocinante.samples import ROCINANTE
from rocinante.ship import ShipSpec

PRESETS = {
    "torpedoes": "Carry eight more torpedoes without losing cruise burn time",
    "armor": "Add 2 cm of hull armor and show the performance cost",
    "drive": "Lengthen the drive cone by 4 m; keep engine performance unchanged",
}


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
    else:
        raise ValueError("Choose a supported fixture preset")
    return ShipSpec.model_validate(after.model_dump())


class Workbench:
    def __init__(self, out: Path, live: bool = False, show_blender: bool = False):
        self.out = out
        self.live = live
        self.show_blender = show_blender
        self.path = out / "workbench.json"
        self.blender_spec_path = out / "blender-current.json"
        out.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            for entry in self.state["iterations"]:
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
        self.refresh_blender()
        if self.show_blender:
            launch_live_ship(self.blender_spec_path)

    def refresh_blender(self):
        """Publish the design currently under review to the visible Blender scene."""
        current = self.state["iterations"][-1]
        if current["status"] == "rejected":
            current = self.state["iterations"][self.state["accepted"]]
        temporary = self.blender_spec_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current["spec"], indent=2))
        temporary.replace(self.blender_spec_path)

    @staticmethod
    def entry(ship: ShipSpec, index: int, status: str, result: RefitResult | None = None):
        burn = plan(ship, "Tycho", "Ceres")
        return {
            "index": index, "name": ship.name, "status": status,
            "spec": ship.model_dump(mode="json"), "derived": ship.derived(),
            "mission": burn.model_dump(mode="json"),
            "delta_v_margin": ship.delta_v_km_s - burn.delta_v_km_s,
            "rationale": ship.rationale or "Baseline design. Ready for a refit.",
            "changed_parts": result.diff.changed_parts if result else [],
            "changes": [c.human() for c in result.diff.changes] if result else [],
        }

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, allow_nan=False))
        temporary.replace(self.path)

    def snapshot(self):
        return {**self.state, "mode": "live" if self.live else "fixture", "presets": PRESETS,
                "model": model_name() if self.live else None,
                "kord_base": KordClient().base_url}

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
        before, after = verified_pair(self.out, handoff["artifacts"])
        handoff.update(status="sharing", error=None)
        self.save()
        kord = KordClient()
        try:
            result = kord.share_diff(
                before, after,
                title=f"{current['name']} v{current['parent']} → v{current['index']} ({current.get('source', 'proposal')})",
            )
            handoff.update(status="shared", share_url=share_url(kord.base_url, result.get("url", "")),
                           expires_at=result.get("expiresAt"))
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
        ship = ShipSpec.model_validate(self.state["iterations"][parent]["spec"])
        if self.live:
            ask = payload.get("ask", "")
            if not isinstance(ask, str) or not ask.strip() or len(ask) > 2000:
                raise ValueError("Enter a refit request of 1–2000 characters")
            after = RefitAgent(build_meshes=False).propose(ship, ask)
        else:
            preset = payload.get("preset", "torpedoes")
            if not isinstance(preset, str) or preset not in PRESETS:
                raise ValueError("Choose a supported fixture preset")
            ask = PRESETS[preset]
            after = fixture_proposal(ship, preset)
        result = RefitResult(ask=ask, before=ship, after=after, diff=diff_ships(ship, after))
        index = len(self.state["iterations"])
        entry = self.entry(after, index, "pending", result)
        entry.update(parent=parent, ask=ask, source="live" if self.live else "fixture")
        if self.live:
            entry["model"] = model_name()
        self.state["iterations"].append(entry)
        self.save()
        self.refresh_blender()
        return self.snapshot()

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
            self.refresh_blender()
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

        def do_GET(self):
            if self.path == "/api/state":
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
                      "/primitives.js": ("primitives.js", "text/javascript")}
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
                if self.path == "/api/propose":
                    state = workbench.propose(payload)
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
