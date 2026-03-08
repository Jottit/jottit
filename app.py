import os
from datetime import datetime, timedelta, timezone

import sentry_sdk
from flask import Flask, render_template, request, session
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from db import init_db, run_migrations
from routes import bp, limiter
from utils import render_bio

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
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_DEBUG") != "1"
app.config["SESSION_COOKIE_DOMAIN"] = os.environ.get(
    "SESSION_COOKIE_DOMAIN", ".jottit.localhost"
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

CSRFProtect(app)
limiter.init_app(app)
app.register_blueprint(bp)


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
    return response


@app.template_filter("render_bio")
def render_bio_filter(value):
    if not value:
        return ""
    return render_bio(value)


@app.template_filter("isoformat")
def isoformat_filter(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


@app.template_filter("relative_time")
def relative_time_filter(value):
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


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


with app.app_context():
    init_db()
    run_migrations()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
