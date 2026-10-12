"""Database Layer - Supabase PostgreSQL version"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime

# Supabase Connection String
DATABASE_URL = os.environ.get("DATABASE_URL", "YAHAN_APNI_URI_PASTE_KAREIN")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        full_name TEXT,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS students(
        id SERIAL PRIMARY KEY,
        roll_no TEXT UNIQUE,
        name TEXT,
        father TEXT,
        class_name TEXT,
        section TEXT,
        gender TEXT,
        contact TEXT,
        parent_contact TEXT,
        address TEXT,
        admission_date TEXT,
        transport_route TEXT
    );

    CREATE TABLE IF NOT EXISTS staff(
        id SERIAL PRIMARY KEY,
        emp_id TEXT UNIQUE,
        name TEXT,
        role TEXT,
        subject TEXT,
        qualification TEXT,
        contact TEXT,
        salary TEXT,
        join_date TEXT
    );
    """)
    conn.commit()
    c.close()
    conn.close()

def run(query, params=None, fetch=False, fetchone=False, commit=False):
    conn = get_db()
    c = conn.cursor()
    c.execute(query, params or ())
    result = None
    if fetch:
        result = c.fetchall()
    if fetchone:
        result = c.fetchone()
    if commit:
        conn.commit()
    c.close()
    conn.close()
    return result

# Initialize DB on import
init_db()
