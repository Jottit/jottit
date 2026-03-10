import re

from flask import flash, redirect, render_template, request, session

from db import (
    check_username_available,
    delete_user,
    find_or_create_user,
    update_user_avatar,
    update_user_settings,
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
from routes import bp, limiter, LICENSES, require_user, send_verification, subdomain_url


@bp.route("/signin", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
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

    back_url = subdomain_url(user["username"]) if user.get("username") else "/"
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


@bp.route("/settings/subdomain", methods=["GET", "POST"])
def settings_subdomain():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_subdomain.html", user=user)

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
            "settings_subdomain.html",
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
    flash("Subdomain saved")
    return redirect("/settings/subdomain")


@bp.route("/settings/export")
def settings_export():
    user_id, user = require_user()
    if not user:
        return redirect("/signin")

    return render_template("settings_export.html")


@bp.route("/settings/avatar", methods=["POST"])
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


@bp.route("/settings/avatar/delete", methods=["POST"])
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
