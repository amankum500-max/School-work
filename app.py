"""
=====================================================
   🏫 SCHOOL MANAGEMENT - WEB VERSION (Flask)
   Complete Working Version
=====================================================
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify)
from functools import wraps
from urllib.parse import quote
import csv, io, os
from datetime import datetime, timedelta
from database import init_db, run, all as db_all, one, current_month, today

app = Flask(__name__)
app.secret_key = "school-secret-key-change-this-2026"


# ==================== COMPAT LAYER ====================
# Templates (fees.html, receipt.html) me `f.field` access ke liye
# aur routes me `db.xxx` jaisa interface provide karne ke liye.

def get_fee(roll_no):
    return one("SELECT * FROM student_fees WHERE roll_no=%s", (roll_no,))

def get_student(roll_no):
    return one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))

def save_fee(roll_no, **fields):
    cols = ['tuition_fee','transport_fee','hostel_fee','admission_fee',
            'dress_fee','exam_fee','book_fee','notebook_fee','misc_fee','admission_paid']
    vals = [fields.get(c, 0) for c in cols]
    existing = get_fee(roll_no)
    if existing:
        set_clause = ", ".join([f"{c}=%s" for c in cols])
        run(f"UPDATE student_fees SET {set_clause} WHERE roll_no=%s", tuple(vals + [roll_no]))
    else:
        cols_str = ", ".join(cols + ['roll_no'])
        ph = ", ".join(["%s"] * (len(cols) + 1))
        run(f"INSERT INTO student_fees ({cols_str}) VALUES ({ph})", tuple(vals + [roll_no]))

def delete_fee(roll_no):
    run("DELETE FROM student_fees WHERE roll_no=%s", (roll_no,))

def bulk_delete_fees(rolls):
    for r in rolls:
        delete_fee(r)

def update_student(roll_no, data):
    if not data: return
    set_clause = ", ".join([f"{k}=%s" for k in data.keys()])
    run(f"UPDATE students SET {set_clause} WHERE roll_no=%s", tuple(list(data.values()) + [roll_no]))

def delete_student(roll_no):
    run("DELETE FROM students WHERE roll_no=%s", (roll_no,))

def get_payments(roll_no=None):
    if roll_no:
        return db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
    return db_all("SELECT * FROM payments ORDER BY id DESC LIMIT 100")

def add_payment(roll_no, amount, mode="cash", note="", paid_by="", receipt_no=""):
    run("""INSERT INTO payments (receipt_no, roll_no, amount, mode, pay_date, remark)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (receipt_no or "R"+datetime.now().strftime("%Y%m%d%H%M%S"),
         roll_no, amount, mode, today(), note))

def log_action(user, action, target="", details=""):
    try:
        run("INSERT INTO audit_logs (user_name, action, details) VALUES (%s,%s,%s)",
            (user, action, f"{target} {details}".strip()))
    except Exception:
        pass

def run_monthly_arrears():
    """No-op safe default — override if you add arrears logic later."""
    return {"updated": 0, "skipped": 0}


# ==================== AI SETUP ====================
try:
    import google.generativeai as genai
    HAS_AI = True
except ImportError:
    HAS_AI = False

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
ai_model = None
if HAS_AI and GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"AI Setup Error: {e}")


# ==================== AUTH ====================
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def calc_grade(pct):
    if pct >= 90: return "A+"
    if pct >= 80: return "A"
    if pct >= 70: return "B"
    if pct >= 60: return "C"
    if pct >= 50: return "D"
    return "F"


# ==================== LOGIN / LOGOUT ====================
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


# ==================== DASHBOARD ====================
@app.route("/dashboard")
@login_required
def dashboard():
    students_count = one("SELECT COUNT(*) c FROM students")["c"]
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
    lifetime_revenue = one("SELECT COALESCE(SUM(amount),0) t FROM payments")["t"]
    lifetime_expense = one("SELECT COALESCE(SUM(amount),0) t FROM expenses")["t"]
    lifetime_profit = lifetime_revenue - lifetime_expense

    month = current_month()
    today_str = today()
    today_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date = %s", (today_str,))["t"]
    current_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s", (month + "%",))["t"]

    monthly_target = 100000
    progress_pct = min(100, (current_collection / monthly_target * 100)) if monthly_target > 0 else 0

    paid_count = one("SELECT COUNT(*) c FROM bills WHERE status='Paid'")["c"]
    partial_count = one("SELECT COUNT(*) c FROM bills WHERE status='Partial'")["c"]
    unpaid_count = one("SELECT COUNT(*) c FROM bills WHERE status='Unpaid' OR status IS NULL")["c"]
    fee_status = {"paid": paid_count, "partial": partial_count, "unpaid": unpaid_count}

    top_defaulters = db_all("""
        SELECT s.id as student_id, s.name, s.roll_no, s.class_name, SUM(b.balance) as total_balance
        FROM bills b JOIN students s ON b.roll_no = s.roll_no
        WHERE b.balance > 0
        GROUP BY s.id, s.name, s.roll_no, s.class_name
        ORDER BY total_balance DESC LIMIT 5
    """)

    class_strength = db_all("SELECT class_name, COUNT(*) as count FROM students GROUP BY class_name ORDER BY class_name")

    top_performers_raw = db_all("""
        SELECT s.name, s.roll_no, s.class_name,
               SUM(CAST(m.marks AS FLOAT)) as total_obtained,
               SUM(CAST(m.total AS FLOAT)) as total_max
        FROM students s JOIN marks m ON s.roll_no = m.roll_no
        GROUP BY s.name, s.roll_no, s.class_name
        ORDER BY (SUM(CAST(m.marks AS FLOAT)) / NULLIF(SUM(CAST(m.total AS FLOAT)), 0)) DESC LIMIT 3
    """)
    performers_list = []
    for p in top_performers_raw:
        pct = (p['total_obtained'] / p['total_max'] * 100) if p['total_max'] > 0 else 0
        performers_list.append({"name": p['name'], "roll_no": p['roll_no'],
                                "class_name": p['class_name'], "pct": round(pct, 1)})

    today_date = datetime.now().strftime("%m-%d")
    birthdays = db_all("SELECT name, roll_no, class_name, dob FROM students WHERE substr(dob, 6, 5) = %s", (today_date,))
    recent_payments = db_all("SELECT receipt_no, roll_no, amount, pay_date FROM payments ORDER BY id DESC LIMIT 5")
    recent_admissions = db_all("SELECT name, roll_no, class_name, admission_date FROM students ORDER BY id DESC LIMIT 5")

    monthly_trend = []
    for i in range(5, -1, -1):
        target_date = datetime.now() - timedelta(days=i*30)
        m_str = target_date.strftime("%Y-%m")
        coll = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s", (m_str + "%",))["t"]
        exp = one("SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE exp_date LIKE %s", (m_str + "%",))["t"]
        monthly_trend.append({"month": target_date.strftime("%b %Y"), "collection": coll, "expense": exp})

    ai_insight = "AI summary loading..."
    if ai_model:
        prompt = f"""
        Aap ek School ke Principal ke AI assistant hain. Niche diye gaye data ka analysis karke 3 hisso me jawab dijiye:
        PART 1 - DAILY BRIEFING: 2 lines ka sharp summary (Hinglish me).
        PART 2 - PREDICTIVE RISK: Top defaulters ko dekh kar predict kijiye kaunse students default karne ke chance hain.
        PART 3 - REVENUE FORECAST: Pichle 6 mahine ke collection trend {[m['collection'] for m in monthly_trend]} ko dekh kar agle mahine ka expected revenue predict kijiye.

        Data:
        - Aaj ka Collection: Rs {today_collection}
        - Lifetime Net Profit: Rs {lifetime_profit}
        - Total Pending Fees: Rs {total_due}
        - Top Defaulters: {[f"{d['name']} (Rs {d['total_balance']})" for d in top_defaulters]}
        """
        try:
            ai_insight = ai_model.generate_content(prompt).text
        except Exception:
            ai_insight = "AI Briefing abhi available nahi hai."

    return render_template('dashboard.html', roll_no=roll_no)
        students=students_count, total_due=total_due,
        today_collection=today_collection, lifetime_profit=lifetime_profit,
        fee_status=fee_status, top_defaulters=top_defaulters,
        class_strength=class_strength, performers_list=performers_list,
        birthdays=birthdays, recent=recent_payments, recent_admissions=recent_admissions,
        monthly_trend=monthly_trend, ai_insight=ai_insight,
        monthly_target=monthly_target, progress_pct=progress_pct,
        current_collection=current_collection)


