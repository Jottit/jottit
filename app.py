import hashlib
import os
from datetime import timedelta

import sentry_sdk
from flask import Flask, render_template, request, session
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from db import init_db, run_migrations
from routes import bp, limiter
from utils import relative_time, render_bio

dsn = os.environ.get("SENTRY_DSN")
if dsn:
    sentry_sdk.init(dsn=dsn, send_default_pii=False)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.url_map.strict_slashes = False

app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    if os.environ.get("FLASK_DEBUG") == "1":
        app.secret_key = "dev-secret-key"
    else:
        raise RuntimeError("SECRET_KEY environment variable is required")

app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_DEBUG") != "1",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_DOMAIN=os.environ.get("SESSION_COOKIE_DOMAIN", ".jottit.localhost"),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

CSRFProtect(app)
limiter.init_app(app)
app.register_blueprint(bp)


# --- Asset versioning ---


def _compute_asset_v():
    h = hashlib.md5()
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    for f in sorted(os.listdir(static_dir)):
        path = os.path.join(static_dir, f)
        if os.path.isfile(path):
            h.update(open(path, "rb").read())
    return h.hexdigest()[:8]


app.jinja_env.globals["asset_v"] = _compute_asset_v()


@app.context_processor
def inject_asset_v():
    if app.debug:
        return {"asset_v": _compute_asset_v()}
    return {}


# --- Middleware ---


@app.before_request
def make_session_permanent():
    session.permanent = True


_CSP = (
    "default-src 'self'; script-src 'self' https://static.cloudflareinsights.com;"
    " connect-src 'self' https://cloudflareinsights.com; style-src 'self';"
    " img-src 'self' https://*.fly.storage.tigris.dev"
)


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    response.headers["Content-Security-Policy"] = _CSP

    if "Cache-Control" not in response.headers:
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path.endswith(("/feed.xml", "/feed.json")):
            response.headers["Cache-Control"] = "public, max-age=300"
        elif request.path == "/sitemap.xml":
            response.headers["Cache-Control"] = "public, max-age=3600"

    return response


# --- Template filters ---

app.template_filter("render_bio")(lambda v: render_bio(v) if v else "")
app.template_filter("relative_time")(relative_time)


@app.template_filter("isoformat")
def isoformat_filter(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


# --- Error handlers ---


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


# --- Init ---

with app.app_context():
    init_db()
    run_migrations()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
