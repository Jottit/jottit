import sys
import webbrowser
from pathlib import Path

import click

from jottit_cli.auth import get_client
from jottit_cli.config import store_page_secret


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
    help="Page visibility (default: private, or unlisted if not signed in)",
)
@click.option("--title", help="Page title (prepended as # heading if missing)")
@click.option(
    "--open", "open_browser", is_flag=True, help="Open in browser after publishing"
)
@click.pass_context
def publish(ctx, file, slug, visibility, title, open_browser):
    """Publish a new page.

    Reads from FILE or stdin. Works without signing in — page will be
    unlisted and you can claim it later with 'jottit claim'.

      jottit publish notes.md

      cat notes.md | jottit publish
    """
    client, fmt = get_client(ctx, require_auth=False)
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
    page_secret = data.get("page_secret")

    url = (
        client.get_page_url(page_slug)
        if client.has_token
        else client.page_url(page_slug)
    )
    if page_secret:
        store_page_secret(page_slug, page_secret, url)

    if open_browser:
        webbrowser.open(url)

    breadcrumbs = [
        {"label": "Edit page", "command": f"jottit edit {page_slug} --json"},
        {"label": "Open in browser", "url": url},
    ]
    if page_secret:
        breadcrumbs.append(
            {"label": "Claim page", "command": f"jottit claim {page_slug}"}
        )
    else:
        breadcrumbs.append({"label": "List pages", "command": "jottit list --json"})

    fmt.success(
        data=data,
        message=f"Published: {url}",
        quiet_value=page_slug,
        breadcrumbs=breadcrumbs,
    )
