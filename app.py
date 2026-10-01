"""
=====================================================
   🏫 SCHOOL MANAGEMENT - WEB VERSION (Flask)
   Mobile-friendly • Responsive • Modern UI
   Run: python app.py  →  open http://localhost:5000
=====================================================
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify)
from functools import wraps
import sqlite3, csv, io, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "school-secret-key-change-this"
DB = "school.db"

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db().cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT,
        active INTEGER DEFAULT 1);

    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE, name TEXT, father TEXT, mother TEXT,
        class_name TEXT, section TEXT, gender TEXT, dob TEXT,
        contact TEXT, parent_contact TEXT, address TEXT,
        admission_date TEXT, transport_route TEXT, hostel TEXT);

    CREATE TABLE IF NOT EXISTS student_fees(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE,
        tuition_fee REAL DEFAULT 0, transport_fee REAL DEFAULT 0,
        hostel_fee REAL DEFAULT 0, admission_fee REAL DEFAULT 0,
        dress_fee REAL DEFAULT 0, exam_fee REAL DEFAULT 0,
        book_fee REAL DEFAULT 0, notebook_fee REAL DEFAULT 0,
        misc_fee REAL DEFAULT 0, admission_paid INTEGER DEFAULT 0);

    CREATE TABLE IF NOT EXISTS bills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_no TEXT UNIQUE, roll_no TEXT, month TEXT, bill_date TEXT,
        tuition REAL DEFAULT 0, transport REAL DEFAULT 0, hostel REAL DEFAULT 0,
        admission REAL DEFAULT 0, dress REAL DEFAULT 0, exam REAL DEFAULT 0,
        book REAL DEFAULT 0, notebook REAL DEFAULT 0, misc REAL DEFAULT 0,
        prev_due REAL DEFAULT 0, total REAL DEFAULT 0, paid REAL DEFAULT 0,
        balance REAL DEFAULT 0, status TEXT DEFAULT 'Unpaid');

    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_no TEXT, roll_no TEXT, bill_id INTEGER,
        amount REAL, mode TEXT, pay_date TEXT, remark TEXT);

    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, description TEXT, amount REAL,
        exp_date TEXT, staff_id TEXT);
    """)
    # Default users
    for u, p, r, n in [
        ("admin", "admin123", "Admin", "School Admin"),
        ("accountant", "acc123", "Accountant", "Head Accountant"),
        ("teacher", "teach123", "Teacher", "Class Teacher"),
    ]:
        try:
            c.execute("INSERT INTO users(username,password,role,full_name) VALUES(?,?,?,?)",
                      (u, p, r, n))
        except sqlite3.IntegrityError:
            pass
    db().commit()
    c.close()

# ---------------- AUTH ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if session.get("role") not in roles:
                flash("Access denied!", "error")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return wrapper
    return deco

# ---------------- ROUTES ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        conn = db()
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=? AND active=1",
            (u, p)).fetchone()
        conn.close()
        if row:
            session["user"] = row["username"]
            session["role"] = row["role"]
            session["name"] = row["full_name"]
            return redirect(url_for("dashboard"))
        flash("Invalid credentials!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    students = conn.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    total_due = conn.execute(
        "SELECT IFNULL(SUM(balance),0) t FROM bills WHERE balance > 0").fetchone()["t"]
    month = datetime.now().strftime("%Y-%m")
    collection = conn.execute(
        "SELECT IFNULL(SUM(amount),0) t FROM payments WHERE pay_date LIKE ?",
        (month + "%",)).fetchone()["t"]
    expense = conn.execute(
        "SELECT IFNULL(SUM(amount),0) t FROM expenses WHERE exp_date LIKE ?",
        (month + "%",)).fetchone()["t"]
    recent = conn.execute(
        "SELECT receipt_no, roll_no, amount, pay_date FROM payments "
        "ORDER BY id DESC LIMIT 8").fetchall()
    conn.close()
    return render_template("dashboard.html",
        students=students, total_due=total_due, collection=collection,
        expense=expense, profit=collection - expense, recent=recent)

