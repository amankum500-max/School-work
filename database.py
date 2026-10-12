"""Database Layer - Supabase PostgreSQL version"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime

# Supabase Connection String
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:Aman%40852125@db.nxdiowbskqvlrudxpbh.supabase.co:5432/postgres")

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
        mother TEXT,
        class_name TEXT,
        section TEXT,
        gender TEXT,
        dob TEXT,
        contact TEXT,
        parent_contact TEXT,
        address TEXT,
        admission_date TEXT,
        transport_route TEXT,
        hostel TEXT
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

    CREATE TABLE IF NOT EXISTS student_fees(
        id SERIAL PRIMARY KEY,
        roll_no TEXT UNIQUE,
        tuition_fee REAL,
        transport_fee REAL,
        hostel_fee REAL,
        admission_fee REAL,
        dress_fee REAL,
        exam_fee REAL,
        book_fee REAL,
        notebook_fee REAL,
        misc_fee REAL,
        admission_paid INTEGER
    );

    CREATE TABLE IF NOT EXISTS bills(
        id SERIAL PRIMARY KEY,
        bill_no TEXT,
        roll_no TEXT,
        month TEXT,
        bill_date TEXT,
        tuition REAL,
        transport REAL,
        hostel REAL,
        admission REAL,
        dress REAL,
        exam REAL,
        book REAL,
        notebook REAL,
        misc REAL,
        prev_due REAL,
        total REAL,
        paid REAL,
        balance REAL,
        status TEXT
    );

    CREATE TABLE IF NOT EXISTS payments(
        id SERIAL PRIMARY KEY,
        receipt_no TEXT,
        roll_no TEXT,
        bill_id INTEGER,
        amount REAL,
        mode TEXT,
        pay_date TEXT,
        remark TEXT
    );

    CREATE TABLE IF NOT EXISTS expenses(
        id SERIAL PRIMARY KEY,
        category TEXT,
        description TEXT,
        amount REAL,
        exp_date TEXT,
        staff_id TEXT
    );

    CREATE TABLE IF NOT EXISTS marks(
        id SERIAL PRIMARY KEY,
        roll_no TEXT,
        subject TEXT,
        exam TEXT,
        marks TEXT,
        total TEXT
    );
    """)
    conn.commit()
    c.close()
    conn.close()

def run(query, params=None, fetch=False, fetchone=False):
    conn = get_db()
    c = conn.cursor()
    c.execute(query, params or ())
    result = None
    if fetch:
        result = c.fetchall()
    if fetchone:
        result = c.fetchone()
    conn.commit()
    c.close()
    conn.close()
    return result

# Helper functions jo app.py mein use hote hain
def all(query, params=None):
    return run(query, params, fetch=True)

def one(query, params=None):
    return run(query, params, fetchone=True)

def current_month():
    return datetime.now().strftime("%Y-%m")

def today():
    return datetime.now().strftime("%Y-%m-%d")

# Initialize DB on import
init_db()
