import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from jottit_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def _mock_config(token="jot_test"):
    from jottit_cli.config import Config

    return Config(token=token, base_url="http://localhost:5000")


def _mock_response(status_code=200, json_data=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data or {}
    return r


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestWhoami:
    @patch("jottit_cli.commands.whoami.get_client")
    def test_whoami_human(self, mock_gc, runner):
        client = MagicMock()
        client.get.return_value = _mock_response(
            200,
            {
                "username": "simon",
                "name": "Simon",
                "email": "s@example.com",
            },
        )
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())
        result = runner.invoke(cli, ["whoami"])
        assert result.exit_code == 0
        assert "simon" in result.output

    @patch("jottit_cli.commands.whoami.get_client")
    def test_whoami_json(self, mock_gc, runner):
        client = MagicMock()
        client.get.return_value = _mock_response(
            200,
            {
                "username": "simon",
                "name": "Simon",
                "email": "s@example.com",
            },
        )
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter(use_json=True))
        result = runner.invoke(cli, ["--json", "whoami"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["username"] == "simon"
        assert "breadcrumbs" in data


class TestPublish:
    @patch("jottit_cli.commands.publish.get_client")
    def test_publish_file(self, mock_gc, runner, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello\n\nWorld")

        client = MagicMock()
        client.post.return_value = _mock_response(201, {"slug": "hello"})
        client.get.return_value = _mock_response(200, {"username": "simon"})
        client.page_url.return_value = "http://localhost:5000/@simon/hello"
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["publish", str(md_file)])
        assert result.exit_code == 0
        assert "Published" in result.output
        client.post.assert_called_once()
        call_json = client.post.call_args[1]["json"]
        assert "# Hello" in call_json["content"]

    @patch("jottit_cli.commands.publish.get_client")
    def test_publish_stdin(self, mock_gc, runner):
        client = MagicMock()
        client.post.return_value = _mock_response(201, {"slug": "stdin-page"})
        client.get.return_value = _mock_response(200, {"username": "simon"})
        client.page_url.return_value = "http://localhost:5000/@simon/stdin-page"
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["publish"], input="# From stdin\n\nHello")
        assert result.exit_code == 0
        call_json = client.post.call_args[1]["json"]
        assert "From stdin" in call_json["content"]

    @patch("jottit_cli.commands.publish.get_client")
    def test_publish_quiet(self, mock_gc, runner, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello")

        client = MagicMock()
        client.post.return_value = _mock_response(201, {"slug": "hello"})
        client.get.return_value = _mock_response(200, {"username": "simon"})
        client.page_url.return_value = "http://localhost:5000/@simon/hello"
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter(quiet=True))

        result = runner.invoke(cli, ["--quiet", "publish", str(md_file)])
        assert result.exit_code == 0
        assert result.output.strip() == "hello"

    @patch("jottit_cli.commands.publish.get_client")
    def test_publish_with_title(self, mock_gc, runner, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("No heading here, just content.")

        client = MagicMock()
        client.post.return_value = _mock_response(201, {"slug": "my-title"})
        client.get.return_value = _mock_response(200, {"username": "simon"})
        client.page_url.return_value = "http://localhost:5000/@simon/my-title"
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["publish", str(md_file), "--title", "My Title"])
        assert result.exit_code == 0
        call_json = client.post.call_args[1]["json"]
        assert call_json["content"].startswith("# My Title\n\n")


class TestList:
    @patch("jottit_cli.commands.list.get_client")
    def test_list_json(self, mock_gc, runner):
        client = MagicMock()
        client.get.return_value = _mock_response(
            200,
            {
                "pages": [
                    {
                        "slug": "page-1",
                        "title": "Page 1",
                        "visibility": "listed",
                        "updated_at": "2026-03-26T10:00:00+00:00",
                    },
                    {
                        "slug": "page-2",
                        "title": "Page 2",
                        "visibility": "unlisted",
                        "updated_at": "2026-03-25T10:00:00+00:00",
                    },
                ]
            },
        )
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter(use_json=True))

        result = runner.invoke(cli, ["--json", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]) == 2

    @patch("jottit_cli.commands.list.get_client")
    def test_list_quiet(self, mock_gc, runner):
        client = MagicMock()
        client.get.return_value = _mock_response(
            200,
            {
                "pages": [
                    {"slug": "page-1", "draft": False, "listing": "listed"},
                    {"slug": "page-2", "draft": False, "listing": "listed"},
                ]
            },
        )
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter(quiet=True))

        result = runner.invoke(cli, ["--quiet", "list"])
        assert result.exit_code == 0
        slugs = result.output.strip().split("\n")
        assert slugs == ["page-1", "page-2"]


class TestEdit:
    @patch("jottit_cli.commands.edit.get_page_secret", return_value=None)
    @patch("jottit_cli.commands.edit.get_client")
    def test_edit_with_file(self, mock_gc, mock_gps, runner, tmp_path):
        md_file = tmp_path / "updated.md"
        md_file.write_text("# Updated\n\nNew content")

        client = MagicMock()
        client.put.return_value = _mock_response(200, {"slug": "my-page"})
        client.get.return_value = _mock_response(200, {"username": "simon"})
        client.page_url.return_value = "http://localhost:5000/@simon/my-page"
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["edit", "my-page", "--file", str(md_file)])
        assert result.exit_code == 0
        assert "Updated" in result.output

    @patch("jottit_cli.commands.edit.get_page_secret", return_value=None)
    @patch("jottit_cli.commands.edit.get_client")
    def test_edit_metadata_only(self, mock_gc, mock_gps, runner):
        client = MagicMock()
        client.put.return_value = _mock_response(200, {"slug": "my-page"})
        client.get.return_value = _mock_response(200, {"username": "simon"})
        client.page_url.return_value = "http://localhost:5000/@simon/my-page"
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["edit", "my-page", "--visibility", "listed"])
        assert result.exit_code == 0
        call_json = client.put.call_args[1]["json"]
        assert call_json == {"visibility": "listed"}


class TestDelete:
    @patch("jottit_cli.commands.delete.get_client")
    def test_delete_with_yes(self, mock_gc, runner):
        client = MagicMock()
        client.delete.return_value = _mock_response(200, {})
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["delete", "my-page", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    @patch("jottit_cli.commands.delete.get_client")
    def test_delete_confirms(self, mock_gc, runner):
        client = MagicMock()
        client.delete.return_value = _mock_response(200, {})
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter())

        result = runner.invoke(cli, ["delete", "my-page"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted" in result.output

    @patch("jottit_cli.commands.delete.get_client")
    def test_delete_json_requires_yes(self, mock_gc, runner):
        client = MagicMock()
        from jottit_cli.output import Formatter

        mock_gc.return_value = (client, Formatter(use_json=True))

        result = runner.invoke(cli, ["--json", "delete", "my-page"])
        assert result.exit_code != 0
