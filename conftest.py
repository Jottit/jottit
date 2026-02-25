import db as db_module
import psycopg
import pytest

from app import app as flask_app

TEST_DB = "jottit_test"


@pytest.fixture(autouse=True)
def test_db():
    conn = psycopg.connect("dbname=postgres", autocommit=True)
    conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.execute(f"CREATE DATABASE {TEST_DB}")
    conn.close()

    db_module.DATABASE = f"dbname={TEST_DB}"

    conn = db_module.get_db()
    with open("schema.sql") as f:
        conn.execute(f.read())
    conn.commit()
    conn.close()

    yield

    db_module.DATABASE = "dbname=jottit_dev"

    conn = psycopg.connect("dbname=postgres", autocommit=True)
    conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.close()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