@app.route("/students")
@login_required
def students():
    conn = db()
    q = request.args.get("q", "")
    if q:
        rows = conn.execute(
            "SELECT * FROM students WHERE name LIKE ? OR roll_no LIKE ? "
            "ORDER BY roll_no", (f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = conn.execute("SELECT * FROM students ORDER BY roll_no").fetchall()
    conn.close()
    return render_template("students.html", students=rows, q=q)

@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        conn = db()
        conn.execute("""INSERT INTO students
            (roll_no,name,father,mother,class_name,section,gender,dob,
             contact,parent_contact,address,admission_date,transport_route,hostel)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["roll_no"], d["name"], d["father"], d["mother"],
             d["class_name"], d["section"], d["gender"], d["dob"],
             d["contact"], d["parent_contact"], d["address"],
             d["admission_date"], d["transport_route"], d["hostel"]))
        conn.commit(); conn.close()
        flash("✅ Student added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("students"))

@app.route("/student/delete/<int:sid>")
@login_required
def delete_student(sid):
    conn = db()
    conn.execute("DELETE FROM students WHERE id=?", (sid,))
    conn.commit(); conn.close()
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students"))

@app.route("/bills")
@login_required
def bills():
    conn = db()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    rows = conn.execute(
        "SELECT * FROM bills WHERE month=? ORDER BY roll_no", (month,)).fetchall()
    conn.close()
    return render_template("bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form["month"]
    conn = db()
    students = conn.execute("SELECT roll_no, name FROM students").fetchall()
    created = skipped = 0
    for s in students:
        roll = s["roll_no"]
        ex = conn.execute("SELECT id FROM bills WHERE roll_no=? AND month=?",
                          (roll, month)).fetchone()
        if ex:
            skipped += 1; continue
        fs = conn.execute("SELECT * FROM student_fees WHERE roll_no=?",
                          (roll,)).fetchone()
        if not fs:
            skipped += 1; continue

        t  = fs["tuition_fee"] or 0
        tr = fs["transport_fee"] or 0
        ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        prev_added = conn.execute(
            "SELECT IFNULL(SUM(admission),0) a FROM bills WHERE roll_no=?",
            (roll,)).fetchone()["a"]
        adm = 0 if adm_paid or prev_added > 0 else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        prev_due = conn.execute(
            "SELECT IFNULL(SUM(balance),0) d FROM bills WHERE roll_no=? AND balance>0",
            (roll,)).fetchone()["d"]
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due
        bill_no = f"B{month.replace('-','')}{roll}"

        conn.execute("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bill_no, roll, month, datetime.now().strftime("%Y-%m-%d"),
             t, tr, ho, adm, dr, ex_f, bk, nb, ms, prev_due,
             total, 0, total, "Unpaid"))
        created += 1
    conn.commit(); conn.close()
    flash(f"✅ Bills created: {created}  |  Skipped: {skipped}", "success")
    return redirect(url_for("bills", month=month))

@app.route("/collect", methods=["GET", "POST"])
@login_required
def collect():
    if request.method == "POST":
        bill_id = request.form["bill_id"]
        amt = float(request.form["amount"])
        mode = request.form["mode"]
        remark = request.form.get("remark", "")
        conn = db()
        bill = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
        new_paid = bill["paid"] + amt
        new_bal = bill["total"] - new_paid
        status = "Paid" if new_bal <= 0 else "Partial"
        conn.execute("UPDATE bills SET paid=?,balance=?,status=? WHERE id=?",
                     (new_paid, new_bal, status, bill_id))
        rc = "R" + datetime.now().strftime("%Y%m%d%H%M%S")
        conn.execute("""INSERT INTO payments
            (receipt_no,roll_no,bill_id,amount,mode,pay_date,remark)
            VALUES(?,?,?,?,?,?,?)""",
            (rc, bill["roll_no"], bill_id, amt, mode,
             datetime.now().strftime("%Y-%m-%d"), remark))
        conn.commit(); conn.close()
        flash(f"✅ Payment ₹{amt:,.0f} recorded! Receipt: {rc}", "success")
        return redirect(url_for("collect"))
    roll = request.args.get("roll", "")
    rows = []
    if roll:
        conn = db()
        rows = conn.execute(
            "SELECT * FROM bills WHERE roll_no=? AND balance>0 ORDER BY month",
            (roll,)).fetchall()
        conn.close()
    return render_template("collect.html", bills=rows, roll=roll)

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    conn = db()
    if request.method == "POST":
        d = request.form
        conn.execute("""INSERT INTO expenses
            (category,description,amount,exp_date,staff_id)
            VALUES(?,?,?,?,?)""",
            (d["category"], d["description"], d["amount"],
             d["exp_date"], d.get("staff_id", "")))
        conn.commit()
        flash("✅ Expense added!", "success")
    rows = conn.execute("SELECT * FROM expenses ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("expenses.html", expenses=rows)

@app.route("/reports")
@login_required
def reports():
    conn = db()
    coll = conn.execute(
        "SELECT substr(pay_date,1,7) m, SUM(amount) a FROM payments "
        "GROUP BY m ORDER BY m DESC LIMIT 12").fetchall()
    exp = conn.execute(
        "SELECT substr(exp_date,1,7) m, SUM(amount) a FROM expenses "
        "GROUP BY m ORDER BY m DESC LIMIT 12").fetchall()
    total_c = conn.execute("SELECT IFNULL(SUM(amount),0) t FROM payments").fetchone()["t"]
    total_e = conn.execute("SELECT IFNULL(SUM(amount),0) t FROM expenses").fetchone()["t"]
    conn.close()
    return render_template("reports.html",
        coll=coll, exp=exp, total_c=total_c, total_e=total_e,
        profit=total_c - total_e)

@app.route("/export/<table>")
@login_required
def export_csv(table):
    allowed = ["students", "bills", "payments", "expenses"]
    if table not in allowed:
        return "Not allowed", 403
    conn = db()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    si = io.StringIO()
    if rows:
        w = csv.DictWriter(si, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    mem = io.BytesIO(si.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=f"{table}_{datetime.now():%Y%m%d}.csv")

# ---------------- RUN ----------------
if __name__ == "__main__":
    if not os.path.exists(DB):
        init_db()
    else:
        init_db()  # ensures tables
    app.run(host="0.0.0.0", port=5000, debug=True)"""
=====================================================
   🏫 SCHOOL MANAGEMENT - WEB VERSION (Flask)
   Mobile-friendly • Responsive • Modern UI
   Run: python app.py  →  open http://localhost:5000
=====================================================
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify)
from functools import wraps
import sqlite3, csv, io, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "school-secret-key-change-this"
DB = "school.db"

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db().cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT,
        active INTEGER DEFAULT 1);

    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE, name TEXT, father TEXT, mother TEXT,
        class_name TEXT, section TEXT, gender TEXT, dob TEXT,
        contact TEXT, parent_contact TEXT, address TEXT,
        admission_date TEXT, transport_route TEXT, hostel TEXT);

    CREATE TABLE IF NOT EXISTS student_fees(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE,
        tuition_fee REAL DEFAULT 0, transport_fee REAL DEFAULT 0,
        hostel_fee REAL DEFAULT 0, admission_fee REAL DEFAULT 0,
        dress_fee REAL DEFAULT 0, exam_fee REAL DEFAULT 0,
        book_fee REAL DEFAULT 0, notebook_fee REAL DEFAULT 0,
        misc_fee REAL DEFAULT 0, admission_paid INTEGER DEFAULT 0);

    CREATE TABLE IF NOT EXISTS bills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_no TEXT UNIQUE, roll_no TEXT, month TEXT, bill_date TEXT,
        tuition REAL DEFAULT 0, transport REAL DEFAULT 0, hostel REAL DEFAULT 0,
        admission REAL DEFAULT 0, dress REAL DEFAULT 0, exam REAL DEFAULT 0,
        book REAL DEFAULT 0, notebook REAL DEFAULT 0, misc REAL DEFAULT 0,
        prev_due REAL DEFAULT 0, total REAL DEFAULT 0, paid REAL DEFAULT 0,
        balance REAL DEFAULT 0, status TEXT DEFAULT 'Unpaid');

    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_no TEXT, roll_no TEXT, bill_id INTEGER,
        amount REAL, mode TEXT, pay_date TEXT, remark TEXT);

    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, description TEXT, amount REAL,
        exp_date TEXT, staff_id TEXT);

    CREATE TABLE IF NOT EXISTS results(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT, exam_name TEXT, subject TEXT,
        marks_obtained REAL DEFAULT 0, total_marks REAL DEFAULT 100,
        grade TEXT, created_at TEXT);
    """)
    # Default users
    for u, p, r, n in [
        ("admin", "admin123", "Admin", "School Admin"),
        ("accountant", "acc123", "Accountant", "Head Accountant"),
        ("teacher", "teach123", "Teacher", "Class Teacher"),
    ]:
        try:
            c.execute("INSERT INTO users(username,password,role,full_name) VALUES(?,?,?,?)",
                      (u, p, r, n))
        except sqlite3.IntegrityError:
            pass
    db().commit()
    c.close()

# ---------------- AUTH ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if session.get("role") not in roles:
                flash("Access denied!", "error")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return wrapper
    return deco

# ---------------- ROUTES ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        conn = db()
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=? AND active=1",
            (u, p)).fetchone()
        conn.close()
        if row:
            session["user"] = row["username"]
            session["role"] = row["role"]
            session["name"] = row["full_name"]
            return redirect(url_for("dashboard"))
        flash("Invalid credentials!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    students = conn.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    total_due = conn.execute(
        "SELECT IFNULL(SUM(balance),0) t FROM bills WHERE balance > 0").fetchone()["t"]
    month = datetime.now().strftime("%Y-%m")
    collection = conn.execute(
        "SELECT IFNULL(SUM(amount),0) t FROM payments WHERE pay_date LIKE ?",
        (month + "%",)).fetchone()["t"]
    expense = conn.execute(
        "SELECT IFNULL(SUM(amount),0) t FROM expenses WHERE exp_date LIKE ?",
        (month + "%",)).fetchone()["t"]
    recent = conn.execute(
        "SELECT receipt_no, roll_no, amount, pay_date FROM payments "
        "ORDER BY id DESC LIMIT 8").fetchall()
    conn.close()
    return render_template("dashboard.html",
        students=students, total_due=total_due, collection=collection,
        expense=expense, profit=collection - expense, recent=recent)

@app.route("/students")
@login_required
def students():
    conn = db()
    q = request.args.get("q", "")
    if q:
        rows = conn.execute(
            "SELECT * FROM students WHERE name LIKE ? OR roll_no LIKE ? "
            "ORDER BY roll_no", (f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = conn.execute("SELECT * FROM students ORDER BY roll_no").fetchall()
    conn.close()
    return render_template("students.html", students=rows, q=q)

@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        conn = db()
        conn.execute("""INSERT INTO students
            (roll_no,name,father,mother,class_name,section,gender,dob,
             contact,parent_contact,address,admission_date,transport_route,hostel)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["roll_no"], d["name"], d["father"], d["mother"],
             d["class_name"], d["section"], d["gender"], d["dob"],
             d["contact"], d["parent_contact"], d["address"],
             d["admission_date"], d["transport_route"], d["hostel"]))
        conn.commit(); conn.close()
        flash("✅ Student added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("students"))

@app.route("/student/delete/<int:sid>")
@login_required
def delete_student(sid):
    conn = db()
    conn.execute("DELETE FROM students WHERE id=?", (sid,))
    conn.commit(); conn.close()
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students"))

@app.route("/bills")
@login_required
def bills():
    conn = db()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    rows = conn.execute(
        "SELECT * FROM bills WHERE month=? ORDER BY roll_no", (month,)).fetchall()
    conn.close()
    return render_template("bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form["month"]
    conn = db()
    students = conn.execute("SELECT roll_no, name FROM students").fetchall()
    created = skipped = 0
    for s in students:
        roll = s["roll_no"]
        ex = conn.execute("SELECT id FROM bills WHERE roll_no=? AND month=?",
                          (roll, month)).fetchone()
        if ex:
            skipped += 1; continue
        fs = conn.execute("SELECT * FROM student_fees WHERE roll_no=?",
                          (roll,)).fetchone()
        if not fs:
            skipped += 1; continue

        t  = fs["tuition_fee"] or 0
        tr = fs["transport_fee"] or 0
        ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        prev_added = conn.execute(
            "SELECT IFNULL(SUM(admission),0) a FROM bills WHERE roll_no=?",
            (roll,)).fetchone()["a"]
        adm = 0 if adm_paid or prev_added > 0 else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        prev_due = conn.execute(
            "SELECT IFNULL(SUM(balance),0) d FROM bills WHERE roll_no=? AND balance>0",
            (roll,)).fetchone()["d"]
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due
        bill_no = f"B{month.replace('-','')}{roll}"

        conn.execute("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bill_no, roll, month, datetime.now().strftime("%Y-%m-%d"),
             t, tr, ho, adm, dr, ex_f, bk, nb, ms, prev_due,
             total, 0, total, "Unpaid"))
        created += 1
    conn.commit(); conn.close()
    flash(f"✅ Bills created: {created}  |  Skipped: {skipped}", "success")
    return redirect(url_for("bills", month=month))

@app.route("/collect", methods=["GET", "POST"])
@login_required
def collect():
    if request.method == "POST":
        bill_id = request.form["bill_id"]
        amt = float(request.form["amount"])
        mode = request.form["mode"]
        remark = request.form.get("remark", "")
        conn = db()
        bill = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
        new_paid = bill["paid"] + amt
        new_bal = bill["total"] - new_paid
        status = "Paid" if new_bal <= 0 else "Partial"
        conn.execute("UPDATE bills SET paid=?,balance=?,status=? WHERE id=?",
                     (new_paid, new_bal, status, bill_id))
        rc = "R" + datetime.now().strftime("%Y%m%d%H%M%S")
        conn.execute("""INSERT INTO payments
            (receipt_no,roll_no,bill_id,amount,mode,pay_date,remark)
            VALUES(?,?,?,?,?,?,?)""",
            (rc, bill["roll_no"], bill_id, amt, mode,
             datetime.now().strftime("%Y-%m-%d"), remark))
        conn.commit(); conn.close()
        flash(f"✅ Payment ₹{amt:,.0f} recorded! Receipt: {rc}", "success")
        return redirect(url_for("collect"))
    roll = request.args.get("roll", "")
    rows = []
    if roll:
        conn = db()
        rows = conn.execute(
            "SELECT * FROM bills WHERE roll_no=? AND balance>0 ORDER BY month",
            (roll,)).fetchall()
        conn.close()
    return render_template("collect.html", bills=rows, roll=roll)

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    conn = db()
    if request.method == "POST":
        d = request.form
        conn.execute("""INSERT INTO expenses
            (category,description,amount,exp_date,staff_id)
            VALUES(?,?,?,?,?)""",
            (d["category"], d["description"], d["amount"],
             d["exp_date"], d.get("staff_id", "")))
        conn.commit()
        flash("✅ Expense added!", "success")
    rows = conn.execute("SELECT * FROM expenses ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("expenses.html", expenses=rows)

# ---------------- RESULT SECTION ----------------
@app.route("/result", methods=["GET"])
@login_required
def result():
    roll = request.args.get("roll", "")
    exam = request.args.get("exam", "")
    conn = db()
    
    query = """
        SELECT r.*, s.name, s.class_name, s.section 
        FROM results r 
        LEFT JOIN students s ON r.roll_no = s.roll_no 
        WHERE 1=1
    """
    params = []
    if roll:
        query += " AND r.roll_no = ?"
        params.append(roll)
    if exam:
        query += " AND r.exam_name LIKE ?"
        params.append(f"%{exam}%")
    
    query += " ORDER BY r.id DESC"
    
    rows = conn.execute(query, params).fetchall()
    students_list = conn.execute("SELECT roll_no, name, class_name FROM students ORDER BY roll_no").fetchall()
    conn.close()
    
    return render_template("result.html", results=rows, students=students_list, roll=roll, exam=exam)

@app.route("/result/add", methods=["POST"])
@login_required
def add_result():
    d = request.form
    try:
        conn = db()
        marks = float(d["marks_obtained"])
        total = float(d["total_marks"])
        pct = (marks / total) * 100 if total > 0 else 0
        
        # Grade Calculation Logic
        if pct >= 90: grade = "A+"
        elif pct >= 80: grade = "A"
        elif pct >= 70: grade = "B"
        elif pct >= 60: grade = "C"
        elif pct >= 33: grade = "D"
        else: grade = "F"

        conn.execute("""INSERT INTO results
            (roll_no, exam_name, subject, marks_obtained, total_marks, grade, created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (d["roll_no"], d["exam_name"], d["subject"], marks, total, grade,
             datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        conn.close()
        flash("✅ Marks / Result added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("result"))

@app.route("/result/delete/<int:rid>")
@login_required
def delete_result(rid):
    conn = db()
    conn.execute("DELETE FROM results WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    flash("🗑️️ Result record deleted.", "success")
    return redirect(url_for("result"))

@app.route("/reports")
@login_required
def reports():
    conn = db()
    coll = conn.execute(
        "SELECT substr(pay_date,1,7) m, SUM(amount) a FROM payments "
        "GROUP BY m ORDER BY m DESC LIMIT 12").fetchall()
    exp = conn.execute(
        "SELECT substr(exp_date,1,7) m, SUM(amount) a FROM expenses "
        "GROUP BY m ORDER BY m DESC LIMIT 12").fetchall()
    total_c = conn.execute("SELECT IFNULL(SUM(amount),0) t FROM payments").fetchone()["t"]
    total_e = conn.execute("SELECT IFNULL(SUM(amount),0) t FROM expenses").fetchone()["t"]
    conn.close()
    return render_template("reports.html",
        coll=coll, exp=exp, total_c=total_c, total_e=total_e,
        profit=total_c - total_e)

@app.route("/export/<table>")
@login_required
def export_csv(table):
    allowed = ["students", "bills", "payments", "expenses", "results"]
    if table not in allowed:
        return "Not allowed", 403
    conn = db()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    si = io.StringIO()
    if rows:
        w = csv.DictWriter(si, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    mem = io.BytesIO(si.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=f"{table}_{datetime.now():%Y%m%d}.csv")

# ---------------- RUN ----------------
if __name__ == "__main__":
    if not os.path.exists(DB):
        init_db()
    else:
        init_db()  # ensures tables
    app.run(host="0.0.0.0", port=5000, debug=True)

