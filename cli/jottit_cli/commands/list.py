import click

from jottit_cli.auth import get_client
from jottit_cli.output import console


def _relative_time(iso_str):
    if not iso_str:
        return ""
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        delta = now - dt
        if delta.days > 30:
            return dt.strftime("%b %d, %Y")
        if delta.days > 0:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        minutes = delta.seconds // 60
        if minutes > 0:
            return f"{minutes}m ago"
        return "just now"
    except (ValueError, TypeError):
        return iso_str


def _title_from_content(content):
    if not content:
        return ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line:
            return line[:60]
    return ""


@click.command("list")
@click.option("--drafts", is_flag=True, help="Show only drafts")
@click.option("--listing", type=click.Choice(["listed", "unlisted", "pinned"]))
@click.pass_context
def list_pages(ctx, drafts, listing):
    """List your pages."""
    client, fmt = get_client(ctx)
    r = client.get("/pages")
    if r.status_code != 200:
        fmt.error("Failed to list pages.")

    pages = r.json().get("pages", [])

    if drafts:
        pages = [p for p in pages if p.get("draft")]
    if listing:
        pages = [p for p in pages if p.get("listing") == listing]

    rows = []
    for p in pages:
        title = p.get("title") or _title_from_content(p.get("content", ""))
        rows.append(
            {
                "slug": p["slug"],
                "title": title,
                "listing": "draft" if p.get("draft") else p.get("listing", ""),
                "updated": _relative_time(p.get("updated_at")),
            }
        )

    if not rows and not fmt.use_json:
        console.print("No pages found.")
        return

    fmt.table(
        rows=rows,
        columns=["Slug", "Title", "Listing", "Updated"],
        data_list=pages,
        quiet_key="slug",
        breadcrumbs=[
            {"label": "Publish a page", "command": "jottit publish FILE --json"},
        ],
    )
