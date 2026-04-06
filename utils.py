import difflib
import re
import secrets
import string
from datetime import datetime, timezone
from html import escape as html_escape

import mistune
from mistune.plugins.table import table as mistune_table_plugin
from mistune.plugins.url import url as mistune_url_plugin
import nh3

_mistune_md = mistune.create_markdown()
mistune_table_plugin(_mistune_md)
mistune_url_plugin(_mistune_md)


def _smartypants(html):
    """Convert ASCII punctuation to typographic equivalents in text nodes."""

    def _replace(text):
        # Unescape HTML entities so patterns can match uniformly
        text = text.replace("&quot;", '"')
        text = text.replace("&#x27;", "'")
        text = text.replace("&apos;", "'")
        text = text.replace("---", "\u2014")
        text = text.replace("--", "\u2013")
        text = text.replace("...", "\u2026")
        text = re.sub(r'(^|\s)"', "\\1\u201c", text)
        text = re.sub(r'"', "\u201d", text)
        text = re.sub(r"(\w)'(\w)", "\\1\u2019\\2", text)
        text = re.sub(r"(^|\s)'", "\\1\u2018", text)
        text = re.sub(r"'", "\u2019", text)
        return text

    parts = re.split(r"(<[^>]+>)", html)
    return "".join(_replace(p) if not p.startswith("<") else p for p in parts)


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

MAX_CONTENT_LENGTH = 200_000  # ~200KB, roughly 40k words

_SANITIZE_ATTRIBUTES = {**nh3.ALLOWED_ATTRIBUTES, "*": {"class"}}


def generate_slug(length=6):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_random_slug(slug):
    return bool(re.fullmatch(r"[a-z0-9]{6}", slug))


def render_markdown(text):
    html = _mistune_md(text)
    html = _smartypants(html)
    return nh3.clean(html, link_rel=None, attributes=_SANITIZE_ATTRIBUTES)


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def valid_email(s):
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", s))


def valid_username(s):
    return bool(re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", s))


def render_bio(text, url_prefix=""):
    def replace_md_link(m):
        display = html_escape(m.group(1))
        href = m.group(2)
        if url_prefix and not href.startswith(("http://", "https://", "/", "#")):
            href = f"{url_prefix}/{href}"
        href = html_escape(href)
        return f'<a href="{href}">{display}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", replace_md_link, text)
    return nh3.clean(text, tags={"a"}, attributes={"a": {"href"}}, link_rel=None)


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


def relative_time(value):
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - value
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


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
