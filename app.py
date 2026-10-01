"""
=====================================================
   🏫 SCHOOL MANAGEMENT - WEB VERSION (Flask)
   Mobile-friendly • Responsive • Modern UI
   Includes: Students, Fees, Bills, Collect, Expenses,
             Reports, Defaulters, Result, Report Card, Merit List
=====================================================
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file)
from functools import wraps
import csv, io, os
from datetime import datetime
from database import init_db, run, all as db_all, one, current_month, today

app = Flask(__name__)
app.secret_key = "school-secret-key-change-this-2026"

# ---------------- AUTH ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

# ---------------- GRADE HELPER ----------------
def calc_grade(pct):
    if pct >= 90: return "A+"
    if pct >= 80: return "A"
    if pct >= 70: return "B"
    if pct >= 60: return "C"
    if pct >= 50: return "D"
    return "F"

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        row = one("SELECT * FROM users WHERE username=? AND password=? AND active=1", (u, p))
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

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    students = one("SELECT COUNT(*) c FROM students")["c"]
    total_due = one("SELECT IFNULL(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
    month = current_month()
    collection = one("SELECT IFNULL(SUM(amount),0) t FROM payments WHERE pay_date LIKE ?",
                     (month + "%",))["t"]
    expense = one("SELECT IFNULL(SUM(amount),0) t FROM expenses WHERE exp_date LIKE ?",
                  (month + "%",))["t"]
    recent = db_all("SELECT receipt_no, roll_no, amount, pay_date FROM payments "
                    "ORDER BY id DESC LIMIT 8")
    return render_template("dashboard.html",
        students=students, total_due=total_due, collection=collection,
        expense=expense, profit=collection - expense, recent=recent)

# ---------------- STUDENTS ----------------
@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "")
    if q:
        rows = db_all("SELECT * FROM students WHERE name LIKE ? OR roll_no LIKE ? ORDER BY roll_no",
                      (f"%{q}%", f"%{q}%"))
    else:
        rows = db_all("SELECT * FROM students ORDER BY roll_no")
    return render_template("students.html", students=rows, q=q)

@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        run("""INSERT INTO students
            (roll_no,name,father,mother,class_name,section,gender,dob,
             contact,parent_contact,address,admission_date,transport_route,hostel)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["roll_no"], d["name"], d["father"], d["mother"],
             d["class_name"], d["section"], d["gender"], d["dob"],
             d["contact"], d["parent_contact"], d["address"],
             d["admission_date"], d["transport_route"], d["hostel"]))
        flash("✅ Student added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("students"))

@app.route("/student/delete/<int:sid>")
@login_required
def delete_student(sid):
    run("DELETE FROM students WHERE id=?", (sid,))
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students"))

# ---------------- FEE STRUCTURE ----------------
@app.route("/fees")
@login_required
def fees():
    rows = db_all("""SELECT s.roll_no, s.name, s.class_name, s.section,
                     f.tuition_fee, f.transport_fee, f.hostel_fee, f.misc_fee
                     FROM students s LEFT JOIN student_fees f ON s.roll_no = f.roll_no
                     ORDER BY s.roll_no""")
    return render_template("fees.html", fees=rows)

@app.route("/fees/save", methods=["POST"])
@login_required
def save_fees():
    d = request.form
    roll = d["roll_no"]
    existing = one("SELECT id FROM student_fees WHERE roll_no=?", (roll,))
    vals = (
        float(d.get("tuition_fee") or 0), float(d.get("transport_fee") or 0),
        float(d.get("hostel_fee") or 0), float(d.get("admission_fee") or 0),
        float(d.get("dress_fee") or 0), float(d.get("exam_fee") or 0),
        float(d.get("book_fee") or 0), float(d.get("notebook_fee") or 0),
        float(d.get("misc_fee") or 0), int(d.get("admission_paid") or 0),
        roll
    )
    if existing:
        run("""UPDATE student_fees SET
            tuition_fee=?, transport_fee=?, hostel_fee=?, admission_fee=?,
            dress_fee=?, exam_fee=?, book_fee=?, notebook_fee=?, misc_fee=?,
            admission_paid=? WHERE roll_no=?""", vals)
    else:
        run("""INSERT INTO student_fees
            (tuition_fee,transport_fee,hostel_fee,admission_fee,
             dress_fee,exam_fee,book_fee,notebook_fee,misc_fee,
             admission_paid,roll_no) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", vals)
    flash("✅ Fee structure saved!", "success")
    return redirect(url_for("fees"))

# ---------------- BILLS ----------------
@app.route("/bills")
@login_required
def bills():
    month = request.args.get("month", current_month())
    rows = db_all("SELECT * FROM bills WHERE month=? ORDER BY roll_no", (month,))
    return render_template("bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form["month"]
    students = db_all("SELECT roll_no, name FROM students")
    created = skipped = 0
    for s in students:
        roll = s["roll_no"]
        ex = one("SELECT id FROM bills WHERE roll_no=? AND month=?", (roll, month))
        if ex:
            skipped += 1; continue
        fs = one("SELECT * FROM student_fees WHERE roll_no=?", (roll,))
        if not fs:
            skipped += 1; continue

        t  = fs["tuition_fee"] or 0
        tr = fs["transport_fee"] or 0
        ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        prev_added = one("SELECT IFNULL(SUM(admission),0) a FROM bills WHERE roll_no=?",
                         (roll,))["a"]
        adm = 0 if (adm_paid or prev_added > 0) else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        prev_due = one("SELECT IFNULL(SUM(balance),0) d FROM bills WHERE roll_no=? AND balance>0",
                       (roll,))["d"]
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due
        bill_no = f"B{month.replace('-','')}{roll}"

        run("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bill_no, roll, month, today(),
             t, tr, ho, adm, dr, ex_f, bk, nb, ms, prev_due,
             total, 0, total, "Unpaid"))
        created += 1
    flash(f"✅ Bills created: {created}  |  Skipped: {skipped}", "success")
    return redirect(url_for("bills", month=month))

# ---------------- FEE COLLECTION ----------------
@app.route("/collect", methods=["GET", "POST"])
@login_required
def collect():
    if request.method == "POST":
        bill_id = request.form["bill_id"]
        amt = float(request.form["amount"])
        mode = request.form["mode"]
        remark = request.form.get("remark", "")
        bill = one("SELECT * FROM bills WHERE id=?", (bill_id,))
        new_paid = bill["paid"] + amt
        new_bal = bill["total"] - new_paid
        status = "Paid" if new_bal <= 0 else "Partial"
        run("UPDATE bills SET paid=?,balance=?,status=? WHERE id=?",
            (new_paid, new_bal, status, bill_id))
        rc = "R" + datetime.now().strftime("%Y%m%d%H%M%S")
        run("""INSERT INTO payments
            (receipt_no,roll_no,bill_id,amount,mode,pay_date,remark)
            VALUES(?,?,?,?,?,?,?)""",
            (rc, bill["roll_no"], bill_id, amt, mode, today(), remark))
        flash(f"✅ Payment ₹{amt:,.0f} recorded! Receipt: {rc}", "success")
        return redirect(url_for("collect"))
    roll = request.args.get("roll", "")
    rows = []
    if roll:
        rows = db_all("SELECT * FROM bills WHERE roll_no=? AND balance>0 ORDER BY month", (roll,))
    return render_template("collect.html", bills=rows, roll=roll)

# ---------------- DEFAULTERS ----------------
@app.route("/defaulters")
@login_required
def defaulters():
    rows = db_all("""SELECT s.roll_no, s.name, s.class_name, s.section,
                     s.parent_contact, b.month, b.balance
                     FROM bills b JOIN students s ON b.roll_no = s.roll_no
                     WHERE b.balance > 0 ORDER BY b.balance DESC""")
    total = sum(r["balance"] for r in rows)
    return render_template("defaulters.html", defaulters=rows, total=total)

# ---------------- EXPENSES ----------------
@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        d = request.form
        run("""INSERT INTO expenses (category,description,amount,exp_date,staff_id)
               VALUES(?,?,?,?,?)""",
            (d["category"], d["description"], d["amount"],
             d["exp_date"], d.get("staff_id", "")))
        flash("✅ Expense added!", "success")
    rows = db_all("SELECT * FROM expenses ORDER BY id DESC")
    return render_template("expenses.html", expenses=rows)

# ---------------- REPORTS ----------------
@app.route("/reports")
@login_required
def reports():
    coll = db_all("""SELECT substr(pay_date,1,7) m, SUM(amount) a FROM payments
                     GROUP BY m ORDER BY m DESC LIMIT 12""")
    exp = db_all("""SELECT substr(exp_date,1,7) m, SUM(amount) a FROM expenses
                    GROUP BY m ORDER BY m DESC LIMIT 12""")
    total_c = one("SELECT IFNULL(SUM(amount),0) t FROM payments")["t"]
    total_e = one("SELECT IFNULL(SUM(amount),0) t FROM expenses")["t"]
    return render_template("reports.html",
        coll=coll, exp=exp, total_c=total_c, total_e=total_e,
        profit=total_c - total_e)

# ---------------- RESULT / MARKS ----------------
@app.route("/result")
@login_required
def result():
    roll = request.args.get("roll", "")
    marks = []
    if roll:
        marks = db_all("SELECT * FROM marks WHERE roll_no=? ORDER BY subject", (roll,))
    return render_template("result.html", marks=marks, roll=roll)

@app.route("/marks/add", methods=["POST"])
@login_required
def add_marks():
    d = request.form
    existing = one("SELECT id FROM marks WHERE roll_no=? AND subject=? AND exam=?",
                   (d["roll_no"], d["subject"], d["exam"]))
    if existing:
        run("UPDATE marks SET marks=?, total=? WHERE id=?",
            (d["marks"], d["total"], existing["id"]))
        flash("✏️ Marks updated!", "success")
    else:
        run("INSERT INTO marks (roll_no,subject,exam,marks,total) VALUES(?,?,?,?,?)",
            (d["roll_no"], d["subject"], d["exam"], d["marks"], d["total"]))
        flash("✅ Marks added!", "success")
    return redirect(url_for("result", roll=d["roll_no"]))

@app.route("/report-card")
@login_required
def report_card():
    roll = request.args.get("roll", "")
    student = None
    marks = []
    total_obtained = total_max = overall_pct = 0
    overall_grade = "-"
    if roll:
        student = one("SELECT * FROM students WHERE roll_no=?", (roll,))
        if student:
            rows = db_all("SELECT * FROM marks WHERE roll_no=? ORDER BY subject", (roll,))
            for r in rows:
                m = float(r["marks"] or 0)
                t = float(r["total"] or 0)
                pct = (m / t * 100) if t > 0 else 0
                marks.append({
                    "subject": r["subject"], "exam": r["exam"],
                    "marks": r["marks"], "total": r["total"],
                    "pct": pct, "grade": calc_grade(pct)
                })
                total_obtained += m
                total_max += t
            if total_max > 0:
                overall_pct = total_obtained / total_max * 100
                overall_grade = calc_grade(overall_pct)
    return render_template("report_card.html",
        student=student, marks=marks,
        total_obtained=total_obtained, total_max=total_max,
        overall_pct=overall_pct, overall_grade=overall_grade, roll=roll)

@app.route("/merit-list")
@login_required
def merit_list():
    class_name = request.args.get("class_name", "")
    merit = []
    if class_name:
        rows = db_all("""
            SELECT s.roll_no, s.name,
                   SUM(CAST(m.marks AS REAL)) as total_obtained,
                   SUM(CAST(m.total AS REAL)) as total_max
            FROM students s
            JOIN marks m ON s.roll_no = m.roll_no
            WHERE s.class_name = ?
            GROUP BY s.roll_no, s.name
            ORDER BY (total_obtained / total_max) DESC
        """, (class_name,))
        for r in rows:
            to = float(r["total_obtained"] or 0)
            tm = float(r["total_max"] or 0)
            pct = (to / tm * 100) if tm > 0 else 0
            merit.append({
                "roll_no": r["roll_no"], "name": r["name"],
                "total_obtained": to, "total_max": tm,
                "pct": pct, "grade": calc_grade(pct)
            })
    return render_template("merit_list.html", merit=merit, class_name=class_name)

# ---------------- CSV EXPORT ----------------
@app.route("/export/<table>")
@login_required
def export_csv(table):
    allowed = ["students", "bills", "payments", "expenses", "marks"]
    if table not in allowed:
        return "Not allowed", 403
    rows = db_all(f"SELECT * FROM {table}")
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
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
