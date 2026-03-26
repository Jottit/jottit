import sys
from pathlib import Path

import click

from jottit_cli.main import get_client


@click.command()
@click.argument("slug")
@click.option("--file", "file_path", help="Read new content from file")
@click.option("--content", "inline_content", help="Content string")
@click.option("--draft/--no-draft", default=None, help="Set draft status")
@click.option("--listing", type=click.Choice(["listed", "unlisted", "pinned"]))
@click.pass_context
def edit(ctx, slug, file_path, inline_content, draft, listing):
    """Update an existing page.

    Content from --file, --content, or stdin:

      jottit edit my-page --file updated.md

      echo "new content" | jottit edit my-page
    """
    client, fmt = get_client(ctx)

    payload = {}

    if file_path:
        payload["content"] = Path(file_path).read_text()
    elif inline_content:
        payload["content"] = inline_content
    elif not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if stdin_content:
            payload["content"] = stdin_content

    if draft is not None:
        payload["draft"] = draft
    if listing:
        payload["listing"] = listing

    if not payload:
        raise click.UsageError(
            "Provide content via --file, --content, or stdin, "
            "or use --draft/--no-draft/--listing to update metadata."
        )

    r = client.put(f"/pages/{slug}", json=payload)
    if r.status_code == 404:
        fmt.error(
            f"Page '{slug}' not found.",
            breadcrumbs=[{"label": "List pages", "command": "jottit list --json"}],
        )
    if r.status_code != 200:
        error = r.json().get("error", "Failed to update page")
        fmt.error(error)

    data = r.json()

    r2 = client.get("/user")
    username = r2.json().get("username") if r2.status_code == 200 else None
    url = client.page_url(slug, username)

    fmt.success(
        data=data,
        message=f"Updated: {url}",
        quiet_value=slug,
        breadcrumbs=[
            {"label": "View page", "url": url},
            {"label": "List pages", "command": "jottit list --json"},
        ],
    )
