import click

from jottit_cli.main import get_client


@click.command()
@click.pass_context
def whoami(ctx):
    """Show the authenticated user."""
    client, fmt = get_client(ctx)
    r = client.get("/user")
    if r.status_code != 200:
        fmt.error("Failed to get user info.")
    data = r.json()
    fmt.success(
        data=data,
        message=f"{data['username']} ({data.get('name') or data['email']})",
        quiet_value=data["username"],
        breadcrumbs=[
            {"label": "List pages", "command": "jottit list --json"},
            {"label": "Publish a page", "command": "jottit publish FILE --json"},
        ],
    )
