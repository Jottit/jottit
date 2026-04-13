import json
import re

from flask import flash, jsonify, redirect, render_template, request, session

from db import (
    check_username_available,
    create_api_token,
    delete_api_token,
    delete_user,
    find_or_create_user,
    get_or_create_api_token,
    set_user_username,
    get_api_tokens,
    get_pages_for_user,
    get_user,
    update_user_avatar,
    update_user_email,
    update_user_settings,
    user_exists,
    verify_code,
)
from storage import (
    ALLOWED_IMAGE_TYPES,
    crop_square,
    delete_image,
    upload_image,
    validate_image,
)
from utils import RESERVED_USERNAMES, valid_email, valid_username
from routes import (
    bp,
    limiter,
    BASE_DOMAIN,
    LICENSES,
    profile_url,
    require_user,
    send_verification,
)


@bp.route("/signin", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def signin():
    if request.method == "GET":
        return render_template("signin.html")

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("signin.html", error="Email is required.")
    if not valid_email(email):
        return render_template(
            "signin.html", error="Please enter a valid email address."
        )

    send_verification(email, "signin")
    return redirect("/signin/verify")


@bp.route("/signin/verify", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def signin_verify():
    email = (
        (request.form.get("email") or session.get("signin_email") or "").strip().lower()
    )
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
    user = get_user(user_id)
    if user and user.get("username"):
        return redirect(profile_url(user["username"]))
    return redirect("/setup/username")


@bp.route("/signout", methods=["POST"])
def signout():
    session.pop("user_id", None)
    return redirect("/")


@bp.route("/setup/username", methods=["GET", "POST"])
def setup_username():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/signin")
    user = get_user(user_id)
    if user and user.get("username"):
        return redirect(profile_url(user["username"]))

    if request.method == "GET":
        return render_template("setup_username.html")

    username = request.form.get("username", "").strip().lower()
    if not username:
        return render_template("setup_username.html", error="Username is required.")
    if not valid_username(username):
        return render_template(
            "setup_username.html",
            error="Username must be lowercase letters, numbers, and hyphens only.",
            username=username,
        )
    if username in RESERVED_USERNAMES:
        return render_template(
            "setup_username.html",
            error="That username is reserved.",
            username=username,
        )
    if not check_username_available(username):
        return render_template(
            "setup_username.html",
            error="That username is already taken.",
            username=username,
        )

    set_user_username(user_id, username)
    update_user_settings(user_id, name="", username=username, bio="", license=None)
    return redirect(profile_url(username))


@bp.route("/setup/mcp-config", methods=["POST"])
def setup_mcp_config():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    user = get_user(user_id)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token, _ = get_or_create_api_token(user_id, "mcp-default")
    # If token already existed, we can't show the value (not stored).
    # Create a new one with a unique name instead.
    if token is None:
        token, _ = create_api_token(user_id, "mcp-default")

    username = user.get("username", "")
    config = {
        "mcpServers": {
            "jottit": {
                "command": "jottit-mcp",
                "env": {
                    "JOTTIT_API_TOKEN": token,
                },
            }
        }
    }
    return jsonify({"config": config, "config_text": json.dumps(config, indent=2)})


@bp.route("/pages")
def user_pages():
    from routes.public import _build_page_item, sidebar_vars, compute_initials

    user_id, user = require_user()
    if not user:
        return redirect("/signin")
    pages = get_pages_for_user(user_id)
    page_list = [_build_page_item(p) for p in pages]
    username = user.get("username")
    site_title = user.get("name") or username
    return render_template(
        "pages.html",
        pages=page_list,
        site_title=site_title,
        is_owner=True,
        avatar_url=user.get("avatar"),
        owner_initials=compute_initials(user),
        owner_avatar_url=user.get("avatar"),
        profile_incomplete=not user.get("avatar") and not user.get("bio"),
        license_info=LICENSES.get(user.get("license") or ""),
        profile_url=profile_url(username) if username else None,
        base_url=request.scheme + "://" + BASE_DOMAIN,
        **sidebar_vars(user_id, username, is_owner=True),
    )


@bp.route("/settings")
def user_settings():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    back_url = profile_url(user["username"]) if user.get("username") else "/"
    return render_template(
        "settings.html", user=user, back_url=back_url, licenses=LICENSES
    )


@bp.route("/settings/profile", methods=["GET", "POST"])
def settings_profile():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_profile.html", user=user)

    is_ajax = request.content_type and "application/json" in request.content_type
    if is_ajax:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()[:100]
        bio = data.get("bio", "").strip()[:500]
    else:
        name = request.form.get("name", "").strip()[:100]
        bio = request.form.get("bio", "").strip()[:500]

    update_user_settings(
        user_id, name, user.get("username") or "", bio, user.get("license")
    )

    if is_ajax:
        return {"ok": True}
    flash("Profile saved")
    return redirect("/settings/profile")


@bp.route("/settings/license", methods=["GET", "POST"])
def settings_license():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_license.html", user=user, licenses=LICENSES)

    license = request.form.get("license", "").strip()
    if license and license not in LICENSES:
        license = ""
    update_user_settings(
        user_id, user.get("name"), user.get("username") or "", user.get("bio"), license
    )
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True}
    flash("License saved")
    return redirect("/settings/license")


@bp.route("/settings/address", methods=["GET", "POST"])
def settings_address_redirect():
    return redirect("/settings/username", 301)


@bp.route("/settings/subdomain", methods=["GET", "POST"])
def settings_subdomain_redirect():
    return redirect("/settings/username", 301)


@bp.route("/settings/account", methods=["GET", "POST"])
def settings_account_redirect():
    return redirect("/settings/email", 301)


@bp.route("/settings/username", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def settings_username():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_username.html", user=user)

    username = request.form.get("username", "").strip().lower()

    error = None
    if username and username != user.get("username"):
        if not valid_username(username):
            error = "Username must be lowercase letters, numbers, and hyphens only."
        elif username in RESERVED_USERNAMES:
            error = "That username is reserved."
        elif not check_username_available(username):
            error = "That username is already taken."

    if error:
        return render_template(
            "settings_username.html",
            user={**user, "username": username},
            error=error,
        )

    update_user_settings(
        user_id,
        user.get("name") or "",
        username,
        user.get("bio") or "",
        user.get("license"),
    )
    flash("Saved")
    return redirect("/settings/username")


@bp.route("/settings/email", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def settings_email():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_email.html", user=user)

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template(
            "settings_email.html", user=user, error="Email is required."
        )
    if not valid_email(email):
        return render_template(
            "settings_email.html",
            user={**user, "email": email},
            error="Please enter a valid email address.",
        )
    if email == user["email"]:
        return redirect("/settings/email")
    if user_exists(email):
        return render_template(
            "settings_email.html",
            user={**user, "email": email},
            error="That email is already in use.",
        )

    send_verification(email, "email_change")
    session["email_change_new"] = email
    return redirect("/settings/email/verify")


@bp.route("/settings/email/verify", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def settings_email_verify():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    email = session.get("email_change_new")
    if not email:
        return redirect("/settings/email")

    if request.method == "GET":
        return render_template(
            "verify.html", email=email, action="/settings/email/verify"
        )

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "email_change"):
        return render_template(
            "verify.html",
            email=email,
            action="/settings/email/verify",
            error="Invalid or expired code.",
        )

    if user_exists(email):
        session.pop("email_change_new", None)
        flash("That email is already in use.")
        return redirect("/settings/email")

    update_user_email(user_id, email)
    session.pop("email_change_new", None)
    flash("Email updated")
    return redirect("/settings/email")


@bp.route("/settings/export")
def settings_export():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    return render_template("settings_export.html")


@bp.route("/settings/avatar", methods=["POST"])
@limiter.limit("5 per 5 minutes")
def settings_avatar():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    file = request.files.get("avatar")
    if not file:
        return redirect("/settings/profile")

    error = validate_image(file)
    if error:
        return render_template("settings_profile.html", user=user, error=f"{error}.")

    ext = ALLOWED_IMAGE_TYPES[file.content_type]
    fmt = file.content_type.split("/")[-1].upper()
    if fmt == "JPG":
        fmt = "JPEG"
    cropped = crop_square(file, fmt)
    key = f"{user_id}/avatar.{ext}"
    url = upload_image(key, cropped, file.content_type)
    update_user_avatar(user_id, url)
    return redirect("/settings/profile")


@bp.route("/settings/delete", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def settings_delete():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_delete.html")

    confirm = request.form.get("confirm", "").strip().lower()
    if confirm != "delete":
        return render_template(
            "settings_delete.html", error='Please type "delete" to confirm.'
        )

    delete_user(user_id)
    session.clear()
    return redirect("/")


@bp.route("/settings/tokens", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def settings_tokens():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    new_token = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        new_token, _ = create_api_token(user_id, name)

    tokens = get_api_tokens(user_id)
    return render_template("settings_tokens.html", tokens=tokens, new_token=new_token)


@bp.route("/settings/tokens/<int:token_id>/revoke", methods=["POST"])
@limiter.limit("10 per 5 minutes")
def settings_token_revoke(token_id):
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    delete_api_token(token_id, user_id)
    flash("Token revoked")
    return redirect("/settings/tokens")


@bp.route("/settings/avatar/delete", methods=["POST"])
@limiter.limit("5 per 5 minutes")
def settings_avatar_delete():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if user.get("avatar"):
        url = user["avatar"]
        if url.startswith("/uploads/"):
            key = url.removeprefix("/uploads/")
        else:
            key = "/".join(url.split("/")[3:])
        if key and re.match(r"^\d+/avatar\.\w+$", key):
            delete_image(key)
        update_user_avatar(user_id, None)
    return redirect("/settings/profile")
