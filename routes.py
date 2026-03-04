import io
import json
import os
import zipfile
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db import (
    check_subdomain_available,
    claim_site,
    create_verification_code,
    find_or_create_user,
    get_export_pages,
    get_feed_entries,
    get_page,
    get_pages_for_site,
    get_revision,
    get_revisions,
    get_site,
    get_site_by_subdomain,
    get_sites_for_user,
    save_page,
    update_site_settings,
    verify_code,
)
from mail import send_verification_email
from utils import (
    RESERVED_SLUGS,
    RESERVED_SUBDOMAINS,
    describe_change,
    generate_slug,
    get_body,
    get_title,
    parse_nav,
    process_wikilinks,
    render_markdown,
    valid_subdomain,
)

limiter = Limiter(get_remote_address, storage_uri="memory://")

bp = Blueprint("routes", __name__)

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "jottit.localhost:8000")


def _get_subdomain():
    host = request.host
    if host.endswith("." + BASE_DOMAIN):
        return host[: -(len(BASE_DOMAIN) + 1)]
    return None


def _subdomain_url(subdomain, path=""):
    scheme = request.scheme
    return f"{scheme}://{subdomain}.{BASE_DOMAIN}{path}"


@bp.before_request
def resolve_subdomain():
    subdomain = _get_subdomain()
    if subdomain == "www":
        return redirect(f"{request.scheme}://{BASE_DOMAIN}{request.full_path}", 301)
    if not subdomain:
        g.subdomain_site = None
        return
    site = get_site_by_subdomain(subdomain)
    if not site:
        abort(404)
    g.subdomain_site = site


@bp.route("/")
def home():
    site = g.subdomain_site
    if site:
        return view_page(site["slug"])

    signed_in = "user_id" in session
    sites = []
    has_more_sites = False
    if signed_in:
        user_id = session["user_id"]
        sites = get_sites_for_user(user_id, limit=4)
        has_more_sites = len(sites) > 3
        sites = sites[:3]
    return render_template(
        "home.html", signed_in=signed_in, sites=sites, has_more_sites=has_more_sites
    )


@bp.route("/about")
def about():
    return render_template("about.html", signed_in="user_id" in session)


@bp.route("/talk")
def talk():
    return render_template("talk.html", signed_in="user_id" in session)


@bp.route("/sites")
def sites_list():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/signin")
    sites = get_sites_for_user(user_id)
    return render_template("sites.html", sites=sites)


def _require_subdomain_site():
    site = g.subdomain_site
    if not site:
        abort(404)
    return site


@bp.route("/edit", methods=["GET", "POST"])
def subdomain_edit():
    site = _require_subdomain_site()
    return edit_page(site["slug"])


@bp.route("/export")
def subdomain_export():
    site = _require_subdomain_site()
    return export_site(site["slug"])


@bp.route("/history")
def subdomain_history():
    site = _require_subdomain_site()
    return page_history(site["slug"])


@bp.route("/history/<int:revision>")
def subdomain_revision(revision):
    site = _require_subdomain_site()
    return view_revision(site["slug"], revision)


@bp.route("/claim", methods=["GET", "POST"])
def subdomain_claim():
    site = _require_subdomain_site()
    return claim_page(site["slug"])


@bp.route("/claim/verify", methods=["GET", "POST"])
def subdomain_claim_verify():
    site = _require_subdomain_site()
    return claim_verify(site["slug"])


@bp.route("/settings")
def subdomain_settings():
    site = _require_subdomain_site()
    return site_settings(site["slug"])


@bp.route("/feed.xml")
def subdomain_rss():
    site = _require_subdomain_site()
    return rss_feed(site["slug"])


@bp.route("/feed.json")
def subdomain_json_feed():
    site = _require_subdomain_site()
    return json_feed(site["slug"])


@bp.route("/new")
def new_page():
    slug = generate_slug()
    return redirect(f"/{slug}/edit")


