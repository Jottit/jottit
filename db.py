import psycopg
from psycopg.rows import dict_row

DATABASE = "dbname=jottit_dev"


def get_db():
    conn = psycopg.connect(DATABASE, row_factory=dict_row, autocommit=False)
    return conn


def init_db():
    conn = get_db()
    with open("schema.sql") as f:
        conn.execute(f.read())
    conn.commit()
    conn.close()
