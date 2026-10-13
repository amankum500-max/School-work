"""
=====================================================
   🏫 SCHOOL MANAGEMENT - WEB VERSION (Flask)
   Mobile-friendly • Responsive • Modern UI
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
        row = one("SELECT * FROM users WHERE username=%s AND password=%s AND active=1", (u, p))
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
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
    month = current_month()
    collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s",
                     (month + "%",))["t"]
    expense = one("SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE exp_date LIKE %s",
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
        rows = db_all("SELECT * FROM students WHERE name LIKE %s OR roll_no LIKE %s ORDER BY roll_no",
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
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
    run("DELETE FROM students WHERE id=%s", (sid,))
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
    existing = one("SELECT id FROM student_fees WHERE roll_no=%s", (roll,))
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
            tuition_fee=%s, transport_fee=%s, hostel_fee=%s, admission_fee=%s,
            dress_fee=%s, exam_fee=%s, book_fee=%s, notebook_fee=%s, misc_fee=%s,
            admission_paid=%s WHERE roll_no=%s""", vals)
    else:
        run("""INSERT INTO student_fees
            (tuition_fee,transport_fee,hostel_fee,admission_fee,
             dress_fee,exam_fee,book_fee,notebook_fee,misc_fee,
             admission_paid,roll_no) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
    flash("✅ Fee structure saved!", "success")
    return redirect(url_for("fees"))

# ---------------- BILLS ----------------
@app.route("/bills")
@login_required
def bills():
    month = request.args.get("month", current_month())
    rows = db_all("SELECT * FROM bills WHERE month=%s ORDER BY roll_no", (month,))
    return render_template("bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form["month"]
    students = db_all("SELECT roll_no, name FROM students")
    created = skipped = 0
    for s in students:
        roll = s["roll_no"]
        ex = one("SELECT id FROM bills WHERE roll_no=%s AND month=%s", (roll, month))
        if ex:
            skipped += 1; continue
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs:
            skipped += 1; continue

        t  = fs["tuition_fee"] or 0
        tr = fs["transport_fee"] or 0
        ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        prev_added = one("SELECT COALESCE(SUM(admission),0) a FROM bills WHERE roll_no=%s",
                         (roll,))["a"]
        adm = 0 if (adm_paid or prev_added > 0) else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        prev_due = one("SELECT COALESCE(SUM(balance),0) d FROM bills WHERE roll_no=%s AND balance>0",
                       (roll,))["d"]
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due
        bill_no = f"B{month.replace('-','')}{roll}"

        run("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
        bill = one("SELECT * FROM bills WHERE id=%s", (bill_id,))
        new_paid = bill["paid"] + amt
        new_bal = bill["total"] - new_paid
        status = "Paid" if new_bal <= 0 else "Partial"
        run("UPDATE bills SET paid=%s,balance=%s,status=%s WHERE id=%s",
            (new_paid, new_bal, status, bill_id))
        rc = "R" + datetime.now().strftime("%Y%m%d%H%M%S")
        run("""INSERT INTO payments
            (receipt_no,roll_no,bill_id,amount,mode,pay_date,remark)
            VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (rc, bill["roll_no"], bill_id, amt, mode, today(), remark))
        flash(f"✅ Payment ₹{amt:,.0f} recorded! Receipt: {rc}", "success")
        return redirect(url_for("collect"))
    roll = request.args.get("roll", "")
    rows = []
    if roll:
        rows = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month", (roll,))
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
               VALUES(%s,%s,%s,%s,%s)""",
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
    total_c = one("SELECT COALESCE(SUM(amount),0) t FROM payments")["t"]
    total_e = one("SELECT COALESCE(SUM(amount),0) t FROM expenses")["t"]
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
        marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll,))
    return render_template("result.html", marks=marks, roll=roll)

@app.route("/marks/add", methods=["POST"])
@login_required
def add_marks():
    d = request.form
    existing = one("SELECT id FROM marks WHERE roll_no=%s AND subject=%s AND exam=%s",
                   (d["roll_no"], d["subject"], d["exam"]))
    if existing:
        run("UPDATE marks SET marks=%s, total=%s WHERE id=%s",
            (d["marks"], d["total"], existing["id"]))
        flash("✏️ Marks updated!", "success")
    else:
        run("INSERT INTO marks (roll_no,subject,exam,marks,total) VALUES(%s,%s,%s,%s,%s)",
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
        student = one("SELECT * FROM students WHERE roll_no=%s", (roll,))
        if student:
            rows = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll,))
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
                   SUM(CAST(m.marks AS FLOAT)) as total_obtained,
                   SUM(CAST(m.total AS FLOAT)) as total_max
            FROM students s
            JOIN marks m ON s.roll_no = m.roll_no
            WHERE s.class_name = %s
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
"""
=====================================================
   🏫 AI-POWERED SCHOOL MANAGEMENT SYSTEM
   Complete • Advanced • Fully Automated
