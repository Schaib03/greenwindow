from greenwindow import cli


def test_plan_prints_the_greener_window(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GREENWINDOW_PROVIDER", "static")
    monkeypatch.setenv("GREENWINDOW_STATIC_FORECAST", "step=1h;700,700,700,250,250,700,700,700")
    svg = tmp_path / "plan.svg"

    code = cli.main(
        ["plan", "--duration", "2h", "--deadline", "7h", "--power-watts", "500", "--svg", str(svg)]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "◀ run" in out
    assert "700 → 250 gCO2eq/kWh" in out
    assert svg.read_text(encoding="utf-8").startswith("<svg")


def test_plan_runs_now_when_nothing_is_greener(monkeypatch, capsys):
    monkeypatch.setenv("GREENWINDOW_PROVIDER", "static")
    monkeypatch.setenv("GREENWINDOW_STATIC_FORECAST", "step=1h;300,300,300,300")
    assert cli.main(["plan", "--duration", "1h", "--deadline", "3h"]) == 0
    assert "Start now" in capsys.readouterr().out


def test_forecast_command(monkeypatch, capsys):
    monkeypatch.setenv("GREENWINDOW_PROVIDER", "static")
    monkeypatch.setenv("GREENWINDOW_STATIC_FORECAST", "step=1h;300,500,400,350")
    assert cli.main(["forecast", "--horizon", "3h"]) == 0
    assert "static" in capsys.readouterr().out


def test_errors_are_reported_cleanly(monkeypatch, capsys):
    monkeypatch.setenv("GREENWINDOW_PROVIDER", "electricitymaps")
    monkeypatch.delenv("ELECTRICITYMAPS_TOKEN", raising=False)
    assert cli.main(["forecast"]) == 1
    assert "ELECTRICITYMAPS_TOKEN" in capsys.readouterr().err
