"""Database Layer - Supabase PostgreSQL version"""
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
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        full_name TEXT,
        active INTEGER DEFAULT 1
    );
--  Staff Table
CREATE TABLE IF NOT EXISTS staff (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) UNIQUE,
    name VARCHAR(100) NOT NULL,
    designation VARCHAR(50),
    subject VARCHAR(50),
    contact VARCHAR(20),
    email VARCHAR(100),
    joining_date DATE,
    salary NUMERIC(10,2),
    address TEXT
);

--  Library Books Table
CREATE TABLE IF NOT EXISTS library_books (
    id SERIAL PRIMARY KEY,
    book_id VARCHAR(50) UNIQUE,
    title VARCHAR(200) NOT NULL,
    author VARCHAR(100),
    category VARCHAR(50),
    total_copies INT DEFAULT 1,
    available_copies INT DEFAULT 1
);

--  Book Issues Table
CREATE TABLE IF NOT EXISTS book_issues (
    id SERIAL PRIMARY KEY,
    book_id VARCHAR(50),
    roll_no VARCHAR(50),
    issue_date DATE,
    due_date DATE,
    return_date DATE,
    fine NUMERIC(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'Issued'
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
--  Health Records Table
CREATE TABLE IF NOT EXISTS student_health (
    id SERIAL PRIMARY KEY,
    roll_no VARCHAR(50) REFERENCES students(roll_no) ON DELETE CASCADE,
    blood_group VARCHAR(10),
    allergies TEXT,
    emergency_contact VARCHAR(20)
);

--  Attendance Table
CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    roll_no VARCHAR(50) REFERENCES students(roll_no) ON DELETE CASCADE,
    att_date DATE NOT NULL,
    status VARCHAR(10) NOT NULL -- 'Present', 'Absent', 'Late'
);
--  Hostel Rooms
CREATE TABLE IF NOT EXISTS hostel_rooms (
    id SERIAL PRIMARY KEY,
    room_no VARCHAR(20) UNIQUE,
    floor VARCHAR(20),
    capacity INT DEFAULT 4,
    occupied INT DEFAULT 0,
    monthly_fee NUMERIC(10,2) DEFAULT 0,
    warden_name VARCHAR(100),
    warden_contact VARCHAR(20)
);

--  Hostel Allocations
CREATE TABLE IF NOT EXISTS hostel_allocations (
    id SERIAL PRIMARY KEY,
    roll_no VARCHAR(50),
    room_no VARCHAR(20),
    allocated_date DATE,
    status VARCHAR(20) DEFAULT 'Active'
);

--  Transport Routes
CREATE TABLE IF NOT EXISTS transport_routes (
    id SERIAL PRIMARY KEY,
    route_name VARCHAR(100),
    route_number VARCHAR(20),
    driver_name VARCHAR(100),
    driver_contact VARCHAR(20),
    vehicle_no VARCHAR(50),
    capacity INT DEFAULT 30,
    occupied INT DEFAULT 0,
    monthly_fee NUMERIC(10,2) DEFAULT 0,
    stops TEXT
);

--  Transport Allocations
CREATE TABLE IF NOT EXISTS transport_allocations (
    id SERIAL PRIMARY KEY,
    roll_no VARCHAR(50),
    route_number VARCHAR(20),
    stop_name VARCHAR(100),
    allocated_date DATE,
    status VARCHAR(20) DEFAULT 'Active'
);

--  Parent Portal Users
CREATE TABLE IF NOT EXISTS parent_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL,
    parent_name VARCHAR(100),
    child_roll_no VARCHAR(50),
    contact VARCHAR(20),
    active INT DEFAULT 1
);
--  Classes & Sections
CREATE TABLE IF NOT EXISTS classes (
    id SERIAL PRIMARY KEY,
    class_name VARCHAR(50) UNIQUE,
    sections VARCHAR(100),
    class_teacher VARCHAR(100),
    room_no VARCHAR(20)
);

--  Subjects
CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    subject_name VARCHAR(100) UNIQUE,
    subject_code VARCHAR(20),
    class_name VARCHAR(50),
    teacher_name VARCHAR(100),
    max_marks INT DEFAULT 100
);

--  Audit Log
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_name VARCHAR(100),
    action VARCHAR(200),
    details TEXT,
    log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

--  Notice Board
CREATE TABLE IF NOT EXISTS notices (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200),
    content TEXT,
    category VARCHAR(50),
    posted_by VARCHAR(100),
    posted_date DATE,
    priority VARCHAR(20) DEFAULT 'Normal',
    active INT DEFAULT 1
);
init_db()
