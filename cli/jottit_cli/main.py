import click

from jottit_cli import __version__
from jottit_cli.commands.delete import delete
from jottit_cli.commands.edit import edit
from jottit_cli.commands.list import list_pages
from jottit_cli.commands.login import login
from jottit_cli.commands.publish import publish
from jottit_cli.commands.setup import setup
from jottit_cli.commands.whoami import whoami
from jottit_cli.output import Formatter


class _JottitGroup(click.Group):
    """Allow global flags (--json, --quiet) after the subcommand."""

    def parse_args(self, ctx, args):
        # Pull global flags from anywhere in args before parsing
        global_flags = {"--json", "--quiet"}
        pulled = set()
        remaining = []
        for arg in args:
            if arg in global_flags and arg not in pulled:
                pulled.add(arg)
                remaining.insert(0, arg)
            else:
                remaining.append(arg)
        return super().parse_args(ctx, remaining)


@click.group(cls=_JottitGroup)
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


cli.add_command(whoami)
cli.add_command(publish)
cli.add_command(list_pages, "list")
cli.add_command(edit)
cli.add_command(delete)
cli.add_command(login)
cli.add_command(setup)
