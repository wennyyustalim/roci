import signal

from typer.testing import CliRunner

from rocinante import cli

runner = CliRunner()


def test_kill_stops_demo_listener(monkeypatch):
    monkeypatch.setattr(cli, "_listener_pids", lambda port: [123])
    monkeypatch.setattr(cli, "_process_command", lambda pid: "/tmp/.venv/bin/roci demo")
    sent = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))

    result = runner.invoke(cli.app, ["kill"])

    assert result.exit_code == 0
    assert sent == [(123, signal.SIGTERM)]
    assert "Stopped roci demo on port 3001" in result.stdout


def test_kill_refuses_unrelated_listener(monkeypatch):
    monkeypatch.setattr(cli, "_listener_pids", lambda port: [456])
    monkeypatch.setattr(cli, "_process_command", lambda pid: "python unrelated_server.py")
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: (_ for _ in ()).throw(AssertionError()))

    result = runner.invoke(cli.app, ["kill", "--port", "4000"])

    assert result.exit_code == 1
    assert "not a roci demo" in result.stdout


def test_kill_when_nothing_is_running(monkeypatch):
    monkeypatch.setattr(cli, "_listener_pids", lambda port: [])

    result = runner.invoke(cli.app, ["kill"])

    assert result.exit_code == 0
    assert "No demo server is listening" in result.stdout
