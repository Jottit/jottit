import sys
from pathlib import Path

import click

from jottit_cli.auth import get_client, get_client_optional_auth
from jottit_cli.config import get_page_secret


@click.command()
@click.argument("slug")
@click.option("--file", "file_path", help="Read new content from file")
@click.option("--content", "inline_content", help="Content string")
@click.option(
    "--visibility",
    type=click.Choice(["private", "unlisted", "listed", "pinned"]),
    default=None,
    help="Set page visibility",
)
@click.pass_context
def edit(ctx, slug, file_path, inline_content, visibility):
    """Update an existing page.

    Content from --file, --content, or stdin:

      jottit edit my-page --file updated.md

      echo "new content" | jottit edit my-page
    """
    secret = get_page_secret(slug)
    if secret:
        client, fmt = get_client_optional_auth(ctx)
    else:
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

    if visibility:
        payload["visibility"] = visibility

    if not payload:
        raise click.UsageError(
            "Provide content via --file, --content, or stdin, "
            "or use --visibility to update metadata."
        )

    headers = {}
    if secret:
        headers["X-Page-Secret"] = secret

    r = client.put(f"/pages/{slug}", json=payload, headers=headers)
    if r.status_code == 404:
        fmt.error(
            f"Page '{slug}' not found.",
            breadcrumbs=[{"label": "List pages", "command": "jottit list --json"}],
        )
    elif r.status_code != 200:
        error = r.json().get("error", "Failed to update page")
        fmt.error(error)

    data = r.json()
    if secret:
        url = client.page_url(slug)
    else:
        url = client.get_page_url(slug)

    fmt.success(
        data=data,
        message=f"Updated: {url}",
        quiet_value=slug,
        breadcrumbs=[
            {"label": "View page", "url": url},
            {"label": "List pages", "command": "jottit list --json"},
        ],
    )
