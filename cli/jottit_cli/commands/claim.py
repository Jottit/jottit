import click

from jottit_cli.auth import get_client
from jottit_cli.config import get_page_secret, remove_page_secret


@click.command()
@click.argument("slug")
@click.pass_context
def claim(ctx, slug):
    """Claim an unclaimed page you published.

    Requires signing in first with 'jottit login'. Uses the page secret
    stored locally when you published without an account.

      jottit claim my-page
    """
    client, fmt = get_client(ctx)

    secret = get_page_secret(slug)
    if not secret:
        fmt.error(
            f"No page secret found for '{slug}'. You can only claim pages you published from this machine.",
        )

    r = client.post(
        f"/pages/{slug}/claim",
        headers={"X-Page-Secret": secret},
    )

    if r.status_code == 403:
        fmt.error("Invalid page secret or page already claimed.")
        return
    elif r.status_code == 409:
        fmt.error("Page already claimed.")
        return
    elif r.status_code != 200:
        error = r.json().get("error", "Failed to claim page")
        fmt.error(error)
        return

    remove_page_secret(slug)

    data = r.json()
    url = client.get_page_url(slug)

    fmt.success(
        data=data,
        message=f"Claimed: {url}",
        quiet_value=slug,
        breadcrumbs=[
            {"label": "Edit page", "command": f"jottit edit {slug} --json"},
            {"label": "View page", "url": url},
            {"label": "List pages", "command": "jottit list --json"},
        ],
    )