=====================================================
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify)
from functools import wraps
import csv, io, os, base64
from datetime import datetime, timedelta
from database import init_db, run, all as db_all, one, current_month, today

# ---------- Optional AI & Utilities ----------
try:
    import google.generativeai as genai
    HAS_AI = True
except ImportError:
    HAS_AI = False

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-change-this-2026")

# ---------- AI Setup ----------
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
ai_model = None
if HAS_AI and GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel('gemini-pro')
    except Exception as e:
        print(f"AI Setup Error: {e}")

# ---------------- AUTH ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if session.get("role") != "admin":
            flash("Aapko iska permission nahi hai!", "error")
            return redirect(url_for("dashboard"))
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
        row = one("SELECT * FROM users WHERE username=%s AND password=%s AND active=1", (u, p))
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
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
    month = current_month()
    collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s",
                     (month + "%",))["t"]
    expense = one("SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE exp_date LIKE %s",
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
        rows = db_all("SELECT * FROM students WHERE name LIKE %s OR roll_no LIKE %s ORDER BY roll_no",
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
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
@admin_required
def delete_student(sid):
    run("DELETE FROM students WHERE id=%s", (sid,))
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students"))

# ---------------- ADVANCED FEE STRUCTURE ----------------
@app.route("/fees")
@login_required
def fees():
    rows = db_all("""SELECT s.roll_no, s.name, s.class_name, s.section,
                     f.tuition_fee, f.transport_fee, f.hostel_fee, f.admission_fee,
                     f.dress_fee, f.exam_fee, f.book_fee, f.notebook_fee,
                     f.misc_fee, f.back_dues
                     FROM students s LEFT JOIN student_fees f ON s.roll_no = f.roll_no
                     ORDER BY s.roll_no""")
    return render_template("fees.html", fees=rows)

@app.route("/fees/save", methods=["POST"])
@login_required
def save_fees():
    d = request.form
    roll = d["roll_no"]
    existing = one("SELECT id FROM student_fees WHERE roll_no=%s", (roll,))
    vals = (
        float(d.get("tuition_fee") or 0), float(d.get("transport_fee") or 0),
        float(d.get("hostel_fee") or 0), float(d.get("admission_fee") or 0),
        float(d.get("dress_fee") or 0), float(d.get("exam_fee") or 0),
        float(d.get("book_fee") or 0), float(d.get("notebook_fee") or 0),
        float(d.get("misc_fee") or 0), float(d.get("back_dues") or 0),
        int(d.get("admission_paid") or 0), roll
    )
    if existing:
        run("""UPDATE student_fees SET
            tuition_fee=%s, transport_fee=%s, hostel_fee=%s, admission_fee=%s,
            dress_fee=%s, exam_fee=%s, book_fee=%s, notebook_fee=%s, misc_fee=%s,
            back_dues=%s, admission_paid=%s WHERE roll_no=%s""", vals)
    else:
        run("""INSERT INTO student_fees
            (tuition_fee,transport_fee,hostel_fee,admission_fee,
             dress_fee,exam_fee,book_fee,notebook_fee,misc_fee,back_dues,
             admission_paid,roll_no) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
    flash("✅ Fee structure saved!", "success")
    return redirect(url_for("fees"))

@app.route("/fees/edit/<roll_no>", methods=["GET", "POST"])
@login_required
def edit_fees(roll_no):
    if request.method == "POST":
        d = request.form
        run("""UPDATE student_fees SET
            tuition_fee=%s, transport_fee=%s, hostel_fee=%s, admission_fee=%s,
            dress_fee=%s, exam_fee=%s, book_fee=%s, notebook_fee=%s, misc_fee=%s,
            back_dues=%s WHERE roll_no=%s""",
            (d.get("tuition_fee") or 0, d.get("transport_fee") or 0, d.get("hostel_fee") or 0,
             d.get("admission_fee") or 0, d.get("dress_fee") or 0, d.get("exam_fee") or 0,
             d.get("book_fee") or 0, d.get("notebook_fee") or 0, d.get("misc_fee") or 0,
             d.get("back_dues") or 0, roll_no))
        flash("✅ Fee structure updated!", "success")
        return redirect(url_for("fees"))

    fee_data = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll_no,))
    return render_template("edit_fees.html", fee=fee_data)

@app.route("/fees/delete/<roll_no>")
@login_required
@admin_required
def delete_fees(roll_no):
    run("DELETE FROM student_fees WHERE roll_no=%s", (roll_no,))
    flash(f"🗑️ Roll No {roll_no} ka fee structure delete ho gaya!", "success")
    return redirect(url_for("fees"))

@app.route("/run-arrears-update")
@login_required
@admin_required
def run_arrears_update():
    today_dt = datetime.today()
    first_day_of_month = today_dt.replace(day=1)
    last_day_of_prev_month = first_day_of_month - timedelta(days=1)
    prev_month_name = last_day_of_prev_month.strftime("%B")
    prev_year = last_day_of_prev_month.year

    students = db_all("SELECT roll_no FROM students")
    for student in students:
        roll = student['roll_no']
        fee = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fee: continue

        expected_monthly = (fee['tuition_fee'] or 0) + (fee['transport_fee'] or 0) + (fee['hostel_fee'] or 0) + (fee['misc_fee'] or 0)
        paid_row = one("SELECT SUM(amount) as total_paid FROM payments WHERE roll_no=%s AND pay_date LIKE %s",
                       (roll, f"{prev_year}-{last_day_of_prev_month.month:02d}%"))
        amount_paid_last_month = paid_row['total_paid'] if paid_row and paid_row['total_paid'] else 0

        old_back_dues = fee['back_dues'] or 0
        last_month_pending = max(0, expected_monthly - amount_paid_last_month)
        new_total_back_dues = old_back_dues + last_month_pending

        run("UPDATE student_fees SET back_dues=%s WHERE roll_no=%s", (new_total_back_dues, roll))

    flash(f"✅ {prev_month_name} {prev_year} ka Back Dues update ho gaya!", "success")
    return redirect(url_for("fees"))

@app.route("/receipt/<roll_no>")
@login_required
def receipt(roll_no):
    fee_data = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll_no,))
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    return render_template("receipt.html", fee=fee_data, student=student)

# ---------------- BILLS ----------------
@app.route("/bills")
@login_required
def bills():
    month = request.args.get("month", current_month())
    rows = db_all("SELECT * FROM bills WHERE month=%s ORDER BY roll_no", (month,))
    return render_template("bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form["month"]
    students = db_all("SELECT roll_no, name FROM students")
    created = skipped = 0
    for s in students:
        roll = s["roll_no"]
        ex = one("SELECT id FROM bills WHERE roll_no=%s AND month=%s", (roll, month))
        if ex:
            skipped += 1; continue
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs:
            skipped += 1; continue

        t  = fs["tuition_fee"] or 0
        tr = fs["transport_fee"] or 0
        ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        prev_added = one("SELECT COALESCE(SUM(admission),0) a FROM bills WHERE roll_no=%s",
                         (roll,))["a"]
        adm = 0 if (adm_paid or prev_added > 0) else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        manual_back_dues = fs["back_dues"] or 0
        prev_due = one("SELECT COALESCE(SUM(balance),0) d FROM bills WHERE roll_no=%s AND balance>0",
                       (roll,))["d"]
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due + manual_back_dues
        bill_no = f"B{month.replace('-','')}{roll}"

        run("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (bill_no, roll, month, today(),
             t, tr, ho, adm, dr, ex_f, bk, nb, ms, prev_due + manual_back_dues,
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
        bill = one("SELECT * FROM bills WHERE id=%s", (bill_id,))
        new_paid = bill["paid"] + amt
        new_bal = bill["total"] - new_paid
        status = "Paid" if new_bal <= 0 else "Partial"
        run("UPDATE bills SET paid=%s,balance=%s,status=%s WHERE id=%s",
            (new_paid, new_bal, status, bill_id))

        # Smart Back Dues logic: pehle back dues clear honge
        fee_data = one("SELECT back_dues FROM student_fees WHERE roll_no=%s", (bill["roll_no"],))
        if fee_data and fee_data['back_dues'] and fee_data['back_dues'] > 0:
            new_back_dues = max(0, fee_data['back_dues'] - amt)
            run("UPDATE student_fees SET back_dues=%s WHERE roll_no=%s",
                (new_back_dues, bill["roll_no"]))

        rc = "R" + datetime.now().strftime("%Y%m%d%H%M%S")
        run("""INSERT INTO payments
            (receipt_no,roll_no,bill_id,amount,mode,pay_date,remark)
            VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (rc, bill["roll_no"], bill_id, amt, mode, today(), remark))
        flash(f"✅ Payment ₹{amt:,.0f} recorded! Receipt: {rc}", "success")
        return redirect(url_for("collect"))
    roll = request.args.get("roll", "")
    rows = []
    if roll:
        rows = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month", (roll,))
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
               VALUES(%s,%s,%s,%s,%s)""",
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
    total_c = one("SELECT COALESCE(SUM(amount),0) t FROM payments")["t"]
    total_e = one("SELECT COALESCE(SUM(amount),0) t FROM expenses")["t"]
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
        marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll,))
    return render_template("result.html", marks=marks, roll=roll)

@app.route("/marks/add", methods=["POST"])
@login_required
def add_marks():
    d = request.form
    existing = one("SELECT id FROM marks WHERE roll_no=%s AND subject=%s AND exam=%s",
                   (d["roll_no"], d["subject"], d["exam"]))
    if existing:
        run("UPDATE marks SET marks=%s, total=%s WHERE id=%s",
            (d["marks"], d["total"], existing["id"]))
        flash("✏️ Marks updated!", "success")
    else:
        run("INSERT INTO marks (roll_no,subject,exam,marks,total) VALUES(%s,%s,%s,%s,%s)",
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
        student = one("SELECT * FROM students WHERE roll_no=%s", (roll,))
        if student:
            rows = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll,))
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
                   SUM(CAST(m.marks AS FLOAT)) as total_obtained,
                   SUM(CAST(m.total AS FLOAT)) as total_max
            FROM students s
            JOIN marks m ON s.roll_no = m.roll_no
            WHERE s.class_name = %s
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

# ==================== 🤖 AI FEATURES ====================

# ---------- AI CHAT ASSISTANT ----------
@app.route("/ai-assistant", methods=["GET", "POST"])
@login_required
def ai_assistant():
    if request.method == "POST":
        data = request.get_json() or {}
        user_query = data.get("query", "").strip()
        if not user_query:
            return jsonify({"reply": "Kuch pooch toh sahi bhai!"})

        if not ai_model:
            return jsonify({"reply": "AI abhi available nahi hai. Render me GEMINI_API_KEY set kar."})

        total_students = one("SELECT COUNT(*) c FROM students")["c"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        defaulters = db_all("""SELECT s.name, s.roll_no, b.balance FROM bills b
                             JOIN students s ON b.roll_no=s.roll_no
                             WHERE b.balance>0 ORDER BY b.balance DESC LIMIT 5""")
        students_sample = db_all("SELECT roll_no, name, class_name, vi FROM students LIMIT 20")

        context = f"""
        Aap ek School Management System ke AI assistant hain. Hinglish me short aur helpful jawab dijiye (max 100 words).

        Current School Data:
        - Total Students: {total_students}
        - Total Pending Fees: Rs {total_due}
        - Top Defaulters: {[dict(d) for d in defaulters]}
        - Students Sample: {[dict(s) for s in students_sample]}

        User ka Sawaal: {user_query}
        """

        try:
            response = ai_model.generate_content(context)
            return jsonify({"reply": response.text})
        except Exception as e:
            return jsonify({"reply": f"AI Error: {str(e)}"})
    return render_template("ai_assistant.html")
