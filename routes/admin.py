import re

from flask import flash, g, redirect, render_template, request, session

from db import (
    check_username_available,
    check_wiki_slug_available,
    create_api_token,
    create_wiki,
    delete_api_token,
    delete_user,
    find_or_create_user,
    get_api_tokens,
    get_default_wiki_for_user,
    get_user,
    get_wiki,
    get_wikis_for_user,
    update_user_avatar,
    update_user_email,
    update_user_settings,
    update_wiki,
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
from routes import bp, limiter, LICENSES, WIKI_VISIBILITY_OPTIONS, profile_url, require_user, send_verification, wiki_url


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

    if not user_exists(email):
        return render_template("signin.html", not_found=True)

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
    return redirect("/")


@bp.route("/signout", methods=["POST"])
def signout():
    session.pop("user_id", None)
    return redirect("/")


@bp.route("/settings")
def user_settings():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    back_url = "/"
    wikis = get_wikis_for_user(user_id)
    return render_template(
        "settings.html", user=user, back_url=back_url, licenses=LICENSES, wikis=wikis
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
    """License settings - now redirects to wiki settings since license is wiki-level."""
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    wikis = get_wikis_for_user(user_id)
    if not wikis:
        return redirect("/settings")

    if request.method == "GET":
        return render_template("settings_license.html", user=user, licenses=LICENSES, wikis=wikis)

    wiki_id = request.form.get("wiki_id", type=int)
    wiki = get_wiki(wiki_id) if wiki_id else None
    if not wiki or wiki["owner_id"] != user_id:
        return redirect("/settings/license")

    license = request.form.get("license", "").strip()
    if license and license not in LICENSES:
        license = ""
    update_wiki(wiki_id, license=license or None)
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


# --- Wiki management ---


@bp.route("/wiki/new", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def new_wiki():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("wiki_new.html")

    name = request.form.get("name", "").strip()[:100]
    slug = request.form.get("slug", "").strip().lower()[:64]
    visibility = request.form.get("visibility", "public")

    if not name:
        return render_template("wiki_new.html", error="Name is required.", slug=slug, name=name)

    if not slug:
        from utils import slugify
        slug = slugify(name)

    if not slug:
        return render_template("wiki_new.html", error="Slug is required.", slug=slug, name=name)

    if not valid_username(slug):
        return render_template(
            "wiki_new.html",
            error="Slug must be lowercase letters, numbers, and hyphens only.",
            slug=slug, name=name,
        )

    if slug in RESERVED_USERNAMES:
        return render_template("wiki_new.html", error="That slug is reserved.", slug=slug, name=name)

    if not check_wiki_slug_available(slug):
        return render_template(
            "wiki_new.html", error="That slug is already taken.", slug=slug, name=name
        )

    if visibility not in WIKI_VISIBILITY_OPTIONS:
        visibility = "public"

    wiki_id = create_wiki(slug, name, user_id, visibility)
    return redirect(wiki_url(slug))


@bp.route("/wiki/<int:wiki_id>/settings", methods=["GET", "POST"])
def wiki_settings(wiki_id):
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    wiki = get_wiki(wiki_id)
    if not wiki or wiki["owner_id"] != user_id:
        abort(404)

    if request.method == "GET":
        return render_template("wiki_settings.html", wiki=wiki, licenses=LICENSES)

    name = request.form.get("name", "").strip()[:100]
    visibility = request.form.get("visibility", wiki["visibility"])
    license = request.form.get("license", "").strip()

    if name:
        update_wiki(wiki_id, name=name)
    if visibility in WIKI_VISIBILITY_OPTIONS:
        update_wiki(wiki_id, visibility=visibility)
    if license is not None:
        if license and license not in LICENSES:
            license = ""
        update_wiki(wiki_id, license=license or None)

    flash("Wiki settings saved")
    return redirect(f"/wiki/{wiki_id}/settings")


from flask import abort  # noqa: E402
