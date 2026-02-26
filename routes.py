import difflib
import io
import json
import re
import secrets
import string
import zipfile
from email.utils import format_datetime
from html import escape as html_escape
from xml.sax.saxutils import escape as xml_escape

import markdown
from flask import (
    Blueprint,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
)

from db import (
    check_subdomain_available,
    claim_site,
    create_page,
    create_verification_code,
    find_or_create_user,
    get_export_pages,
    get_feed_entries,
    get_latest_revision,
    get_page,
    get_pages_for_site,
    get_revision,
    get_revisions,
    get_site,
    get_sites_for_user,
    get_user_email,
    remove_from_nav,
    save_page,
    update_nav_order,
    update_site_settings,
    verify_code,
)
from mail import send_verification_email

bp = Blueprint("routes", __name__)


def generate_slug(length=6):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _process_wikilinks(content, site_slug, existing_page_slugs=None):
    def replace(match):
        name = match.group(1).strip()
        if not name:
            return match.group(0)
        page_slug = _slugify(name)
        if not page_slug:
            return match.group(0)
        display = html_escape(name)
        if existing_page_slugs is not None and page_slug not in existing_page_slugs:
            return f'<a href="/{site_slug}/edit?page={page_slug}" class="wikilink-new">{display}</a>'
        return f'<a href="/{site_slug}/{page_slug}">{display}</a>'

    return re.sub(r"\[\[([^\[\]]+)\]\]", replace, content)


@bp.route("/")
def home():
    signed_in = "user_id" in session
    return render_template("home.html", signed_in=signed_in)


@bp.route("/new")
def new_page():
    slug = generate_slug()
    return redirect(f"/{slug}/edit")


@bp.route("/<slug>/edit", methods=["GET", "POST"])
def edit_page(slug):
    site = get_site(slug)
    if site and site["user_id"] is not None:
        if session.get("user_id") != site["user_id"]:
            return redirect(f"/{slug}")

    page_slug = (
        request.args.get("page")
        if request.method == "GET"
        else request.form.get("page")
    )

    if request.method == "GET":
        row = get_latest_revision(slug, page_slug)
        content = row["content"] if row else ""
        title = ""
        if content.startswith("# "):
            parts = content.split("\n", 1)
            title = parts[0][2:]
            content = parts[1].strip() if len(parts) > 1 else ""
        return render_template(
            "edit.html", slug=slug, title=title, content=content, page_slug=page_slug
        )

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    draft = "draft" in request.form

    if title:
        content = f"# {title}\n\n{content}"

    save_page(slug, content, draft, page_slug)
    if page_slug:
        return redirect(f"/{slug}/{page_slug}")
    return redirect(f"/{slug}")


@bp.route("/<slug>/claim", methods=["GET", "POST"])
def claim_page(slug):
    site = get_site(slug)
    if not site or site["user_id"] is not None:
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim.html", slug=slug)

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("claim.html", slug=slug, error="Email is required.")

    code = create_verification_code(email, "claim")
    send_verification_email(email, code)
    return render_template(
        "verify.html", slug=slug, email=email, action=f"/{slug}/claim/verify"
    )


@bp.route("/<slug>/claim/verify", methods=["GET", "POST"])
def claim_verify(slug):
    site = get_site(slug)
    if not site or site["user_id"] is not None:
        return redirect(f"/{slug}")

    email = request.form.get("email") or session.get("claim_email")
    if not email:
        return redirect(f"/{slug}/claim")

    if request.method == "GET":
        return render_template(
            "verify.html", slug=slug, email=email, action=f"/{slug}/claim/verify"
        )

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "claim"):
        return render_template(
            "verify.html",
            slug=slug,
            email=email,
            action=f"/{slug}/claim/verify",
            error="Invalid or expired code.",
        )

    user_id = find_or_create_user(email)
    claim_site(slug, user_id)
    session["user_id"] = user_id
    return redirect(f"/{slug}")


@bp.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "GET":
        return render_template("signin.html")

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("signin.html", error="Email is required.")

    code = create_verification_code(email, "signin")
    send_verification_email(email, code)
    return render_template("verify.html", email=email, action="/signin/verify")


@bp.route("/signin/verify", methods=["GET", "POST"])
def signin_verify():
    email = request.form.get("email") or session.get("signin_email")
    if not email:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("verify.html", email=email, action="/signin/verify")

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "signin"):
        return render_template(
            "verify.html",
            email=email,
            action="/signin/verify",
            error="Invalid or expired code.",
        )

    user_id = find_or_create_user(email)
    session.pop("signin_email", None)
    session["user_id"] = user_id
    return redirect("/")


@bp.route("/signout")
def signout():
    session.pop("user_id", None)
    return redirect("/")


@bp.route("/settings")
def settings():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/signin")

    sites = get_sites_for_user(user_id)
    email = get_user_email(user_id)
    return render_template("settings.html", sites=sites, email=email)


