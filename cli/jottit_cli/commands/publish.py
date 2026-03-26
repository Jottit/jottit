import sys
import webbrowser
from pathlib import Path

import click

from jottit_cli.auth import get_client


def _read_content(file, title):
    if file:
        content = Path(file).read_text()
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        raise click.UsageError("Provide a FILE argument or pipe content via stdin.")
    if title and not content.lstrip().startswith("# "):
        content = f"# {title}\n\n{content}"
    return content


@click.command()
@click.argument("file", required=False)
@click.option("--slug", help="Custom slug for the page")
@click.option(
    "--visibility",
    type=click.Choice(["private", "unlisted", "listed", "pinned"]),
    default=None,
    help="Page visibility (default: private)",
)
@click.option("--title", help="Page title (prepended as # heading if missing)")
@click.option(
    "--open", "open_browser", is_flag=True, help="Open in browser after publishing"
)
@click.pass_context
def publish(ctx, file, slug, visibility, title, open_browser):
    """Publish a new page.

    Reads from FILE or stdin:

      jottit publish notes.md

      cat notes.md | jottit publish
    """
    client, fmt = get_client(ctx)
    content = _read_content(file, title)

    payload = {"content": content}
    if slug:
        payload["slug"] = slug
    if visibility:
        payload["visibility"] = visibility

    r = client.post("/pages", json=payload)
    if r.status_code not in (200, 201):
        error = r.json().get("error", "Failed to publish page")
        fmt.error(error)

    data = r.json()
    page_slug = data["slug"]
    url = client.get_page_url(page_slug)

    if open_browser:
        webbrowser.open(url)

    fmt.success(
        data=data,
        message=f"Published: {url}",
        quiet_value=page_slug,
        breadcrumbs=[
            {"label": "Edit page", "command": f"jottit edit {page_slug} --json"},
            {"label": "Open in browser", "url": url},
            {"label": "List pages", "command": "jottit list --json"},
        ],
    )
