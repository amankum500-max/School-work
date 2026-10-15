"""
=====================================================
   DATABASE LAYER - Supabase PostgreSQL
   Complete School ERP + AI Database
=====================================================
"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime

# Supabase Connection String
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    -- USERS & AUTH
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        full_name TEXT,
        active INTEGER DEFAULT 1
    );

    -- PARENT PORTAL USERS
    CREATE TABLE IF NOT EXISTS parent_users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        parent_name TEXT,
        child_roll_no TEXT,
        contact TEXT,
        active INTEGER DEFAULT 1
    );

    -- STUDENTS
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

    -- STAFF
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

    -- STUDENT FEES STRUCTURE
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
        admission_paid INTEGER,
        back_dues REAL DEFAULT 0
    );

    -- BILLS
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

    -- PAYMENTS
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

    -- EXPENSES
    CREATE TABLE IF NOT EXISTS expenses(
        id SERIAL PRIMARY KEY,
        category TEXT,
        description TEXT,
        amount REAL,
        exp_date TEXT,
        staff_id TEXT
    );

    -- MARKS / RESULTS
    CREATE TABLE IF NOT EXISTS marks(
        id SERIAL PRIMARY KEY,
        roll_no TEXT,
        subject TEXT,
        exam TEXT,
        marks TEXT,
        total TEXT
    );

    -- ATTENDANCE
    CREATE TABLE IF NOT EXISTS attendance(
        id SERIAL PRIMARY KEY,
        roll_no TEXT,
        att_date TEXT NOT NULL,
        status TEXT NOT NULL
    );

    -- STUDENT HEALTH RECORDS
    CREATE TABLE IF NOT EXISTS student_health(
        id SERIAL PRIMARY KEY,
        roll_no TEXT UNIQUE,
        blood_group TEXT,
        allergies TEXT,
        emergency_contact TEXT
    );

    -- DIGITAL LIBRARY
    CREATE TABLE IF NOT EXISTS library_books(
        id SERIAL PRIMARY KEY,
        book_id TEXT UNIQUE,
        title TEXT NOT NULL,
        author TEXT,
        category TEXT,
        total_copies INTEGER DEFAULT 1,
        available_copies INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS book_issues(
        id SERIAL PRIMARY KEY,
        book_id TEXT,
        roll_no TEXT,
        issue_date TEXT,
        due_date TEXT,
        return_date TEXT,
        fine REAL DEFAULT 0,
        status TEXT DEFAULT 'Issued'
    );

    -- HOSTEL MANAGEMENT
    CREATE TABLE IF NOT EXISTS hostel_rooms(
        id SERIAL PRIMARY KEY,
        room_no TEXT UNIQUE,
        floor TEXT,
        capacity INTEGER DEFAULT 4,
        occupied INTEGER DEFAULT 0,
        monthly_fee REAL DEFAULT 0,
        warden_name TEXT,
        warden_contact TEXT
    );

    CREATE TABLE IF NOT EXISTS hostel_allocations(
        id SERIAL PRIMARY KEY,
        roll_no TEXT,
        room_no TEXT,
        allocated_date TEXT,
        status TEXT DEFAULT 'Active'
    );

    -- TRANSPORT MANAGEMENT
    CREATE TABLE IF NOT EXISTS transport_routes(
        id SERIAL PRIMARY KEY,
        route_name TEXT,
        route_number TEXT UNIQUE,
        driver_name TEXT,
        driver_contact TEXT,
        vehicle_no TEXT,
        capacity INTEGER DEFAULT 30,
        occupied INTEGER DEFAULT 0,
        monthly_fee REAL DEFAULT 0,
        stops TEXT
    );

    CREATE TABLE IF NOT EXISTS transport_allocations(
        id SERIAL PRIMARY KEY,
        roll_no TEXT,
        route_number TEXT,
        stop_name TEXT,
        allocated_date TEXT,
        status TEXT DEFAULT 'Active'
    );

    -- CLASSES & SUBJECTS
    CREATE TABLE IF NOT EXISTS classes(
        id SERIAL PRIMARY KEY,
        class_name TEXT UNIQUE,
        sections TEXT,
        class_teacher TEXT,
        room_no TEXT
    );

    CREATE TABLE IF NOT EXISTS subjects(
        id SERIAL PRIMARY KEY,
        subject_name TEXT,
        subject_code TEXT,
        class_name TEXT,
        teacher_name TEXT,
        max_marks INTEGER DEFAULT 100
    );

    -- AUDIT LOGS
    CREATE TABLE IF NOT EXISTS audit_logs(
        id SERIAL PRIMARY KEY,
        user_name TEXT,
        action TEXT,
        details TEXT,
        log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- NOTICE BOARD
    CREATE TABLE IF NOT EXISTS notices(
        id SERIAL PRIMARY KEY,
        title TEXT,
        content TEXT,
        category TEXT,
        posted_by TEXT,
        posted_date TEXT,
        priority TEXT DEFAULT 'Normal',
        active INTEGER DEFAULT 1
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

# Helper functions
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