def _valid_subdomain(s):
    return bool(re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", s))


@bp.route("/<slug>/settings", methods=["GET", "POST"])
def site_settings(slug):
    user_id = session.get("user_id")
    site = get_site(slug)
    if not site or not user_id or site["user_id"] != user_id:
        return redirect(f"/{slug}")

    if request.method == "GET":
        pages = get_pages_for_site(site["id"])
        page_list = []
        for p in pages:
            title = _get_title(p["content"]) if p["content"] else None
            page_list.append(
                {
                    "id": p["id"],
                    "slug": p["slug"],
                    "title": title or p["slug"],
                    "nav_order": p["nav_order"],
                }
            )
        return render_template(
            "site_settings.html", site=site, pages=page_list, slug=slug
        )

    title = request.form.get("title", "").strip()
    subdomain = request.form.get("subdomain", "").strip().lower()

    error = None
    if subdomain:
        if not _valid_subdomain(subdomain):
            error = "Subdomain must be lowercase letters, numbers, and hyphens only."
        elif not check_subdomain_available(subdomain, site["id"]):
            error = "That subdomain is already taken."

    if error:
        pages = get_pages_for_site(site["id"])
        page_list = []
        for p in pages:
            ptitle = _get_title(p["content"]) if p["content"] else None
            page_list.append(
                {
                    "id": p["id"],
                    "slug": p["slug"],
                    "title": ptitle or p["slug"],
                    "nav_order": p["nav_order"],
                }
            )
        return render_template(
            "site_settings.html",
            site={**site, "title": title, "subdomain": subdomain},
            pages=page_list,
            slug=slug,
            error=error,
        )

    update_site_settings(site["id"], title, subdomain)
    return redirect(f"/{slug}/settings")


@bp.route("/<slug>/settings/nav", methods=["POST"])
def update_nav(slug):
    user_id = session.get("user_id")
    site = get_site(slug)
    if not site or not user_id or site["user_id"] != user_id:
        return redirect(f"/{slug}")

    page_ids = request.form.getlist("page_ids")
    for i, page_id in enumerate(page_ids):
        update_nav_order(int(page_id), i)

    return redirect(f"/{slug}/settings")


@bp.route("/<slug>/settings/nav/remove/<int:page_id>", methods=["POST"])
def remove_nav(slug, page_id):
    user_id = session.get("user_id")
    site = get_site(slug)
    if not site or not user_id or site["user_id"] != user_id:
        return redirect(f"/{slug}")

    remove_from_nav(page_id)
    return redirect(f"/{slug}/settings")


@bp.route("/<slug>/settings/add-page", methods=["POST"])
def add_page(slug):
    user_id = session.get("user_id")
    site = get_site(slug)
    if not site or not user_id or site["user_id"] != user_id:
        return redirect(f"/{slug}")

    page_slug = generate_slug()
    create_page(site["id"], page_slug)
    return redirect(f"/{slug}/edit?page={page_slug}")


@bp.route("/<slug>/export")
def export_site(slug):
    user_id = session.get("user_id")
    site = get_site(slug)
    if not site or not user_id or site["user_id"] != user_id:
        return redirect(f"/{slug}")

    pages = get_export_pages(slug)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for page in pages:
            title = _get_title(page["content"]) or page["page_slug"]
            body = _get_body(page["content"])
            date = page["created_at"].strftime("%Y-%m-%d")
            filename = page["page_slug"] if page["page_slug"] != "-" else "index"
            md = f"---\ntitle: {title}\ndate: {date}\n---\n\n{body}\n"
            zf.writestr(f"{slug}/{filename}.md", md)
    buf.seek(0)

    return Response(
        buf.getvalue(),
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


def _get_title(content):
    if content.startswith("# "):
        return content.split("\n", 1)[0][2:]
    return None


def _get_body(content):
    if content.startswith("# "):
        parts = content.split("\n", 1)
        return parts[1].strip() if len(parts) > 1 else ""
    return content


def _describe_change(prev, curr):
    old_title = _get_title(prev)
    new_title = _get_title(curr)

    if new_title != old_title and new_title:
        return f"Changed title to \u201c{new_title}\u201d"

    old_lines = prev.splitlines()
    new_lines = curr.splitlines()
    added = []
    removed = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, old_lines, new_lines
    ).get_opcodes():
        if tag == "insert":
            added.extend(new_lines[j1:j2])
        elif tag == "delete":
            removed.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed.extend(old_lines[i1:i2])
            added.extend(new_lines[j1:j2])

    # Skip the title line from snippets
    added = [line for line in added if not line.startswith("# ")]
    removed = [line for line in removed if not line.startswith("# ")]

    if added and not removed:
        snippet = added[0].strip()
        if snippet:
            return f"Added \u201c{snippet[:60]}\u201d"
        return f"Added {len(added)} line{'s' if len(added) != 1 else ''}"
    if removed and not added:
        snippet = removed[0].strip()
        if snippet:
            return f"Removed \u201c{snippet[:60]}\u201d"
        return f"Removed {len(removed)} line{'s' if len(removed) != 1 else ''}"
    if added and removed:
        old_snip = removed[0].strip()
        new_snip = added[0].strip()
        if old_snip and new_snip:
            return f"Changed \u201c{old_snip[:40]}\u201d to \u201c{new_snip[:40]}\u201d"

    return "Edited page"


@bp.route("/<slug>/history")
def page_history(slug):
    revisions = get_revisions(slug)

    if not revisions:
        abort(404)

    entries = []
    for i, rev in enumerate(revisions):
        if i == 0:
            description = None
        else:
            description = _describe_change(revisions[i - 1]["content"], rev["content"])
        entries.append(
            {
                "revision": rev["revision"],
                "created_at": rev["created_at"],
                "description": description,
            }
        )
    entries.reverse()

    return render_template("history.html", slug=slug, revisions=entries)


@bp.route("/<slug>/history/<int:revision>")
def view_revision(slug, revision):
    row = get_revision(slug, revision)

    if not row:
        abort(404)

    html = markdown.markdown(_process_wikilinks(row["content"], slug))
    return render_template(
        "revision.html",
        content=html,
        slug=slug,
        revision=row["revision"],
        created_at=row["created_at"],
    )


def _build_feed_entries(slug):
    entries = get_feed_entries(slug)
    base_url = request.url_root.rstrip("/")
    site_url = f"{base_url}/{slug}"
    items = []
    for entry in entries:
        page_slug = entry["page_slug"]
        page_url = site_url if page_slug == "-" else f"{base_url}/{page_slug}"
        body = _get_body(entry["content"])
        items.append(
            {
                "title": _get_title(entry["content"]) or slug,
                "url": page_url,
                "body": body,
                "body_html": markdown.markdown(_process_wikilinks(body, slug)),
                "created_at": entry["created_at"],
            }
        )
    return items, site_url


@bp.route("/<slug>/feed.xml")
def rss_feed(slug):
    site = get_site(slug)
    if not site:
        abort(404)

    items, site_url = _build_feed_entries(slug)
    site_title = site["title"] or slug

    last_build_date = format_datetime(items[0]["created_at"]) if items else ""

    items_xml = []
    for item in items:
        items_xml.append(
            "    <item>\n"
            f"      <title>{xml_escape(item['title'])}</title>\n"
            f"      <link>{xml_escape(item['url'])}</link>\n"
            f"      <pubDate>{format_datetime(item['created_at'])}</pubDate>\n"
            f"      <description>{item['body_html']}</description>\n"
            f"      <source:markdown>{item['body']}</source:markdown>\n"
            f'      <guid isPermaLink="true">{xml_escape(item["url"])}</guid>\n'
            "    </item>"
        )

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:source="http://source.scripting.com/">',
        "  <channel>",
        f"    <title>{xml_escape(site_title)}</title>",
        f"    <link>{xml_escape(site_url)}</link>",
        "    <description></description>",
        f"    <lastBuildDate>{last_build_date}</lastBuildDate>",
    ]
    parts.extend(items_xml)
    parts.append("  </channel>")
    parts.append("</rss>")
    xml = "\n".join(parts)

    return Response(xml, content_type="application/rss+xml; charset=utf-8")


