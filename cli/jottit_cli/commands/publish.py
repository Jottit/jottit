import sys
import webbrowser
from pathlib import Path

import click

from jottit_cli.main import get_client


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
@click.option("--draft", is_flag=True, help="Publish as draft")
@click.option("--private", is_flag=True, help="Publish as private (only you can see)")
@click.option("--listing", type=click.Choice(["listed", "unlisted", "pinned"]), default=None)
@click.option("--title", help="Page title (prepended as # heading if missing)")
@click.option("--open", "open_browser", is_flag=True, help="Open in browser after publishing")
@click.pass_context
def publish(ctx, file, slug, draft, private, listing, title, open_browser):
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
    if draft:
        payload["draft"] = True
    if listing:
        payload["listing"] = listing

    r = client.post("/pages", json=payload)
    if r.status_code not in (200, 201):
        error = r.json().get("error", "Failed to publish page")
        fmt.error(error)

    data = r.json()
    page_slug = data["slug"]

    r2 = client.get("/user")
    username = r2.json().get("username") if r2.status_code == 200 else None
    url = client.page_url(page_slug, username)

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
