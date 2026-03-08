import difflib
import re
import secrets
import string
from html import escape as html_escape

import markdown
import nh3

RESERVED_SLUGS = {
    "new",
    "signin",
    "signout",
    "settings",
    "about",
    "talk",
    "pages",
    "admin",
    "api",
    "static",
    "favicon.ico",
    "robots.txt",
    "sitemap.xml",
    "export",
}

RESERVED_USERNAMES = {
    "www",
    "api",
    "admin",
    "mail",
    "smtp",
    "ftp",
    "ns1",
    "ns2",
    "blog",
    "app",
    "static",
    "cdn",
    "assets",
}

_SANITIZE_ATTRIBUTES = {**nh3.ALLOWED_ATTRIBUTES, "*": {"class"}}


def generate_slug(length=6):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def render_markdown(text):
    html = markdown.markdown(text)
    return nh3.clean(html, link_rel=None, attributes=_SANITIZE_ATTRIBUTES)


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def valid_username(s):
    return bool(re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", s))


def process_wikilinks(content, existing_slugs=None):
    def replace(match):
        name = match.group(1).strip()
        if not name:
            return match.group(0)
        page_slug = slugify(name)
        if not page_slug:
            return match.group(0)
        display = html_escape(name)
        if existing_slugs is not None and page_slug not in existing_slugs:
            return f'<a href="/{page_slug}" class="wikilink-new">{display}</a>'
        return f'<a href="/{page_slug}">{display}</a>'

    return re.sub(r"\[\[([^\[\]]+)\]\]", replace, content)


def render_bio(text, existing_slugs=None):
    text = process_wikilinks(text, existing_slugs)
    text = re.sub(
        r"\[([^\]]+)\]\(([^\)]+)\)",
        lambda m: f'<a href="{html_escape(m.group(2))}">{html_escape(m.group(1))}</a>',
        text,
    )
    return nh3.clean(
        text, tags={"a"}, attributes={"a": {"href", "class"}}, link_rel=None
    )


def get_title(content):
    if not content or not content.startswith("# "):
        return None
    return content.split("\n", 1)[0][2:]


def get_body(content):
    if not content:
        return ""
    if content.startswith("# "):
        parts = content.split("\n", 1)
        return parts[1].strip() if len(parts) > 1 else ""
    return content


def get_description(content, max_length=200):
    body = get_body(content)
    if not body:
        return ""
    text = re.sub(r"[#*_\[\]`>]", "", body)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + "..."


def describe_change(prev, curr):
    old_title = get_title(prev)
    new_title = get_title(curr)

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