# ==================== ATTENDANCE ====================
@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    if request.method == "POST":
        att_date = request.form["att_date"]
        class_name = request.form["class_name"]
        run("""DELETE FROM attendance WHERE att_date=%s AND roll_no IN
               (SELECT roll_no FROM students WHERE class_name=%s)""", (att_date, class_name))
        present_count = absent_count = late_count = 0
        for key, value in request.form.items():
            if key.startswith("status_"):
                roll_no = key.replace("status_", "")
                run("INSERT INTO attendance (roll_no, att_date, status) VALUES (%s, %s, %s)",
                    (roll_no, att_date, value))
                if value == "Present": present_count += 1
                elif value == "Absent": absent_count += 1
                elif value == "Late": late_count += 1
        flash(f"✅ Attendance marked! P:{present_count} A:{absent_count} L:{late_count}", "success")
        return redirect(url_for("attendance", date=att_date, class_name=class_name))

    att_date = request.args.get("date", today())
    class_name = request.args.get("class_name", "")
    students_list = []
    if class_name:
        students_list = db_all("SELECT * FROM students WHERE class_name=%s ORDER BY roll_no", (class_name,))
    classes = db_all("SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL ORDER BY class_name")
    return render_template("attendance.html", students=students_list, classes=classes,
                           att_date=att_date, class_name=class_name)


# ==================== HEALTH ====================
@app.route("/student/health/save/<int:sid>", methods=["POST"])
@login_required
def save_health(sid):
    student = one("SELECT roll_no FROM students WHERE id=%s", (sid,))
    if not student: return redirect(url_for("students"))
    d = request.form
    existing = one("SELECT id FROM student_health WHERE roll_no=%s", (student['roll_no'],))
    if existing:
        run("UPDATE student_health SET blood_group=%s, allergies=%s, emergency_contact=%s WHERE roll_no=%s",
            (d["blood_group"], d["allergies"], d["emergency_contact"], student['roll_no']))
    else:
        run("INSERT INTO student_health (blood_group, allergies, emergency_contact, roll_no) VALUES (%s,%s,%s,%s)",
            (d["blood_group"], d["allergies"], d["emergency_contact"], student['roll_no']))
    flash("✅ Health record updated!", "success")
    return redirect(url_for("student_profile", sid=sid))


