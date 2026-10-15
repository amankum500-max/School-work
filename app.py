"""
=====================================================
   🏫 SCHOOL MANAGEMENT - WEB VERSION (Flask)
   Mobile-friendly • Responsive • Modern UI
=====================================================
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify)
from functools import wraps
import csv, io, os
from datetime import datetime, timedelta
from database import init_db, run, all as db_all, one, current_month, today

app = Flask(__name__)
app.secret_key = "school-secret-key-change-this-2026"

# ---------- AI Setup ----------
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
    # 1. Basic & Lifetime Stats
    students_count = one("SELECT COUNT(*) c FROM students")["c"]
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
    lifetime_revenue = one("SELECT COALESCE(SUM(amount),0) t FROM payments")["t"]
    lifetime_expense = one("SELECT COALESCE(SUM(amount),0) t FROM expenses")["t"]
    lifetime_profit = lifetime_revenue - lifetime_expense

    # 2. Current Month & Today Stats
    month = current_month()
    today_str = today()
    today_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date = %s", (today_str,))["t"]
    current_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s", (month + "%",))["t"]
    
    # 3. Monthly Target Progress (Aap yahan target change kar sakte hain)
    monthly_target = 100000 # Example: Rs 1 Lakh ka target
    progress_pct = min(100, (current_collection / monthly_target * 100)) if monthly_target > 0 else 0

    # 4. Fee Status & Top Defaulters
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

    # 5. Class Strength & Top Performers
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
        performers_list.append({"name": p['name'], "roll_no": p['roll_no'], "class_name": p['class_name'], "pct": round(pct, 1)})

    # 6. Birthdays & Recent Activities
    today_date = datetime.now().strftime("%m-%d")
    birthdays = db_all("SELECT name, roll_no, class_name, dob FROM students WHERE substr(dob, 6, 5) = %s", (today_date,))
    recent_payments = db_all("SELECT receipt_no, roll_no, amount, pay_date FROM payments ORDER BY id DESC LIMIT 5")
    recent_admissions = db_all("SELECT name, roll_no, class_name, admission_date FROM students ORDER BY id DESC LIMIT 5")

    # 7. Last 6 Months Trend
    monthly_trend = []
    for i in range(5, -1, -1):
        target_date = datetime.now() - timedelta(days=i*30)
        m_str = target_date.strftime("%Y-%m")
        coll = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date LIKE %s", (m_str + "%",))["t"]
        exp = one("SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE exp_date LIKE %s", (m_str + "%",))["t"]
        monthly_trend.append({"month": target_date.strftime("%b %Y"), "collection": coll, "expense": exp})

    # 8. 🤖 AI PRINCIPAL'S BRIEFING + PREDICTION + FORECAST
    ai_insight = "AI summary loading..."
    if ai_model:
        prompt = f"""
        Aap ek School ke Principal ke AI assistant aur Data Scientist hain. Niche diye gaye data ka analysis karke 3 hisso me jawab dijiye:
        
        PART 1 - DAILY BRIEFING: 2 lines ka sharp summary (Hinglish me).
        PART 2 - PREDICTIVE RISK: Top defaulters ko dekh kar predict kijiye ki agle mahine kaunse students default karne ke sabse zyada chance hain aur kyun.
        PART 3 - REVENUE FORECAST: Pichle 6 mahine ke collection trend {[m['collection'] for m in monthly_trend]} ko dekh kar agle mahine ka expected revenue predict kijiye (Rs me) aur 1 line ki advice dijiye.
        
        Data:
        - Aaj ka Collection: Rs {today_collection}
        - Lifetime Net Profit: Rs {lifetime_profit}
        - Total Pending Fees: Rs {total_due}
        - Top Defaulters: {[f"{d['name']} (Rs {d['total_balance']})" for d in top_defaulters]}
        """
        try:
            ai_insight = ai_model.generate_content(prompt).text
        except Exception as e:
            ai_insight = "AI Briefing abhi available nahi hai. API Key check karein."

    return render_template("dashboard.html",
        students=students_count, total_due=total_due,
        today_collection=today_collection, lifetime_profit=lifetime_profit,
        fee_status=fee_status, top_defaulters=top_defaulters,
        class_strength=class_strength, performers_list=performers_list,
        birthdays=birthdays, recent=recent_payments, recent_admissions=recent_admissions,
        monthly_trend=monthly_trend, ai_insight=ai_insight,
        monthly_target=monthly_target, progress_pct=progress_pct,
        current_collection=current_collection
       )
# ---------------- STUDENTS ----------------
# ==================== 🆕 ADVANCED STUDENT MODULES ====================

# 📅 1. Attendance System
@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    if request.method == "POST":
        att_date = request.form["att_date"]
        class_name = request.form["class_name"]
        
        # Delete old records for this date/class to prevent duplicates
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
                
        flash(f"✅ Attendance marked! Present: {present_count}, Absent: {absent_count}, Late: {late_count}", "success")
        return redirect(url_for("attendance", date=att_date, class_name=class_name))

    att_date = request.args.get("date", today())
    class_name = request.args.get("class_name", "")
    students = []
    if class_name:
        students = db_all("SELECT * FROM students WHERE class_name=%s ORDER BY roll_no", (class_name,))
    
    classes = db_all("SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL ORDER BY class_name")
    return render_template("attendance.html", students=students, classes=classes, att_date=att_date, class_name=class_name)

# 🏥 2. Save Health Record
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

# 📤 3. Bulk CSV Import
@app.route("/student/bulk-import", methods=["GET", "POST"])
@login_required
def bulk_import():
    if request.method == "POST":
        if 'file' not in request.files:
            flash("Koi file select nahi ki gayi!", "error")
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash("File select karein!", "error")
            return redirect(request.url)
            
        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)
            count = 0
            for row in csv_input:
                try:
                    run("""INSERT INTO students 
                        (roll_no,name,father,mother,class_name,section,gender,dob,contact,parent_contact,address,admission_date,transport_route,hostel)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (row['roll_no'], row['name'], row.get('father',''), row.get('mother',''), row.get('class_name',''),
                         row.get('section',''), row.get('gender',''), row.get('dob',''), row.get('contact',''),
                         row.get('parent_contact',''), row.get('address',''), row.get('admission_date',''), 
                         row.get('transport_route',''), row.get('hostel','')))
                    count += 1
                except Exception as e:
                    print(f"Error importing {row.get('name')}: {e}")
            flash(f"✅ {count} students successfully imported!", "success")
        else:
            flash("Sirf .csv file allowed hai!", "error")
        return redirect(url_for("students"))
    return render_template("bulk_import.html")

