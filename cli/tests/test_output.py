import json

from jottit_cli.output import Formatter


def test_json_success(capsys):
    fmt = Formatter(use_json=True)
    fmt.success(
        data={"slug": "test"},
        breadcrumbs=[{"label": "List", "command": "jottit list"}],
    )
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["data"]["slug"] == "test"
    assert len(out["breadcrumbs"]) == 1


def test_quiet_success(capsys):
    fmt = Formatter(quiet=True)
    fmt.success(data={}, quiet_value="my-slug")
    assert capsys.readouterr().out.strip() == "my-slug"


def test_quiet_no_value(capsys):
    fmt = Formatter(quiet=True)
    fmt.success(data={}, quiet_value=None)
    assert capsys.readouterr().out == ""


def test_human_success(capsys):
    fmt = Formatter()
    fmt.success(data={}, message="Done!")
    assert "Done!" in capsys.readouterr().out