# ==================== BULK IMPORT ====================
@app.route("/student/bulk-import", methods=["GET", "POST"])
@login_required
def bulk_import():
    if request.method == "POST":
        if 'file' not in request.files:
            flash("Koi file select nahi ki gayi!", "error")
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.csv'):
            flash("Sirf .csv file allowed hai!", "error")
            return redirect(request.url)
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        count = 0
        for row in csv_input:
            try:
                run("""INSERT INTO students
                    (roll_no,name,father,mother,class_name,section,gender,dob,contact,parent_contact,address,admission_date,transport_route,hostel)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (row['roll_no'], row['name'], row.get('father',''), row.get('mother',''),
                     row.get('class_name',''), row.get('section',''), row.get('gender',''),
                     row.get('dob',''), row.get('contact',''), row.get('parent_contact',''),
                     row.get('address',''), row.get('admission_date',''),
                     row.get('transport_route',''), row.get('hostel','')))
                count += 1
            except Exception as e:
                print(f"Error importing {row.get('name')}: {e}")
        flash(f"✅ {count} students imported!", "success")
        return redirect(url_for("students"))
    return render_template("bulk_import.html")


# ==================== TRANSFER CERTIFICATE ====================
@app.route("/student/tc/<int:sid>")
@login_required
def transfer_certificate(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    if not student: return redirect(url_for("students"))
    pending = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance > 0", (student['roll_no'],))["t"]
    return render_template("transfer_certificate.html", student=student, pending=pending)


# ==================== STUDENTS LIST ====================
@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "")
    class_filter = request.args.get("class_filter", "")
    fee_filter = request.args.get("fee_filter", "")
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    query = """
        SELECT s.*, COALESCE(SUM(b.balance), 0) as total_balance
        FROM students s
        LEFT JOIN bills b ON s.roll_no = b.roll_no AND b.balance > 0
        WHERE 1=1
    """
    params = []
    if q:
        query += " AND (s.name LIKE %s OR s.roll_no LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if class_filter:
        query += " AND s.class_name = %s"
        params.append(class_filter)
    if fee_filter == "due":
        query += " AND b.balance > 0"
    elif fee_filter == "paid":
        query += " AND b.balance IS NULL"

    query += """
        GROUP BY s.id, s.roll_no, s.name, s.father, s.mother, s.class_name, s.section,
                 s.gender, s.dob, s.contact, s.parent_contact, s.address, s.admission_date,
                 s.transport_route, s.hostel
        ORDER BY s.roll_no LIMIT %s OFFSET %s
    """
    params.extend([per_page, offset])
    rows = db_all(query, tuple(params))

    count_query = "SELECT COUNT(DISTINCT s.id) as c FROM students s LEFT JOIN bills b ON s.roll_no = b.roll_no AND b.balance > 0 WHERE 1=1"
    count_params = []
    if q:
        count_query += " AND (s.name LIKE %s OR s.roll_no LIKE %s)"
        count_params.extend([f"%{q}%", f"%{q}%"])
    if class_filter:
        count_query += " AND s.class_name = %s"
        count_params.append(class_filter)
    if fee_filter == "due":
        count_query += " AND b.balance > 0"
    elif fee_filter == "paid":
        count_query += " AND b.balance IS NULL"

    total_students = one(count_query, tuple(count_params))["c"]
    total_pages = (total_students + per_page - 1) // per_page
    classes = db_all("SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL ORDER BY class_name")

    return render_template("students.html", students=rows, q=q,
                           class_filter=class_filter, fee_filter=fee_filter,
                           page=page, total_pages=total_pages, classes=classes)


# ==================== ADD / EDIT / DELETE STUDENT ====================
@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        run("""INSERT INTO students
            (roll_no,name,father,mother,class_name,section,gender,dob,
             contact,parent_contact,address,admission_date,transport_route,hostel,photo_url)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (d["roll_no"], d["name"], d["father"], d["mother"],
             d["class_name"], d["section"], d["gender"], d["dob"],
             d["contact"], d["parent_contact"], d["address"],
             d["admission_date"], d["transport_route"], d["hostel"],
             d.get("photo_url", "")))
        flash("✅ Student added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("students"))


@app.route("/student/edit/<int:sid>", methods=["GET", "POST"])
@login_required
def edit_student(sid):
    if request.method == "POST":
        d = request.form
        run("""UPDATE students SET
            roll_no=%s, name=%s, father=%s, mother=%s, class_name=%s, section=%s,
            gender=%s, dob=%s, contact=%s, parent_contact=%s, address=%s,
            admission_date=%s, transport_route=%s, hostel=%s, photo_url=%s WHERE id=%s""",
            (d["roll_no"], d["name"], d["father"], d["mother"], d["class_name"],
             d["section"], d["gender"], d["dob"], d["contact"], d["parent_contact"],
             d["address"], d["admission_date"], d["transport_route"], d["hostel"],
             d.get("photo_url", ""), sid))
        flash("✅ Student updated!", "success")
        return redirect(url_for("students"))
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    return render_template("edit_student.html", student=student)


@app.route("/student/delete/<int:sid>")
@login_required
def delete_student_route(sid):
    run("DELETE FROM students WHERE id=%s", (sid,))
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students"))


# ==================== STUDENT PROFILE / ID CARD / EXPORT ====================
@app.route("/student/profile/<int:sid>")
@login_required
def student_profile(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))

    bills = db_all("SELECT * FROM bills WHERE roll_no=%s ORDER BY month DESC", (student['roll_no'],))
    payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY pay_date DESC", (student['roll_no'],))
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (student['roll_no'],))
    total_obtained = sum(float(m['marks'] or 0) for m in marks)
    total_max = sum(float(m['total'] or 0) for m in marks)
    percentage = (total_obtained / total_max * 100) if total_max > 0 else 0
    total_billed = sum(b['total'] for b in bills)
    total_paid = sum(p['amount'] for p in payments)
    total_due = total_billed - total_paid

    return render_template("student_profile.html", student=student, bills=bills,
                           payments=payments, marks=marks, total_obtained=total_obtained,
                           total_max=total_max, percentage=percentage, total_due=total_due)