# 📜 4. Transfer Certificate (TC) Generator
@app.route("/student/tc/<int:sid>")
@login_required
def transfer_certificate(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    if not student: return redirect(url_for("students"))
    
    # Check if all dues are clear
    pending = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance > 0", (student['roll_no'],))["t"]
    
    return render_template("transfer_certificate.html", student=student, pending=pending)
@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "")
    class_filter = request.args.get("class_filter", "")
    fee_filter = request.args.get("fee_filter", "")
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    # Base query
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
        ORDER BY s.roll_no
        LIMIT %s OFFSET %s
    """
    params.extend([per_page, offset])
    rows = db_all(query, tuple(params))

    # Get total count for pagination
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

@app.route("/student/edit/<int:sid>", methods=["GET", "POST"])
@login_required
def edit_student(sid):
    if request.method == "POST":
        d = request.form
        run("""UPDATE students SET
            roll_no=%s, name=%s, father=%s, mother=%s, class_name=%s, section=%s,
            gender=%s, dob=%s, contact=%s, parent_contact=%s, address=%s,
            admission_date=%s, transport_route=%s, hostel=%s WHERE id=%s""",
            (d["roll_no"], d["name"], d["father"], d["mother"], d["class_name"],
             d["section"], d["gender"], d["dob"], d["contact"], d["parent_contact"],
             d["address"], d["admission_date"], d["transport_route"], d["hostel"], sid))
        flash("✅ Student updated!", "success")
        return redirect(url_for("students"))
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    return render_template("edit_student.html", student=student)

@app.route("/student/delete/<int:sid>")
@login_required
def delete_student(sid):
    run("DELETE FROM students WHERE id=%s", (sid,))
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students"))

# ==================== 🆕 ADVANCED STUDENT FEATURES ====================

# 👤 1. Student Profile (360 View)
@app.route("/student/profile/<int:sid>")
@login_required
def student_profile(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))
    
    # Fee History (Ledger)
    bills = db_all("SELECT * FROM bills WHERE roll_no=%s ORDER BY month DESC", (student['roll_no'],))
    payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY pay_date DESC", (student['roll_no'],))
    
    # Marks & Performance
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (student['roll_no'],))
    total_obtained = sum(float(m['marks'] or 0) for m in marks)
    total_max = sum(float(m['total'] or 0) for m in marks)
    percentage = (total_obtained / total_max * 100) if total_max > 0 else 0

    # Fee Summary
    total_billed = sum(b['total'] for b in bills)
    total_paid = sum(p['amount'] for p in payments)
    total_due = total_billed - total_paid

    return render_template("student_profile.html", student=student, bills=bills, 
                           payments=payments, marks=marks, total_obtained=total_obtained,
                           total_max=total_max, percentage=percentage, total_due=total_due)

# 🪪 2. ID Card Generator
@app.route("/student/id-card/<int:sid>")
@login_required
def student_id_card(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    return render_template("id_card.html", student=student)

# 📤 3. Export CSV (Already added earlier, keeping it here)
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
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=f"students_{datetime.now():%Y%m%d}.csv")

# 📢 4. Bulk WhatsApp Reminder API
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
                msg = f"Dear Parent, {student['name']} ki Rs {pending} fees pending hai. Kripya jaldi jama karein. - School Management"
                links.append(f"https://wa.me/{phone}?text={quote(msg)}")
    
    return jsonify({"links": links, "count": len(links)})
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
# ==================== 📊 ANALYTICS ====================
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
  # ==================== 🤖 AI ASSISTANT ====================
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
   # ==================== 🧠 ULTIMATE AI HUB ====================
# Ye section school ko "AI-First" banata hai. Har feature me Gemini AI use hota hai.

# 🎓 1. AI Career Counselor
@app.route("/ai/career-counselor/<int:sid>")
@login_required
def ai_career_counselor(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    if not student: return jsonify({"result": "Student not found."})
    
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (student['roll_no'],))
    if not marks: return jsonify({"result": "Is student ka academic data available nahi hai. Pehle marks add karein."})
    if not ai_model: return jsonify({"result": "AI offline hai. API Key check karein."})

    marks_str = ", ".join([f"{m['subject']}: {round((m['marks']/m['total'])*100 if m['total']>0 else 0)}%" for m in marks])
    prompt = f"""
    Aap ek expert Career Counselor hain (India ke context me). Student ka data:
    Name: {student['name']}, Class: {student['class_name']}, Marks: {marks_str}
    
    1. Iske marks ke hisaab se kaunse 3 career fields best hain (jaise Science, Commerce, Arts, Computer, Sports)?
    2. Har field ke liye 1-line kyun recommend kar rahe ho.
    3. Ek short 'Study Plan' bhi dijiye ki agle saal kaise padhe.
    
    Format: Hinglish me, 4-5 bullet points, positive aur professional tone.
    """
    try:
        return jsonify({"result": ai_model.generate_content(prompt).text})
    except Exception as e:
        return jsonify({"result": f"AI Error: {str(e)}"})


# 📝 2. AI Question Paper Generator
@app.route("/ai/generate-paper", methods=["POST"])
@login_required
def ai_generate_paper():
    data = request.get_json() or {}
    subject = data.get("subject", "General")
    class_name = data.get("class_name", "10")
    total_marks = data.get("total_marks", 50)
    
    if not ai_model: return jsonify({"result": "AI offline."})

    prompt = f"""
    Aap ek Senior Teacher hain. Class {class_name} ke liye '{subject}' ka exam paper banayein.
    Total Marks: {total_marks}
    
    Paper me ye sections hone chahiye:
    - Section A: 5 Very Short Answer (1 mark each)
    - Section B: 4 Short Answer (3 marks each)
    - Section C: 2 Long Answer (5 marks each)
    
    Questions CBSE/State Board pattern par based ho. Har question ke baad marks likhein.
    Format: Clean, readable, Hinglish me instructions.
    """
    try:
        return jsonify({"result": ai_model.generate_content(prompt).text})
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"})


# 🔮 3. AI Performance Predictor (Next Exam Marks)
@app.route("/ai/performance-predictor/<int:sid>")
@login_required
def ai_performance_predictor(sid):
    student = one("SELECT * FROM students WHERE id=%s", (sid,))
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (student['roll_no'],))
    if not student or not marks: return jsonify({"result": "Data missing."})
    if not ai_model: return jsonify({"result": "AI offline."})

    marks_str = ", ".join([f"{m['subject']}: {m['marks']}/{m['total']}" for m in marks])
    prompt = f"""
    Aap ek Data Analyst hain. Student: {student['name']}, Class: {student['class_name']}
    Current Marks: {marks_str}
    
    Ye bataiye:
    1. Agle exam me is student ka approximate total percentage kya hoga (prediction)?
    2. Kaunse subject me improvement ki sabse zyada sambhavna hai?
    3. Kaunse subject me risk hai (marks girne ka darr hai)?
    
    Format: 3 bullet points + ek predicted percentage. Hinglish me.
    """
    try:
        return jsonify({"result": ai_model.generate_content(prompt).text})
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"})


# 🚨 4. AI Dropout Risk Detector (Bulk Analysis)
@app.route("/ai/risk-analysis")
@login_required
def ai_risk_analysis():
    if not ai_model: return jsonify({"result": "AI offline."})

    # Gather data: Fee dues + Attendance + Marks
    students = db_all("SELECT id, name, roll_no, class_name FROM students LIMIT 20")
    risk_data = []
    for s in students:
        dues = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (s['roll_no'],))["t"]
        att_total = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (s['roll_no'],))["c"]
        att_present = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (s['roll_no'],))["c"]
        att_pct = round((att_present/att_total*100) if att_total > 0 else 100, 1)
        
        risk_data.append(f"- {s['name']} (Class {s['class_name']}): Dues=Rs{dues}, Attendance={att_pct}%")

    prompt = f"""
    Aap ek School Data Scientist hain. Niche students ka data hai. Aapko 'Dropout Risk' predict karna hai.
    Rule: Jis student ki fees zyada pending hai AUR attendance kam hai, wo HIGH RISK me aata hai.
    
    Data:
    {chr(10).join(risk_data)}
    
    Analysis dijiye (Hinglish me):
    - Top 3 High Risk Students (naam ke saath, kyun risk me hain)
    - Principal ke liye 2 actionable suggestions
    
    Format: Short aur sharp.
    """
    try:
        return jsonify({"result": ai_model.generate_content(prompt).text})
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"})


# 📜 5. AI Report Card Remark Generator (Bulk)
@app.route("/ai/bulk-remarks", methods=["POST"])
@login_required
def ai_bulk_remarks():
    data = request.get_json() or {}
    roll_nos = data.get("roll_nos", [])
    if not roll_nos or not ai_model: return jsonify({"result": "No data or AI offline."})

    results = []
    for roll in roll_nos[:5]: # Limit 5 for speed
        student = one("SELECT name, class_name FROM students WHERE roll_no=%s", (roll,))
        marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll,))
        if not student or not marks: continue
        
        total_o = sum(float(m['marks'] or 0) for m in marks)
        total_m = sum(float(m['total'] or 0) for m in marks)
        pct = round((total_o/total_m*100) if total_m > 0 else 0, 1)
        
        prompt = f"Student {student['name']} (Class {student['class_name']}) ne {pct}% score kiya. Report card ke liye 1 short professional remark (Hinglish, max 15 words) likhiye. Positive aur encouraging."
        try:
            remark = ai_model.generate_content(prompt).text.strip()
            results.append(f"**{student['name']}** ({pct}%): {remark}")
        except: pass
    
    return jsonify({"result": "\n\n".join(results) if results else "Koi data nahi mila."})


# 🗣️ 6. AI Smart Reply for WhatsApp (Parent Communication)
@app.route("/ai/smart-reply", methods=["POST"])
@login_required
def ai_smart_reply():
    data = request.get_json() or {}
    student_name = data.get("name", "Student")
    context = data.get("context", "fees pending")
    
    if not ai_model: return jsonify({"result": "AI offline."})
    
    prompt = f"""
    Aap ek school principal hain. Parent ko WhatsApp message likhna hai. 
    Student: {student_name}, Topic: {context}.
    
    Message aisa ho jo: polite, professional, aur Hinglish me ho. Max 3 lines.
    """
    try:
        return jsonify({"result": ai_model.generate_content(prompt).text})
    except Exception as e:
        return jsonify({"result": f"Error: {str(e)}"})
       @app.route("/ai-hub")
@login_required
def ai_hub():
    # Students ka dropdown banane ke liye
    students = db_all("SELECT id, name, roll_no FROM students ORDER BY name")
    options = "".join([f'<option value="{s["id"]}">{s["name"]} (Roll: {s["roll_no"]})</option>' for s in students])
    return render_template("ai_hub.html", students_options=options)
# ====================================================== 
# ======================================================
# ---------------- RUN ----------------
init_db()
