import click

from jottit_cli import __version__
from jottit_cli.config import load_config
from jottit_cli.client import JottitClient
from jottit_cli.output import Formatter


@click.group()
@click.option("--json", "use_json", is_flag=True, help="Output JSON with breadcrumbs")
@click.option("--quiet", is_flag=True, help="Minimal output")
@click.option("--token", help="API token (overrides config)")
@click.option("--base-url", help="API base URL (overrides config)")
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, use_json, quiet, token, base_url):
    """Jottit CLI — publish pages from the terminal."""
    ctx.ensure_object(dict)
    ctx.obj["formatter"] = Formatter(use_json=use_json, quiet=quiet)
    ctx.obj["token_override"] = token
    ctx.obj["base_url_override"] = base_url


def get_client(ctx):
    config = load_config(
        token_override=ctx.obj.get("token_override"),
        base_url_override=ctx.obj.get("base_url_override"),
    )
    fmt = ctx.obj["formatter"]
    if not config.token:
        fmt.error(
            "Not authenticated. Run 'jottit login' or set JOTTIT_TOKEN.",
            breadcrumbs=[{"label": "Login", "command": "jottit login"}],
        )
    return JottitClient(config), fmt


from jottit_cli.commands.whoami import whoami
from jottit_cli.commands.publish import publish
from jottit_cli.commands.list import list_pages
from jottit_cli.commands.edit import edit
from jottit_cli.commands.delete import delete
from jottit_cli.commands.login import login
from jottit_cli.commands.setup import setup

cli.add_command(whoami)
cli.add_command(publish)
cli.add_command(list_pages, "list")
cli.add_command(edit)
cli.add_command(delete)
cli.add_command(login)
cli.add_command(setup)
