"""Command line for the design loop and its parts.

Each subcommand is runnable on its own, so a broken piece never blocks the
rest. `rocinante doctor` first, always.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rocinante.blend import build_mesh, build_ship_mesh, render_ship_still, render_still
from rocinante.blend.run import blender_bin
from rocinante.diff import diff_derived, diff_specs
from rocinante.kord import KordClient
from rocinante.ork import read_ork, write_ork
from rocinante.sim import get_simulator

app = typer.Typer(add_completion=False, help="Rocket design, simulated and version controlled.")
console = Console()


@app.command()
def doctor() -> None:
    """Check every dependency the loop needs. Run this at 9am."""
    table = Table("Check", "Status", "Detail")

    blender = shutil.which(blender_bin()) or (
        blender_bin() if Path(blender_bin()).exists() else None
    )
    table.add_row("Blender", "ok" if blender else "MISSING", blender or "set BLENDER_BIN")

    # /usr/bin/java exists on macOS even with no JDK -- it is a stub that errors.
    try:
        java = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, timeout=20, check=False
        )
        java_ok = java.returncode == 0
        java_detail = (java.stderr or java.stdout).splitlines()[0] if java_ok else "stub only"
    except (OSError, subprocess.SubprocessError):
        java_ok, java_detail = False, "not found"
    table.add_row("Java", "ok" if java_ok else "MISSING", java_detail if java_ok else "brew install --cask temurin")

    jar = Path("vendor/OpenRocket-23.09.jar")
    table.add_row("OpenRocket jar", "ok" if jar.exists() else "MISSING", str(jar))

    for module in ("orhelper", "rocketpy", "openai"):
        try:
            __import__(module)
            table.add_row(module, "ok", "")
        except ImportError:
            table.add_row(module, "missing", f"uv pip install {module}")

    kord = KordClient()
    table.add_row("Kord", "ok" if kord.enabled else "offline", kord.base_url or "set KORD_API_*")

    console.print(table)


@app.command()
def sample(out: Path = typer.Option(Path("out/sample.ork"), "--out", "-o")) -> None:
    """Write a known-good rocket. The fixture everything else is tested against."""
    from rocinante.samples import BASELINE

    write_ork(BASELINE, out)
    console.print(f"wrote [bold]{out}[/] ({out.stat().st_size} bytes)")


@app.command("import")
def import_ork(path: Path) -> None:
    """Parse a .ork and print the spec. Seeds the agent from a human design."""
    console.print_json(read_ork(path).model_dump_json())


@app.command()
def simulate(path: Path, backend: str = typer.Option(None, "--backend", "-b")) -> None:
    """Fly one .ork file."""
    result = get_simulator(backend).run(read_ork(path))
    console.print(result.summary())


@app.command()
def mesh(path: Path, out: Path = typer.Option(Path("out/rocket.glb"), "--out", "-o")) -> None:
    """Build a .ork into a .glb through Blender."""
    console.print(f"wrote [bold]{build_mesh(read_ork(path), out)}[/]")


@app.command()
def hero(path: Path, out: Path = typer.Option(Path("out/hero.png"), "--out", "-o")) -> None:
    """The one Blender render. Save it for the end of the day."""
    console.print(f"rendered [bold]{render_still(read_ork(path), out)}[/]")


@app.command()
def diff(before: Path, after: Path) -> None:
    """Compare two .ork files as designs, not as bytes."""
    d = diff_specs(read_ork(before), read_ork(after))
    console.print(d.markdown())
    console.print(f"\nchanged parts: {', '.join(d.changed_parts) or 'none'}")


@app.command()
def design(
    goal: str = typer.Argument(..., help="e.g. '3000 ft apogee, stable, E motor'"),
    target_apogee_m: float = typer.Option(None, "--apogee"),
    iterations: int = typer.Option(12, "--iterations", "-n"),
    backend: str = typer.Option(None, "--backend", "-b"),
    out: Path = typer.Option(Path("out"), "--out"),
    no_mesh: bool = typer.Option(False, "--no-mesh", help="Skip Blender. Much faster."),
    approval: bool = typer.Option(False, "--approval", help="Wait on the Kord verdict."),
) -> None:
    """Run the design loop."""
    from rocinante.agent import DesignGoal, DesignLoop

    loop = DesignLoop(
        goal=DesignGoal(text=goal, target_apogee_m=target_apogee_m),
        out_dir=out,
        max_iterations=iterations,
        sim_backend=backend,
        build_meshes=not no_mesh,
        require_approval=approval,
    )

    def report(it) -> None:
        line = it.result.summary() if it.result else f"[red]{it.error}[/]"
        console.print(f"[bold]v{it.index}[/] {line}")
        if it.spec.rationale:
            console.print(f"      {it.spec.rationale}")

    loop.run(on_iteration=report)
    console.print(f"\n{len(loop.history)} iterations -> [bold]{out}/manifest.json[/]")


# --- the ship -----------------------------------------------------------


@app.command()
def ship(
    out: Path = typer.Option(None, "--out", "-o", help="Write the spec as JSON."),
) -> None:
    """Print the baseline Rocinante and everything derived from it."""
    from rocinante.samples import ROCINANTE

    console.print_json(ROCINANTE.model_dump_json())
    table = Table("Derived", "Value")
    for key, value in ROCINANTE.derived().items():
        table.add_row(key.replace("_", " "), f"{value:,.2f}")
    console.print(table)
    if ROCINANTE.crew_limited:
        console.print(
            f"[yellow]crew-limited:[/] the drive gives {ROCINANTE.max_accel_g:.1f} g, "
            f"the crew take {ROCINANTE.crew_g_limit:.1f} g"
        )
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(ROCINANTE.model_dump_json(indent=2))
        console.print(f"wrote [bold]{out}[/]")


@app.command("ship-mesh")
def ship_mesh(
    out: Path = typer.Option(Path("out/rocinante.glb"), "--out", "-o"),
    spec: Path = typer.Option(None, "--spec", help="A ShipSpec JSON. Defaults to baseline."),
) -> None:
    """Regenerate the ship from its spec, through Blender, to .glb."""
    from rocinante.ship import ShipSpec

    s = ShipSpec.model_validate_json(spec.read_text()) if spec else _baseline()
    console.print(f"wrote [bold]{build_ship_mesh(s, out)}[/]")


@app.command("ship-hero")
def ship_hero(out: Path = typer.Option(Path("out/hero.png"), "--out", "-o")) -> None:
    """The cold-open render. Once, at the end of the day."""
    console.print(f"rendered [bold]{render_ship_still(_baseline(), out)}[/]")


@app.command()
def burn(
    origin: str = typer.Argument("Tycho"),
    destination: str = typer.Argument("Ceres"),
    accel: float = typer.Option(1 / 3, "--accel", "-a", help="In g."),
) -> None:
    """Solve a constant-thrust transfer and check the ship can fly it."""
    from rocinante.flight import plan

    b = plan(_baseline(), origin, destination, accel)
    console.print(b.summary())
    for warning in b.warnings:
        console.print(f"  [yellow]! {warning}[/]")


@app.command()
def refit(
    ask: str = typer.Argument(..., help="e.g. 'eight more torpedoes, same burn time'"),
    out: Path = typer.Option(Path("out"), "--out"),
    no_mesh: bool = typer.Option(False, "--no-mesh", help="Skip Blender. Much faster."),
    no_kord: bool = typer.Option(False, "--no-kord", help="Skip the diff link."),
) -> None:
    """The beat: ask Astra for a change, regenerate, diff, file it with Kord."""
    from rocinante.agent import RefitAgent, model_name

    agent = RefitAgent(out_dir=out, build_meshes=not no_mesh)
    console.print(f"[dim]asking {model_name()}...[/]")
    result = agent.refit(_baseline(), ask)

    console.print(f"\n[bold]{result.after.rationale}[/]\n")
    console.print(result.diff.markdown())
    console.print(f"\n{diff_derived(result.before, result.after)}")
    if result.diff.changed_parts:
        console.print(f"parts to light: {', '.join(result.diff.changed_parts)}")

    if not no_kord:
        agent.file_with_kord(result)
        if result.share_url:
            console.print(f"\n3D diff: [bold]{result.share_url}[/]")
        if result.review_session_id:
            console.print(f"review session: {result.review_session_id}")

    (out / "refit.json").write_text(result.after.model_dump_json(indent=2))


@app.command()
def share(
    before: Path = typer.Argument(...),
    after: Path = typer.Argument(...),
    title: str = typer.Option(None, "--title", "-t"),
) -> None:
    """Mint a public Kord diff link for two files. No account needed."""
    result = KordClient().share_diff(before, after, title=title)
    console.print(f"[bold]{result['url']}[/]")
    console.print(f"[dim]expires {result.get('expiresAt', '?')}[/]")


def _baseline():
    from rocinante.samples import ROCINANTE

    return ROCINANTE


PUBLIC_KORD = "https://work.withkord.com"


@app.command()
def demo(
    out: Path = typer.Option(Path("out/workbench"), "--out", "-o"),
    port: int = typer.Option(3001, "--port", "-p"),
    live: bool | None = typer.Option(
        None, "--live/--fixture",
        help="Model proposals or fixture presets. Default: live when OPENAI_API_KEY is set.",
    ),
    kord: str = typer.Option(
        PUBLIC_KORD, "--kord",
        help="Kord instance for shared comparisons. Overrides KORD_API_BASE from .env.",
    ),
    chrome: bool = typer.Option(True, "--chrome/--no-chrome", help="Open the workbench in Chrome."),
    blender: bool = typer.Option(True, "--blender/--no-blender", help="Show the live Roci in Blender."),
    openrocket: bool = typer.Option(
        True, "--openrocket/--no-openrocket", help="Open the latest torpedo in OpenRocket."
    ),
) -> None:
    """The one command: serve the workbench and open Chrome, Blender and OpenRocket.

    Blender tracks the design under review and regenerates it on every proposal.
    OpenRocket gets the newest torpedo written fresh from its spec.
    """
    from rocinante.agent.refit import model_name
    from rocinante.demo import open_browser, open_openrocket, write_latest_torpedo
    from rocinante.workbench import Workbench, make_server

    has_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if live is None:
        live = has_key
    if live and not has_key:
        raise typer.BadParameter(
            "Live mode needs OPENAI_API_KEY. Put it in .env and launch with bin/roci demo, "
            "or pass --fixture."
        )
    os.environ["KORD_API_BASE"] = kord

    try:
        server = make_server(Workbench(out, live=live, show_blender=blender), port)
    except OSError as exc:
        console.print(f"[red]Port {port} is already in use ({exc.strerror}).[/]")
        console.print("Stop the other workbench, or run again with --port.")
        raise typer.Exit(1) from exc

    url = f"http://127.0.0.1:{port}/"
    table = Table("Window", "Shows", "Detail")
    table.add_row("Workbench", url, f"{'live ' + model_name() if live else 'fixture presets'}; "
                  f"state in {out / 'workbench.json'}")
    if chrome:
        table.add_row(open_browser(url), "review UI", url)
    if blender:
        table.add_row("Blender", "ship under review", f"watching {out / 'blender-current.json'}")
    if openrocket:
        ork_path, source = write_latest_torpedo(out)
        opened = open_openrocket(ork_path)
        table.add_row(opened or "OpenRocket", "latest torpedo" if opened else "NOT INSTALLED",
                      f"{ork_path} from {source}")
    table.add_row("Kord", "shared comparisons", kord)
    console.print(table)
    console.print("[dim]Ctrl-C stops the server; the app windows stay open.[/]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@app.command()
def viewer(
    out: Path = typer.Option(Path("out"), "--out", "-o"),
    port: int = typer.Option(8000, "--port", "-p"),
) -> None:
    """Serve the 3D diff viewer over the latest run."""
    web = Path(__file__).parent.parent.parent / "web"
    out.mkdir(parents=True, exist_ok=True)
    for f in web.iterdir():
        if f.is_file():
            shutil.copy(f, out / f.name)
    manifest = out / "manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"goal": "", "iterations": []}))
    console.print(f"http://localhost:{port}/")
    subprocess.run(
        ["python3", "-m", "http.server", str(port), "--directory", str(out)], check=False
    )


if __name__ == "__main__":
    app()
