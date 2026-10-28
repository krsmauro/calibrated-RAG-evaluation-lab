"""`ragcalibrate run` when the service cannot take queries: one line, no traceback."""

import pytest

from ragcalibrate.harness import cli
from ragcalibrate.harness.adapter import HttpSut, SutNotReady


def test_run_stops_with_one_line_when_the_service_is_not_ready(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def down(self: HttpSut) -> None:
        raise SutNotReady("cannot reach http://127.0.0.1:8000/ (ConnectError)")

    monkeypatch.setattr(HttpSut, "check_ready", down)
    # The check runs first, so this needs neither a service nor the eval-set files.
    assert cli.main(["run", "--strategy", "hybrid"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("ragcalibrate: cannot reach http://127.0.0.1:8000/ (ConnectError)")
    assert "make serve" in err
    assert len(err.splitlines()) == 1
