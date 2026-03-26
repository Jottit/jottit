import os
from pathlib import Path
from unittest.mock import patch

from jottit_cli.config import load_config, save_config


def test_load_config_empty():
    with patch.object(Path, "exists", return_value=False):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()
    assert config.token is None
    assert config.base_url == "https://jottit.org"


def test_load_config_from_file(tmp_path):
    rc = tmp_path / ".jottitrc"
    rc.write_text("token = jot_test123\nbase_url = http://localhost:5000\n")
    with patch("jottit_cli.config.CONFIG_PATH", rc):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()
    assert config.token == "jot_test123"
    assert config.base_url == "http://localhost:5000"


def test_load_config_env_overrides_file(tmp_path):
    rc = tmp_path / ".jottitrc"
    rc.write_text("token = file_token\n")
    with patch("jottit_cli.config.CONFIG_PATH", rc):
        with patch.dict(os.environ, {"JOTTIT_TOKEN": "env_token"}, clear=True):
            config = load_config()
    assert config.token == "env_token"


def test_load_config_override_param():
    with patch.object(Path, "exists", return_value=False):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(token_override="override_token")
    assert config.token == "override_token"


def test_save_config(tmp_path):
    rc = tmp_path / ".jottitrc"
    with patch("jottit_cli.config.CONFIG_PATH", rc):
        save_config("jot_saved")
    content = rc.read_text()
    assert "token = jot_saved" in content
    assert oct(rc.stat().st_mode)[-3:] == "600"


def test_save_config_with_custom_base_url(tmp_path):
    rc = tmp_path / ".jottitrc"
    with patch("jottit_cli.config.CONFIG_PATH", rc):
        save_config("jot_saved", "http://localhost:5000")
    content = rc.read_text()
    assert "base_url = http://localhost:5000" in content