@app.route("/student/id-card/<int:sid>")
@login_required
def student_id_card(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    return render_template("id_card.html", student=student)


@app.route("/students/export")
@login_required
def export_students():
    rows = db_all("SELECT * FROM students ORDER BY roll_no")
    si = io.StringIO()
    if rows:
        w = csv.DictWriter(si, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows: w.writerow(dict(r))
    mem = io.BytesIO(si.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=f"students_{datetime.now():%Y%m%d}.csv")


# ==================== BULK REMINDERS ====================
@app.route("/api/bulk-reminders", methods=["POST"])
@login_required
def bulk_reminders():
    data = request.get_json() or {}
    student_ids = data.get("student_ids", [])
    if not student_ids:
        return jsonify({"error": "No students selected"})
    links = []
    for sid in student_ids:
        student = one("SELECT * FROM students WHERE id=%s", (sid,))
        if student:
            pending = one("SELECT SUM(balance) t FROM bills WHERE roll_no=%s AND balance > 0", (student['roll_no'],))["t"]
            if pending and pending > 0:
                phone = student['parent_contact'] or student['contact']
                if phone and len(str(phone)) == 10:
                    phone = "91" + str(phone)
                msg = f"Dear Parent, {student['name']} ki Rs {pending} fees pending hai. Kripya jaldi jama karein."
                links.append(f"https://wa.me/{phone}?text={quote(msg)}")
    return jsonify({"links": links, "count": len(links)})


# ==================== FEES (FIXED) ====================
@app.route("/fees")
@login_required
def fees():
    rows = db_all("""
        SELECT s.roll_no, s.name, s.class_name, s.section,
               s.parent_contact as parent_phone, s.contact as phone,
               COALESCE(f.tuition_fee,0) as tuition_fee,
               COALESCE(f.transport_fee,0) as transport_fee,
               COALESCE(f.hostel_fee,0) as hostel_fee,
               COALESCE(f.admission_fee,0) as admission_fee,
               COALESCE(f.dress_fee,0) as dress_fee,
               COALESCE(f.exam_fee,0) as exam_fee,
               COALESCE(f.book_fee,0) as book_fee,
               COALESCE(f.notebook_fee,0) as notebook_fee,
               COALESCE(f.misc_fee,0) as misc_fee,
               COALESCE(f.admission_paid,0) as admission_paid,
               COALESCE((SELECT SUM(balance) FROM bills WHERE roll_no=s.roll_no AND balance>0), 0) as back_dues
        FROM students s LEFT JOIN student_fees f ON s.roll_no = f.roll_no
        ORDER BY s.roll_no
    """)
    return render_template("fees.html", fees=rows)


@app.route("/fees/save", methods=["POST"])
@login_required
def save_fees():
    d = request.form
    roll = d["roll_no"]
    vals = (
        float(d.get("tuition_fee") or 0), float(d.get("transport_fee") or 0),
        float(d.get("hostel_fee") or 0), float(d.get("admission_fee") or 0),
        float(d.get("dress_fee") or 0), float(d.get("exam_fee") or 0),
        float(d.get("book_fee") or 0), float(d.get("notebook_fee") or 0),
        float(d.get("misc_fee") or 0), int(d.get("admission_paid") or 0),
        roll
    )
    existing = one("SELECT id FROM student_fees WHERE roll_no=%s", (roll,))
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


@app.route("/edit_fees/<roll_no>", methods=["GET", "POST"])
@login_required
def edit_fees(roll_no):
    fee = get_fee(roll_no)
    student = get_student(roll_no)
    if not fee or not student:
        flash(f"❌ Record not found for {roll_no}", "warning")
        return redirect(url_for("fees"))

    if request.method == "POST":
        def num(k):
            try: return float(request.form.get(k) or 0)
            except (ValueError, TypeError): return 0
        try:
            save_fee(roll_no,
                tuition_fee=num('tuition_fee'), transport_fee=num('transport_fee'),
                hostel_fee=num('hostel_fee'), admission_fee=num('admission_fee'),
                dress_fee=num('dress_fee'), exam_fee=num('exam_fee'),
                book_fee=num('book_fee'), notebook_fee=num('notebook_fee'),
                misc_fee=num('misc_fee'), admission_paid=int(num('admission_paid')),
            )
            name = request.form.get('student_name', '').strip()
            if name:
                update_student(roll_no, {'name': name})
            log_action(session['user'], 'EDIT_FEES', roll_no)
            flash(f"✅ {roll_no} updated!", "success")
            return redirect(url_for("fees"))
        except Exception as e:
            flash(f"❌ Failed: {e}", "danger")

    # Merge student data into fee dict so template can access easily
    merged = dict(fee)
    merged['name'] = student['name']
    merged['class_name'] = student.get('class_name', '')
    merged['section'] = student.get('section', '')
    merged['parent_phone'] = student.get('parent_contact', '')
    return render_template('edit_fees.html', fee=merged, student=student)


@app.route("/delete_fees/<roll_no>")
@login_required
def delete_fees(roll_no):
    try:
        delete_fee(roll_no)
        flash(f"🗑️ {roll_no} fee deleted", "success")
    except Exception as e:
        flash(f"❌ {e}", "danger")
    return redirect(url_for("fees"))


@app.route("/receipt/<roll_no>")
@login_required
def receipt(roll_no):
    fee = get_fee(roll_no)
    student = get_student(roll_no)
    if not fee or not student:
        flash("❌ No record", "warning")
        return redirect(url_for("fees"))
    total = sum([float(fee.get(k) or 0) for k in [
        'tuition_fee', 'transport_fee', 'hostel_fee', 'admission_fee',
        'dress_fee', 'exam_fee', 'book_fee', 'notebook_fee', 'misc_fee'
    ]])
    # Add back_dues from bills
    back_dues = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
    total += float(back_dues or 0)
    return render_template("receipt.html",
        fee=fee, student=student,
        payments=get_payments(roll_no),
        total=total, now=datetime.now())


@app.route("/collect/<roll_no>", methods=["GET", "POST"])
@login_required
def collect(roll_no=None):
    if request.method == "POST":
        roll_no = request.form.get("roll_no")
        try:
            amount = float(request.form.get("amount") or 0)
            fee = get_fee(roll_no)
            if amount > 0:
                # Try to reduce back_dues via bills first
                open_bills = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month", (roll_no,))
                remaining = amount
                for b in open_bills:
                    if remaining <= 0: break
                    pay = min(remaining, float(b['balance']))
                    new_paid = float(b['paid']) + pay
                    new_bal = float(b['total']) - new_paid
                    status = "Paid" if new_bal <= 0 else "Partial"
                    run("UPDATE bills SET paid=%s,balance=%s,status=%s WHERE id=%s",
                        (new_paid, new_bal, status, b['id']))
                    remaining -= pay

                rcp = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
                add_payment(roll_no, amount, mode=request.form.get('mode', 'cash'),
                            note=request.form.get('note', ''), paid_by=session.get('user', 'system'),
                            receipt_no=rcp)
                flash(f'✅ ₹{amount} collected! Receipt: {rcp}', 'success')
                return redirect(url_for('receipt', roll_no=roll_no))
        except Exception as e:
            flash(f'❌ {e}', 'danger')

    fee = get_fee(roll_no) if roll_no else None
    student = get_student(roll_no) if roll_no else None
    return render_template('collect.html', fee=fee, student=student)


@app.route("/bulk_delete_fees", methods=["POST"])
@login_required
def bulk_delete_fees_route():
    try:
        data = request.get_json() or {}
        rolls = data.get('roll_nos', [])
        if not rolls:
            return jsonify({'error': 'No rolls'}), 400
        for r in rolls:
            delete_fee(r)
        return jsonify({'success': True, 'deleted': len(rolls)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/run_arrears_update")
@login_required
def run_arrears_update():
    try:
        result = run_monthly_arrears()
        flash(f"✅ Arrears updated — {result.get('updated', 0)} students", "success")
    except Exception as e:
        flash(f"❌ {e}", "danger")
    return redirect(url_for("fees"))


# ==================== BILLS ====================
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
    students_list = db_all("SELECT roll_no, name FROM students")
    created = skipped = 0
    for s in students_list:
        roll = s["roll_no"]
        ex = one("SELECT id FROM bills WHERE roll_no=%s AND month=%s", (roll, month))
        if ex:
            skipped += 1; continue
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs:
            skipped += 1; continue

        t = fs["tuition_fee"] or 0; tr = fs["transport_fee"] or 0; ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        prev_added = one("SELECT COALESCE(SUM(admission),0) a FROM bills WHERE roll_no=%s", (roll,))["a"]
        adm = 0 if (adm_paid or prev_added > 0) else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        prev_due = one("SELECT COALESCE(SUM(balance),0) d FROM bills WHERE roll_no=%s AND balance>0", (roll,))["d"]
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due
        bill_no = f"B{month.replace('-','')}{roll}"

        run("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (bill_no, roll, month, today(), t, tr, ho, adm, dr, ex_f, bk, nb, ms,
             prev_due, total, 0, total, "Unpaid"))
        created += 1
    flash(f"✅ Bills created: {created} | Skipped: {skipped}", "success")
    return redirect(url_for("bills", month=month))


# ==================== COLLECT (old route) ====================
@app.route("/collect_old", methods=["GET", "POST"])
@login_required
def collect_old():
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
        run("""INSERT INTO payments (receipt_no,roll_no,bill_id,amount,mode,pay_date,remark)
               VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (rc, bill["roll_no"], bill_id, amt, mode, today(), remark))
        flash(f"✅ Payment ₹{amt:,.0f} recorded! Receipt: {rc}", "success")
        return redirect(url_for("collect_old"))
    roll = request.args.get("roll", "")
    rows = []
    if roll:
        rows = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month", (roll,))
    return render_template("collect.html", bills=rows, roll=roll)


# ==================== DEFAULTERS ====================
@app.route("/defaulters")
@login_required
def defaulters():
    rows = db_all("""SELECT s.roll_no, s.name, s.class_name, s.section,
                     s.parent_contact, b.month, b.balance
                     FROM bills b JOIN students s ON b.roll_no = s.roll_no
                     WHERE b.balance > 0 ORDER BY b.balance DESC""")
    total = sum(r["balance"] for r in rows)
    return render_template("defaulters.html", defaulters=rows, total=total)


# ==================== EXPENSES ====================
@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        d = request.form
        run("""INSERT INTO expenses (category,description,amount,exp_date,staff_id)
               VALUES(%s,%s,%s,%s,%s)""",
            (d["category"], d["description"], d["amount"], d["exp_date"], d.get("staff_id", "")))
        flash("✅ Expense added!", "success")
    rows = db_all("SELECT * FROM expenses ORDER BY id DESC")
    return render_template("expenses.html", expenses=rows)


# ==================== REPORTS ====================
@app.route("/reports")
@login_required
def reports():
    coll = db_all("""SELECT substr(pay_date,1,7) m, SUM(amount) a FROM payments
                     GROUP BY m ORDER BY m DESC LIMIT 12""")
    exp = db_all("""SELECT substr(exp_date,1,7) m, SUM(amount) a FROM expenses
                    GROUP BY m ORDER BY m DESC LIMIT 12""")
    total_c = one("SELECT COALESCE(SUM(amount),0) t FROM payments")["t"]
    total_e = one("SELECT COALESCE(SUM(amount),0) t FROM expenses")["t"]
    return render_template("reports.html", coll=coll, exp=exp, total_c=total_c,
                           total_e=total_e, profit=total_c - total_e)


# ==================== RESULT / MARKS ====================
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
                m = float(r["marks"] or 0); t = float(r["total"] or 0)
                pct = (m / t * 100) if t > 0 else 0
                marks.append({"subject": r["subject"], "exam": r["exam"],
                              "marks": r["marks"], "total": r["total"],
                              "pct": pct, "grade": calc_grade(pct)})
                total_obtained += m; total_max += t
            if total_max > 0:
                overall_pct = total_obtained / total_max * 100
                overall_grade = calc_grade(overall_pct)
    return render_template("report_card.html", student=student, marks=marks,
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
            FROM students s JOIN marks m ON s.roll_no = m.roll_no
            WHERE s.class_name = %s
            GROUP BY s.roll_no, s.name
            ORDER BY (total_obtained / total_max) DESC
        """, (class_name,))
        for r in rows:
            to = float(r["total_obtained"] or 0); tm = float(r["total_max"] or 0)
            pct = (to / tm * 100) if tm > 0 else 0
            merit.append({"roll_no": r["roll_no"], "name": r["name"],
                          "total_obtained": to, "total_max": tm,
                          "pct": pct, "grade": calc_grade(pct)})
    return render_template("merit_list.html", merit=merit, class_name=class_name)


# ==================== CSV EXPORT ====================
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
        for r in rows: w.writerow(dict(r))
    mem = io.BytesIO(si.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=f"{table}_{datetime.now():%Y%m%d}.csv")


# ==================== ANALYTICS ====================
@app.route("/analytics")
@login_required
def analytics():
    monthly_data = db_all("""
        SELECT substr(pay_date, 1, 7) as month, SUM(amount) as collection
        FROM payments GROUP BY month ORDER BY month DESC LIMIT 6
    """)
    class_dist = db_all("""
        SELECT class_name, COUNT(*) as count FROM students
        GROUP BY class_name ORDER BY class_name
    """)
    top_payers = db_all("""
        SELECT s.name, s.roll_no, SUM(p.amount) as total_paid
        FROM payments p JOIN students s ON p.roll_no = s.roll_no
        GROUP BY s.name, s.roll_no ORDER BY total_paid DESC LIMIT 10
    """)
    yearly_total = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s",
                       (str(datetime.now().year) + "%",))["t"]
    pending_count = one("SELECT COUNT(*) c FROM bills WHERE balance > 0")["c"]
    return render_template("analytics.html",
        monthly_data=monthly_data, class_dist=class_dist,
        top_payers=top_payers, yearly_total=yearly_total,
        pending_count=pending_count)


# ==================== AI ASSISTANT ====================
@app.route("/ai-assistant", methods=["GET", "POST"])
@login_required
def ai_assistant():
    if request.method == "POST":
        data = request.get_json() or {}
        user_query = data.get("query", "").strip()
        if not user_query:
            return jsonify({"reply": "Kuch pooch toh sahi bhai!"})
        if not ai_model:
            return jsonify({"reply": "AI abhi available nahi hai. GEMINI_API_KEY set kar."})
        total_students = one("SELECT COUNT(*) c FROM students")["c"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        context = f"""
        Aap ek School Management System ke AI assistant hain. Hinglish me short aur helpful jawab dijiye.
        Total Students: {total_students}
        Total Pending Fees: Rs {total_due}
        User ka Sawaal: {user_query}
        """
        try:
            response = ai_model.generate_content(context)
            return jsonify({"reply": response.text})
        except Exception as e:
            return jsonify({"reply": f"AI Error: {str(e)}"})
    return render_template("ai_assistant.html")


@app.route("/ai-hub")
@login_required
def ai_hub():
    students_list = db_all("SELECT id, name, roll_no FROM students ORDER BY name")
    options = "".join([f'<option value="{s["id"]}">{s["name"]} (Roll: {s["roll_no"]})</option>' for s in students_list])
    return render_template("ai_hub.html", students_options=options)


# ==================== STAFF ====================
@app.route("/staff")
@login_required
def staff():
    q = request.args.get("q", "")
    if q:
        rows = db_all("SELECT * FROM staff WHERE name LIKE %s OR subject LIKE %s ORDER BY name", (f"%{q}%", f"%{q}%"))
    else:
        rows = db_all("SELECT * FROM staff ORDER BY name")
    total_salary = sum(s['salary'] or 0 for s in rows)
    return render_template("staff.html", staff=rows, q=q, total_salary=total_salary)


@app.route("/staff/add", methods=["POST"])
@login_required
def add_staff():
    d = request.form
    try:
        run("""INSERT INTO staff (staff_id,name,designation,subject,contact,email,joining_date,salary,address)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (d["staff_id"], d["name"], d["designation"], d["subject"], d["contact"],
             d["email"], d["joining_date"], d["salary"] or 0, d["address"]))
        flash("✅ Staff member added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("staff"))


@app.route("/staff/delete/<int:sid>")
@login_required
def delete_staff(sid):
    run("DELETE FROM staff WHERE id=%s", (sid,))
    flash("🗑️ Staff deleted.", "success")
    return redirect(url_for("staff"))


# ==================== LIBRARY ====================
@app.route("/library")
@login_required
def library():
    q = request.args.get("q", "")
    if q:
        books = db_all("SELECT * FROM library_books WHERE title LIKE %s OR author LIKE %s ORDER BY title", (f"%{q}%", f"%{q}%"))
    else:
        books = db_all("SELECT * FROM library_books ORDER BY title")
    issued = db_all("""SELECT bi.*, s.name as student_name, lb.title
                       FROM book_issues bi
                       LEFT JOIN students s ON bi.roll_no = s.roll_no
                       LEFT JOIN library_books lb ON bi.book_id = lb.book_id
                       WHERE bi.status='Issued' ORDER BY bi.due_date""")
    return render_template("library.html", books=books, issued=issued, q=q)


@app.route("/library/add-book", methods=["POST"])
@login_required
def add_book():
    d = request.form
    try:
        run("""INSERT INTO library_books (book_id,title,author,category,total_copies,available_copies)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (d["book_id"], d["title"], d["author"], d["category"], d["copies"], d["copies"]))
        flash("✅ Book added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("library"))


@app.route("/library/issue", methods=["POST"])
@login_required
def issue_book():
    d = request.form
    book = one("SELECT * FROM library_books WHERE book_id=%s", (d["book_id"],))
    if not book or book['available_copies'] <= 0:
        flash("❌ Book available nahi hai!", "error")
        return redirect(url_for("library"))
    issue_date = today()
    due_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    run("""INSERT INTO book_issues (book_id,roll_no,issue_date,due_date,status)
           VALUES (%s,%s,%s,%s,'Issued')""", (d["book_id"], d["roll_no"], issue_date, due_date))
    run("UPDATE library_books SET available_copies = available_copies - 1 WHERE book_id=%s", (d["book_id"],))
    flash(f"✅ Book issued! Due: {due_date}", "success")
    return redirect(url_for("library"))


@app.route("/library/return/<int:iid>")
@login_required
def return_book(iid):
    issue = one("SELECT * FROM book_issues WHERE id=%s", (iid,))
    if issue:
        return_date = today()
        due = datetime.strptime(issue['due_date'], "%Y-%m-%d")
        today_dt = datetime.strptime(return_date, "%Y-%m-%d")
        late_days = (today_dt - due).days
        fine = max(0, late_days * 5)
        run("UPDATE book_issues SET return_date=%s, status='Returned', fine=%s WHERE id=%s",
            (return_date, fine, iid))
        run("UPDATE library_books SET available_copies = available_copies + 1 WHERE book_id=%s", (issue['book_id'],))
        flash(f"✅ Book returned! Fine: Rs {fine}", "success")
    return redirect(url_for("library"))


# ==================== BROADCAST ====================
@app.route("/broadcast")
@login_required
def broadcast():
    return render_template("broadcast.html")


@app.route("/api/broadcast", methods=["POST"])
@login_required
def api_broadcast():
    data = request.get_json() or {}
    target = data.get("target", "all")
    message = data.get("message", "").strip()
    if not message: return jsonify({"error": "Message khali hai!"})
    recipients = []
    if target == "all":
        recipients = db_all("SELECT name, parent_contact as phone FROM students WHERE parent_contact IS NOT NULL")
    elif target == "defaulters":
        recipients = db_all("""SELECT DISTINCT s.name, s.parent_contact as phone
                               FROM students s JOIN bills b ON s.roll_no = b.roll_no
                               WHERE b.balance > 0 AND s.parent_contact IS NOT NULL""")
    links = []
    for r in recipients[:20]:
        phone = str(r['phone'])
        if len(phone) == 10: phone = "91" + phone
        personalized_msg = message.replace("{name}", r['name'])
        links.append(f"https://wa.me/{phone}?text={quote(personalized_msg)}")
    return jsonify({"links": links, "count": len(links)})


# ==================== HOSTEL ====================
@app.route("/hostel")
@login_required
def hostel():
    rooms = db_all("SELECT * FROM hostel_rooms ORDER BY room_no")
    allocations = db_all("""SELECT ha.*, s.name as student_name, s.class_name, s.contact
                            FROM hostel_allocations ha
                            LEFT JOIN students s ON ha.roll_no = s.roll_no
                            WHERE ha.status='Active' ORDER BY ha.allocated_date DESC""")
    total_capacity = sum(r['capacity'] for r in rooms)
    total_occupied = sum(r['occupied'] for r in rooms)
    monthly_income = sum((r['monthly_fee'] * r['occupied']) for r in rooms)
    return render_template("hostel.html", rooms=rooms, allocations=allocations,
                           total_capacity=total_capacity, total_occupied=total_occupied,
                           monthly_income=monthly_income)


@app.route("/hostel/add-room", methods=["POST"])
@login_required
def add_hostel_room():
    d = request.form
    try:
        run("""INSERT INTO hostel_rooms (room_no,floor,capacity,monthly_fee,warden_name,warden_contact)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (d["room_no"], d["floor"], d["capacity"], d["monthly_fee"] or 0,
             d["warden_name"], d["warden_contact"]))
        flash("✅ Hostel room added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("hostel"))


@app.route("/hostel/allocate", methods=["POST"])
@login_required
def allocate_hostel():
    d = request.form
    room = one("SELECT * FROM hostel_rooms WHERE room_no=%s", (d["room_no"],))
    if not room or room['occupied'] >= room['capacity']:
        flash("❌ Room full hai!", "error")
        return redirect(url_for("hostel"))
    run("""INSERT INTO hostel_allocations (roll_no, room_no, allocated_date, status)
           VALUES (%s,%s,%s,'Active')""", (d["roll_no"], d["room_no"], today()))
    run("UPDATE hostel_rooms SET occupied = occupied + 1 WHERE room_no=%s", (d["room_no"],))
    flash(f"✅ Allocated to Room {d['room_no']}!", "success")
    return redirect(url_for("hostel"))


@app.route("/hostel/vacate/<int:aid>")
@login_required
def vacate_hostel(aid):
    alloc = one("SELECT * FROM hostel_allocations WHERE id=%s", (aid,))
    if alloc:
        run("UPDATE hostel_allocations SET status='Vacated' WHERE id=%s", (aid,))
        run("UPDATE hostel_rooms SET occupied = GREATEST(0, occupied - 1) WHERE room_no=%s", (alloc['room_no'],))
        flash("✅ Room vacated!", "success")
    return redirect(url_for("hostel"))


# ==================== TRANSPORT ====================
@app.route("/transport")
@login_required
def transport():
    routes = db_all("SELECT * FROM transport_routes ORDER BY route_number")
    allocations = db_all("""SELECT ta.*, s.name as student_name, s.class_name, s.contact
                            FROM transport_allocations ta
                            LEFT JOIN students s ON ta.roll_no = s.roll_no
                            WHERE ta.status='Active' ORDER BY ta.route_number""")
    total_buses = len(routes)
    total_students = sum(r['occupied'] for r in routes)
    monthly_income = sum((r['monthly_fee'] * r['occupied']) for r in routes)
    return render_template("transport.html", routes=routes, allocations=allocations,
                           total_buses=total_buses, total_students=total_students,
                           monthly_income=monthly_income)


@app.route("/transport/add-route", methods=["POST"])
@login_required
def add_transport_route():
    d = request.form
    try:
        run("""INSERT INTO transport_routes
               (route_name,route_number,driver_name,driver_contact,vehicle_no,capacity,monthly_fee,stops)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (d["route_name"], d["route_number"], d["driver_name"], d["driver_contact"],
             d["vehicle_no"], d["capacity"], d["monthly_fee"] or 0, d["stops"]))
        flash("✅ Transport route added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("transport"))


@app.route("/transport/allocate", methods=["POST"])
@login_required
def allocate_transport():
    d = request.form
    route = one("SELECT * FROM transport_routes WHERE route_number=%s", (d["route_number"],))
    if not route or route['occupied'] >= route['capacity']:
        flash("❌ Bus full hai!", "error")
        return redirect(url_for("transport"))
    run("""INSERT INTO transport_allocations (roll_no, route_number, stop_name, allocated_date, status)
           VALUES (%s,%s,%s,%s,'Active')""", (d["roll_no"], d["route_number"], d["stop_name"], today()))
    run("UPDATE transport_routes SET occupied = occupied + 1 WHERE route_number=%s", (d["route_number"],))
    flash(f"✅ Added to Route {d['route_number']}!", "success")
    return redirect(url_for("transport"))


@app.route("/transport/remove/<int:aid>")
@login_required
def remove_transport(aid):
    alloc = one("SELECT * FROM transport_allocations WHERE id=%s", (aid,))
    if alloc:
        run("UPDATE transport_allocations SET status='Removed' WHERE id=%s", (aid,))
        run("UPDATE transport_routes SET occupied = GREATEST(0, occupied - 1) WHERE route_number=%s", (alloc['route_number'],))
        flash("✅ Student removed from transport!", "success")
    return redirect(url_for("transport"))


# ==================== PARENT PORTAL ====================
@app.route("/parent/login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        parent = one("SELECT * FROM parent_users WHERE username=%s AND password=%s AND active=1", (u, p))
        if parent:
            session["parent_user"] = parent["username"]
            session["parent_name"] = parent["parent_name"]
            session["parent_child"] = parent["child_roll_no"]
            return redirect(url_for("parent_dashboard"))
        flash("Invalid credentials!", "error")
    return render_template("parent_login.html")


@app.route("/parent/dashboard")
def parent_dashboard():
    if "parent_user" not in session:
        return redirect(url_for("parent_login"))
    roll = session["parent_child"]
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll,))
    if not student:
        flash("Student data nahi mila!", "error")
        return redirect(url_for("parent_login"))

    bills = db_all("SELECT * FROM bills WHERE roll_no=%s ORDER BY month DESC", (roll,))
    payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY pay_date DESC", (roll,))
    total_billed = sum(b['total'] for b in bills)
    total_paid = sum(p['amount'] for p in payments)
    total_due = total_billed - total_paid

    marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll,))
    total_o = sum(float(m['marks'] or 0) for m in marks)
    total_m = sum(float(m['total'] or 0) for m in marks)
    percentage = (total_o / total_m * 100) if total_m > 0 else 0

    att_total = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll,))["c"]
    att_present = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll,))["c"]
    att_pct = round((att_present/att_total*100) if att_total > 0 else 100, 1)

    return render_template("parent_dashboard.html", student=student, bills=bills,
                           payments=payments, total_due=total_due, marks=marks,
                           percentage=percentage, att_pct=att_pct)


