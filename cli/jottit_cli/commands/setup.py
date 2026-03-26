import shutil
from importlib import resources
from pathlib import Path

import click


@click.command()
@click.argument("target", type=click.Choice(["claude"]))
@click.option(
    "--project", is_flag=True, help="Install to .claude/commands/ in current project"
)
@click.pass_context
def setup(ctx, target, project):
    """Set up Jottit integration with AI tools.

    Currently supports: claude
    """
    fmt = ctx.obj["formatter"]

    if target == "claude":
        _setup_claude(fmt, project)


def _setup_claude(fmt, project):
    if project:
        dest_dir = Path.cwd() / ".claude" / "commands"
    else:
        dest_dir = Path.home() / ".claude" / "commands"

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "jottit.md"

    source = resources.files("jottit_cli.data").joinpath("SKILL.md")
    with resources.as_file(source) as src_path:
        shutil.copy2(src_path, dest)

    location = "project" if project else "global"
    fmt.success(
        data={"target": "claude", "path": str(dest)},
        message=f"Installed Jottit skill to {dest}\n"
        f"Claude Code can now use 'jottit' commands ({location}).",
        quiet_value=str(dest),
        breadcrumbs=[
            {"label": "Check auth", "command": "jottit whoami --json"},
            {"label": "Publish a page", "command": "jottit publish FILE --json"},
        ],
    )
