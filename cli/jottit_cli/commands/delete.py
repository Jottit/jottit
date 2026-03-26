import click

from jottit_cli.auth import get_client


@click.command()
@click.argument("slug")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def delete(ctx, slug, yes):
    """Delete a page."""
    client, fmt = get_client(ctx)

    if not yes:
        if fmt.use_json or fmt.quiet:
            fmt.error("Use --yes to confirm deletion in non-interactive mode.")
        if not click.confirm(f'Delete "{slug}"?'):
            raise SystemExit(0)

    r = client.delete(f"/pages/{slug}")
    if r.status_code == 404:
        fmt.error(
            f"Page '{slug}' not found.",
            breadcrumbs=[{"label": "List pages", "command": "jottit list --json"}],
        )
    elif r.status_code not in (200, 204):
        fmt.error("Failed to delete page.")

    fmt.success(
        data={"slug": slug, "deleted": True},
        message="Deleted.",
        breadcrumbs=[
            {"label": "List pages", "command": "jottit list --json"},
            {"label": "Publish a page", "command": "jottit publish FILE --json"},
        ],
    )
