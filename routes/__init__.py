import os

from flask import Blueprint, abort, g, redirect, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db import (
    create_verification_code,
    get_page_meta,
    get_user,
    get_user_by_username,
    verify_page_secret,
)
from mail import send_verification_email

limiter = Limiter(get_remote_address, storage_uri="memory://")

bp = Blueprint("routes", __name__)

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "jottit.localhost:8000")

LICENSES = {
    "all-rights-reserved": {"name": "\u00a9 All Rights Reserved", "url": None},
    "cc-by-4.0": {
        "name": "CC BY 4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
    },
    "cc-by-sa-4.0": {
        "name": "CC BY-SA 4.0",
        "url": "https://creativecommons.org/licenses/by-sa/4.0/",
    },
    "cc-by-nc-4.0": {
        "name": "CC BY-NC 4.0",
        "url": "https://creativecommons.org/licenses/by-nc/4.0/",
    },
    "cc-by-nc-sa-4.0": {
        "name": "CC BY-NC-SA 4.0",
        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    },
    "cc0": {
        "name": "CC0 (Public Domain)",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
}

VISIBILITY_OPTIONS = ("unlisted", "listed", "pinned")


def _get_subdomain():
    host = request.host
    if host.endswith("." + BASE_DOMAIN):
        return host[: -(len(BASE_DOMAIN) + 1)]
    return None


def compute_initials(user):
    name = user.get("name")
    if name:
        words = name.split()
        return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper()
    username = user.get("username") or ""
    return username[:2].upper()


def base_url(path=""):
    return f"{request.scheme}://{BASE_DOMAIN}{path}"


def profile_url(username, path=""):
    return f"/@{username}{path}"


def _set_profile_user(username):
    user = get_user_by_username(username)
    if not user:
        abort(404)
    g.subdomain_user = user
    g.url_prefix = f"/@{username}"
    return user


def find_page(slug):
    subdomain_user = g.subdomain_user
    if subdomain_user:
        return get_page_meta(slug, subdomain_user["id"])
    if session.get("user_id"):
        page_meta = get_page_meta(slug, session["user_id"])
        if page_meta:
            return page_meta
    return get_page_meta(slug)


def is_creator(page_meta):
    if not page_meta:
        return False
    slug = page_meta.get("slug", "")
    token = request.cookies.get(f"page_token_{slug}", "")
    return bool(token) and verify_page_secret(slug, token) is not None


def can_edit(page_meta):
    if not page_meta:
        return True
    if page_meta["user_id"] is not None:
        return session.get("user_id") == page_meta["user_id"]
    return is_creator(page_meta)


def send_verification(email, purpose):
    code = create_verification_code(email, purpose)
    send_verification_email(email, code)
    session[f"{purpose}_email"] = email


def account_link_vars():
    signed_in = "user_id" in session
    user = g.current_user if signed_in else None
    owner_avatar_url = user.get("avatar") if user else None
    owner_initials = compute_initials(user) if user else None
    account_profile_url = (
        profile_url(user["username"]) if user and user.get("username") else "/settings"
    )
    return {
        "signed_in": signed_in,
        "owner_avatar_url": owner_avatar_url,
        "owner_initials": owner_initials,
        "profile_url": account_profile_url,
    }


def require_user():
    user_id = session.get("user_id")
    if not user_id:
        return None, None
    user = getattr(g, "current_user", None) or get_user(user_id)
    if not user:
        return None, None
    return user_id, user


@bp.before_request
def validate_session():
    user_id = session.get("user_id")
    if user_id:
        user = get_user(user_id)
        if user:
            g.current_user = user
        else:
            session.pop("user_id", None)
            g.current_user = None
    else:
        g.current_user = None


@bp.before_request
def resolve_subdomain():
    subdomain = _get_subdomain()
    if subdomain == "www":
        return redirect(f"{request.scheme}://{BASE_DOMAIN}{request.full_path}", 301)
    if subdomain:
        path = request.full_path.rstrip("?")
        if path == "/":
            path = ""
        return redirect(f"{request.scheme}://{BASE_DOMAIN}/@{subdomain}{path}", 301)
    g.subdomain_user = None
    g.url_prefix = ""


@bp.before_request
def strip_trailing_slash():
    path = request.path
    if path != "/" and path.endswith("/"):
        query = request.query_string.decode()
        url = path.rstrip("/")
        if query:
            url = f"{url}?{query}"
        return redirect(url, 301)


@bp.app_context_processor
def inject_url_prefix():
    return {"url_prefix": getattr(g, "url_prefix", "")}


from routes import public, site, admin  # noqa: E402, F401
