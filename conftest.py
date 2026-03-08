import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import db as db_module
import psycopg
import pytest

from app import app as flask_app
from routes import limiter

limiter.enabled = False

TEST_DB = "jottit_test"


@pytest.fixture(autouse=True)
def test_db():
    conn = psycopg.connect("dbname=postgres", autocommit=True)
    conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.execute(f"CREATE DATABASE {TEST_DB}")
    conn.close()

    db_module.DATABASE = f"dbname={TEST_DB}"
    db_module.reset_pool()

    with db_module.get_db() as conn:
        with open("schema.sql") as f:
            conn.execute(f.read())
        conn.commit()

    db_module.run_migrations()

    yield

    db_module.reset_pool()
    db_module.DATABASE = "dbname=jottit_dev"

    conn = psycopg.connect("dbname=postgres", autocommit=True)
    conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.close()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SESSION_COOKIE_DOMAIN"] = False
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as client:
        yield client
