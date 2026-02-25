from datetime import datetime, timezone

from flask import Flask

from db import init_db
from routes import bp

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"
app.register_blueprint(bp)


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


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
