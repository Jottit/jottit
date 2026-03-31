import sys
from pathlib import Path

import click

from jottit_cli.auth import get_client
from jottit_cli.config import get_page_secret, list_page_secrets


@click.command()
@click.argument("slug", required=False)
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
    client, fmt = get_client(ctx, require_auth=False)

    if not slug:
        stored = list_page_secrets()
        if not stored:
            raise click.UsageError("No unclaimed pages found. Provide a SLUG argument.")
        if len(stored) > 1:
            slugs = ", ".join(stored.keys())
            raise click.UsageError(
                f"Multiple unclaimed pages found: {slugs}. Provide a SLUG argument."
            )
        slug = next(iter(stored))

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
    if not client.has_token:
        secret = get_page_secret(slug)
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