@app.route("/parent/add-user", methods=["POST"])
@login_required
def add_parent_user():
    d = request.form
    try:
        run("""INSERT INTO parent_users (username,password,parent_name,child_roll_no,contact)
               VALUES (%s,%s,%s,%s,%s)""",
            (d["username"], d["password"], d["parent_name"], d["child_roll_no"], d["contact"]))
        flash("✅ Parent account created!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("students"))


@app.route("/parent/logout")
def parent_logout():
    for key in ["parent_user", "parent_name", "parent_child"]:
        session.pop(key, None)
    return redirect(url_for("parent_login"))


# ==================== CLASSES & SUBJECTS ====================
@app.route("/classes")
@login_required
def classes():
    cls_list = db_all("SELECT * FROM classes ORDER BY class_name")
    subjects = db_all("SELECT * FROM subjects ORDER BY class_name, subject_name")
    return render_template("classes.html", classes=cls_list, subjects=subjects)


@app.route("/class/add", methods=["POST"])
@login_required
def add_class():
    d = request.form
    try:
        run("INSERT INTO classes (class_name, sections, class_teacher, room_no) VALUES (%s,%s,%s,%s)",
            (d["class_name"], d["sections"], d["class_teacher"], d["room_no"]))
        log_action(session.get("user", "System"), "Class Added", details=f"Class: {d['class_name']}")
        flash("✅ Class added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("classes"))


@app.route("/class/delete/<int:cid>")
@login_required
def delete_class(cid):
    run("DELETE FROM classes WHERE id=%s", (cid,))
    flash("🗑️ Class deleted.", "success")
    return redirect(url_for("classes"))


@app.route("/subject/add", methods=["POST"])
@login_required
def add_subject():
    d = request.form
    try:
        run("""INSERT INTO subjects (subject_name, subject_code, class_name, teacher_name, max_marks)
               VALUES (%s,%s,%s,%s,%s)""",
            (d["subject_name"], d["subject_code"], d["class_name"], d["teacher_name"], d["max_marks"] or 100))
        flash("✅ Subject added!", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("classes"))


@app.route("/subject/delete/<int:sid>")
@login_required
def delete_subject(sid):
    run("DELETE FROM subjects WHERE id=%s", (sid,))
    flash("🗑️ Subject deleted.", "success")
    return redirect(url_for("classes"))


# ==================== AUDIT LOGS ====================
@app.route("/audit-logs")
@login_required
def audit_logs():
    q = request.args.get("q", "")
    if q:
        logs = db_all("""SELECT * FROM audit_logs WHERE user_name LIKE %s OR action LIKE %s
                         ORDER BY log_time DESC LIMIT 200""", (f"%{q}%", f"%{q}%"))
    else:
        logs = db_all("SELECT * FROM audit_logs ORDER BY log_time DESC LIMIT 200")
    return render_template("audit_logs.html", logs=logs, q=q)


# ==================== NOTICES ====================
@app.route("/notices", methods=["GET", "POST"])
@login_required
def notices():
    if request.method == "POST":
        d = request.form
        run("""INSERT INTO notices (title, content, category, posted_by, posted_date, priority)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (d["title"], d["content"], d["category"], session.get("name", "Admin"), today(), d["priority"]))
        log_action(session.get("user", "System"), "Notice Posted", details=f"Title: {d['title']}")
        flash("✅ Notice posted!", "success")
        return redirect(url_for("notices"))
    notices_list = db_all("SELECT * FROM notices WHERE active=1 ORDER BY posted_date DESC, id DESC")
    return render_template("notices.html", notices=notices_list)


@app.route("/notice/delete/<int:nid>")
@login_required
def delete_notice(nid):
    run("UPDATE notices SET active=0 WHERE id=%s", (nid,))
    flash("🗑️ Notice removed.", "success")
    return redirect(url_for("notices"))


@app.route("/notice-board-public")
def notice_board_public():
    notices_list = db_all("SELECT * FROM notices WHERE active=1 ORDER BY priority DESC, posted_date DESC LIMIT 20")
    return render_template("notice_board_public.html", notices=notices_list)


# ==================== CERTIFICATES ====================
@app.route("/certificate/<int:sid>/<cert_type>")
@login_required
def generate_certificate(sid, cert_type):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))
    pending = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (student['roll_no'],))["t"]
    ai_content = ""
    if ai_model:
        type_map = {
            "bonafide": "Bonafide Certificate",
            "character": "Character Certificate",
            "migration": "Migration Certificate",
            "merit": "Merit Certificate",
            "sports": "Sports Certificate"
        }
        cert_desc = type_map.get(cert_type, "Achievement Certificate")
        prompt = f"""
        Aap School Principal hain. Student {student['name']} (Class {student['class_name']}-{student['section']}, Roll {student['roll_no']}, Father: {student['father']}) ke liye ek {cert_desc} ka official content likhein.
        Format: 1 line heading, 3-4 lines formal body, closing. Max 60 words.
        """
        try:
            ai_content = ai_model.generate_content(prompt).text
        except Exception:
            pass
    return render_template("certificate.html", student=student, cert_type=cert_type,
                           pending=pending, ai_content=ai_content, today_date=today())


# ==================== ATTENDANCE ANALYTICS ====================
@app.route("/attendance/analytics")
@login_required
def attendance_analytics():
    last_7 = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        total = one("SELECT COUNT(*) c FROM attendance WHERE att_date=%s", (d,))["c"]
        present = one("SELECT COUNT(*) c FROM attendance WHERE att_date=%s AND status='Present'", (d,))["c"]
        absent = one("SELECT COUNT(*) c FROM attendance WHERE att_date=%s AND status='Absent'", (d,))["c"]
        last_7.append({"date": d, "present": present, "absent": absent, "total": total})

    class_att = db_all("""
        SELECT s.class_name, COUNT(a.id) as total,
               SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present
        FROM students s LEFT JOIN attendance a ON s.roll_no = a.roll_no
        WHERE s.class_name IS NOT NULL
        GROUP BY s.class_name ORDER BY s.class_name
    """)
    overall_total = one("SELECT COUNT(*) c FROM attendance")["c"]
    overall_present = one("SELECT COUNT(*) c FROM attendance WHERE status='Present'")["c"]
    overall_pct = round((overall_present/overall_total*100) if overall_total > 0 else 0, 1)
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    top_absentees = db_all("""
        SELECT s.name, s.roll_no, s.class_name, COUNT(*) as absences
        FROM attendance a JOIN students s ON a.roll_no = s.roll_no
        WHERE a.status='Absent' AND a.att_date >= %s
        GROUP BY s.name, s.roll_no, s.class_name
        ORDER BY absences DESC LIMIT 10
    """, (month_ago,))
    return render_template("attendance_analytics.html", last_7=last_7,
                           class_att=class_att, overall_pct=overall_pct,
                           top_absentees=top_absentees,
                           overall_present=overall_present, overall_total=overall_total)


# ==================== BACKUP ====================
@app.route("/backup")
@login_required
def backup():
    return render_template("backup.html")


@app.route("/backup/download")
@login_required
def backup_download():
    tables = ["students", "bills", "payments", "expenses", "marks", "staff",
              "library_books", "book_issues", "hostel_rooms", "hostel_allocations",
              "transport_routes", "transport_allocations", "notices", "classes", "subjects"]
    output = io.StringIO()
    output.write(f"-- School ERP Backup\n-- Generated: {datetime.now()}\n\n")
    for table in tables:
        try:
            rows = db_all(f"SELECT * FROM {table}")
            if not rows: continue
            cols = ", ".join(rows[0].keys())
            output.write(f"\n-- Table: {table} ({len(rows)} rows)\n")
            for r in rows:
                vals = ", ".join([f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if v is not None else "NULL" for v in r.values()])
                output.write(f"INSERT INTO {table} ({cols}) VALUES ({vals});\n")
        except Exception:
            continue
    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    log_action(session.get("user", "System"), "Backup Downloaded")
    return send_file(mem, mimetype="application/sql", as_attachment=True,
                     download_name=f"school_backup_{datetime.now():%Y%m%d_%H%M}.sql")


# ============================================================
# MAIN — YEH SABSE LAST ME HONA CHAHIYE
# ============================================================
if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"DB init warning: {e}")

    print("\n=== ALL ROUTES ===")
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        if rule.endpoint != 'static':
            print(f"{rule.endpoint:35s} → {rule.rule}")
    print("===================\n")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