@bp.route("/<slug>/edit", methods=["GET", "POST"])
def edit_page(slug):
    site = get_site(slug)
    if not site and slug in RESERVED_SLUGS:
        abort(404)
    if site and site["user_id"] is not None:
        if session.get("user_id") != site["user_id"]:
            return redirect(f"/{slug}")

    page_slug = (
        request.args.get("page")
        if request.method == "GET"
        else request.form.get("page")
    )

    if request.method == "GET":
        row = get_page(slug, page_slug)
        content = row["content"] if row else ""
        title = get_title(content) or ""
        content = get_body(content)
        return render_template(
            "edit.html", slug=slug, title=title, content=content, page_slug=page_slug
        )

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    draft = "draft" in request.form

    if title:
        content = f"# {title}\n\n{content}"

    is_new = site is None
    save_page(slug, content, draft, page_slug)
    if is_new and session.get("user_id"):
        claim_site(slug, session["user_id"])
    if page_slug:
        return redirect(f"/{slug}/{page_slug}")
    return redirect(f"/{slug}")


@bp.route("/<slug>/claim", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
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
@limiter.limit("5 per 10 minutes", methods=["POST"])
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
@limiter.limit("5 per hour", methods=["POST"])
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
@limiter.limit("5 per 10 minutes", methods=["POST"])
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


@bp.route("/signout", methods=["POST"])
def signout():
    session.pop("user_id", None)
    return redirect("/")


@bp.route("/<slug>/settings", methods=["GET", "POST"])
def site_settings(slug):
    user_id = session.get("user_id")
    site = get_site(slug)
    if not site or not user_id or site["user_id"] != user_id:
        return redirect(f"/{slug}")

    if request.method == "GET":
        nav_text = site["nav"] or ""
        return render_template(
            "site_settings.html", site=site, nav_text=nav_text, slug=slug
        )

    title = request.form.get("title", "").strip()
    subdomain = request.form.get("subdomain", "").strip().lower()
    nav = request.form.get("nav", "").strip()

    error = None
    if subdomain and subdomain != site["subdomain"]:
        if not valid_subdomain(subdomain):
            error = "Subdomain must be lowercase letters, numbers, and hyphens only."
        elif subdomain in RESERVED_SUBDOMAINS:
            error = "That subdomain is reserved."
        elif not check_subdomain_available(subdomain):
            error = "That subdomain is already taken."

    if error:
        return render_template(
            "site_settings.html",
            site={**site, "title": title, "subdomain": subdomain},
            nav_text=nav,
            slug=slug,
            error=error,
        )

    update_site_settings(site["id"], title, subdomain, nav)
    flash("Changes saved")
    if subdomain:
        return redirect(_subdomain_url(subdomain, "/settings"))
    return redirect(f"/{slug}/settings")


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
            title = get_title(page["content"]) or page["page_slug"]
            body = get_body(page["content"])
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
            description = describe_change(revisions[i - 1]["content"], rev["content"])
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

    html = render_markdown(process_wikilinks(row["content"], slug))
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
        body = get_body(entry["content"])
        items.append(
            {
                "title": get_title(entry["content"]) or slug,
                "url": page_url,
                "body": body,
                "body_html": render_markdown(process_wikilinks(body, slug)),
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
            f"      <description><![CDATA[{item['body_html']}]]></description>\n"
            f"      <source:markdown>{xml_escape(item['body'])}</source:markdown>\n"
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
    subdomain_site = g.subdomain_site
    if subdomain_site and slug != subdomain_site["slug"]:
        page_slug = slug
        slug = subdomain_site["slug"]

    site = subdomain_site or get_site(slug)
    if not subdomain_site and site and site["subdomain"]:
        path = f"/{page_slug}" if page_slug else ""
        return redirect(_subdomain_url(site["subdomain"], path))

    row = get_page(slug, page_slug)

    if not row:
        abort(404)
    unclaimed = row["user_id"] is None
    is_owner = session.get("user_id") == row["user_id"] and not unclaimed
    show_actions = is_owner or unclaimed

    nav_pages = []
    existing_page_slugs = set()
    if site:
        pages = get_pages_for_site(site["id"])
        existing_page_slugs = {p["slug"] for p in pages}
        for item in parse_nav(site["nav"]):
            item_slug = item["slug"]
            is_index = item_slug == "index"
            exists = (
                "-" in existing_page_slugs
                if is_index
                else item_slug in existing_page_slugs
            )
            nav_pages.append(
                {
                    "slug": item_slug,
                    "title": item["label"],
                    "exists": exists,
                    "is_index": is_index,
                }
            )

    page_title = get_title(row["content"])
    content = process_wikilinks(row["content"], slug, existing_page_slugs)
    html = render_markdown(content)
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
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
    )