@bp.route("/<slug>/feed.json")
def json_feed(slug):
    site = get_site(slug)
    if not site:
        abort(404)

    items, site_url = _build_feed_entries(slug)
    site_title = site["title"] or slug

    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": site_title,
        "home_page_url": site_url,
        "feed_url": f"{site_url}/feed.json",
        "items": [
            {
                "id": item["url"],
                "url": item["url"],
                "title": item["title"],
                "content_html": item["body_html"],
                "date_published": item["created_at"].isoformat(),
                "_source_markdown": item["body"],
            }
            for item in items
        ],
    }

    return Response(
        json.dumps(feed), content_type="application/feed+json; charset=utf-8"
    )


@bp.route("/<slug>")
@bp.route("/<slug>/<page_slug>")
def view_page(slug, page_slug=None):
    row = get_page(slug, page_slug)

    if not row:
        abort(404)

    site = get_site(slug)
    unclaimed = row["user_id"] is None
    is_owner = session.get("user_id") == row["user_id"] and not unclaimed
    show_actions = is_owner or unclaimed

    nav_pages = []
    existing_page_slugs = set()
    if site:
        pages = get_pages_for_site(site["id"])
        existing_page_slugs = {p["slug"] for p in pages}
        for p in pages:
            if p["nav_order"] is not None:
                title = _get_title(p["content"]) if p["content"] else None
                nav_pages.append({"slug": p["slug"], "title": title or p["slug"]})

    raw_content = row["content"]
    page_title = _get_title(raw_content)
    content = _process_wikilinks(raw_content, slug, existing_page_slugs)
    html = markdown.markdown(content)
    html = html.replace("<h1>", '<h1 class="p-name">', 1)

    return render_template(
        "page.html",
        content=html,
        draft=row["draft"],
        slug=slug,
        show_actions=show_actions,
        unclaimed=unclaimed,
        is_owner=is_owner,
        site_title=site["title"] if site else None,
        nav_pages=nav_pages,
        updated_at=row["created_at"],
        page_slug=page_slug,
        page_title=page_title,
    )
