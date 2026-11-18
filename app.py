"""
Shayure Ayurveda - Doctor Appointment & Patient Management System
Backend Application
"""

import os
import io
import time
import threading
import sqlite3
from datetime import datetime, date

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    session,
    flash,
    send_file
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from dotenv import load_dotenv

# Try importing psycopg2
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    HAS_PSYCOPG2 = False

# ReportLab for Medical PDF Reports
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "shayure_ayurveda_secret_key_2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "shayure_ayurveda.db")


# ---------------------------------------------------------------------------
# Date & Time Utilities
# ---------------------------------------------------------------------------

def parse_dt(val):
    """Safely parse various datetime representations into a Python datetime object."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    if not val:
        return datetime.now()
    val_str = str(val).strip().replace("T", " ")
    if val_str.endswith("Z"):
        val_str = val_str[:-1].strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%d %b %Y %I:%M %p"
    ):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    return datetime.now()


def parse_appointment_time(val):
    """Normalize input appointment time string into standard 'YYYY-MM-DD HH:MM:SS' format."""
    if not val:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dt = parse_dt(val)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.template_filter("format_datetime")
def format_datetime_filter(val, fmt="%d %b %Y %I:%M %p"):
    if not val:
        return ""
    dt = parse_dt(val)
    return dt.strftime(fmt)


@app.template_filter("strftime")
def strftime_filter(val, fmt="%d %b %Y %I:%M %p"):
    if not val:
        return ""
    dt = parse_dt(val)
    return dt.strftime(fmt)


# ---------------------------------------------------------------------------
# Resilient Database Manager (PostgreSQL with SQLite Fallback)
# ---------------------------------------------------------------------------

class DatabaseManager:
    """
    Manages dual-engine database connectivity.
    Attempts PostgreSQL connection with a short timeout;
    falls back cleanly to SQLite (shayure_ayurveda.db) without hanging.
    """
    def __init__(self):
        self.use_postgres = False
        self.pg_conn = None
        self.sqlite_conn = None
        self.lock = threading.Lock()
        self.last_cursor = None
        self.connect()

    def connect(self):
        db_host = os.getenv("DB_HOST")
        db_name = os.getenv("DB_NAME")
        if HAS_PSYCOPG2 and db_host and db_name:
            print(f"Attempting PostgreSQL connection to {db_host}...")
            try:
                self.pg_conn = psycopg2.connect(
                    host=db_host,
                    database=db_name,
                    user=os.getenv("DB_USER"),
                    password=os.getenv("DB_PASSWORD"),
                    port=os.getenv("DB_PORT", "5432"),
                    sslmode=os.getenv("DB_SSLMODE", "require"),
                    connect_timeout=3
                )
                self.use_postgres = True
                print("Database connected: PostgreSQL ✅")
                return
            except Exception as e:
                print("PostgreSQL connection failed or timed out. Falling back to SQLite:", e)

        print(f"Database connected: SQLite fallback ({SQLITE_DB_PATH}) ✅")
        self.sqlite_conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)

        # Register TO_CHAR function for SQLite chart compatibility
        def sqlite_to_char(val, fmt):
            if not val:
                return ""
            dt = parse_dt(val)
            if fmt == "Mon":
                return dt.strftime("%b")
            elif fmt == "YYYY":
                return dt.strftime("%Y")
            elif fmt == "YYYY-MM":
                return dt.strftime("%Y-%m")
            return dt.strftime("%b")

        self.sqlite_conn.create_function("TO_CHAR", 2, sqlite_to_char)
        self.use_postgres = False

    def execute(self, sql, params=None):
        with self.lock:
            if self.use_postgres:
                cur = self.pg_conn.cursor()
                if params is not None:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                self.last_cursor = cur
                return cur
            else:
                adapted_sql = sql.replace("ILIKE", "LIKE").replace("%s", "?")
                cur = self.sqlite_conn.cursor()
                if params is not None:
                    cur.execute(adapted_sql, params)
                else:
                    cur.execute(adapted_sql)
                self.last_cursor = cur
                return cur

    def commit(self):
        with self.lock:
            if self.use_postgres:
                self.pg_conn.commit()
            else:
                self.sqlite_conn.commit()

    def rollback(self):
        with self.lock:
            if self.use_postgres and self.pg_conn:
                self.pg_conn.rollback()
            elif self.sqlite_conn:
                self.sqlite_conn.rollback()

    def fetchone(self):
        with self.lock:
            if self.last_cursor:
                return self.last_cursor.fetchone()
            return None

    def fetchall(self):
        with self.lock:
            if self.last_cursor:
                return self.last_cursor.fetchall()
            return []


class CursorProxy:
    """DB-API compliant Cursor proxy delegating to DatabaseManager."""
    def __init__(self, db_mgr):
        self.db = db_mgr

    def execute(self, sql, params=None):
        return self.db.execute(sql, params)

    def fetchone(self):
        return self.db.fetchone()

    def fetchall(self):
        return self.db.fetchall()

    @property
    def lastrowid(self):
        if self.db.last_cursor:
            return getattr(self.db.last_cursor, "lastrowid", None)
        return None

    @property
    def rowcount(self):
        if self.db.last_cursor:
            return getattr(self.db.last_cursor, "rowcount", -1)
        return -1


class ConnProxy:
    """DB-API compliant Connection proxy delegating to DatabaseManager."""
    def __init__(self, db_mgr):
        self.db = db_mgr

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def cursor(self):
        return CursorProxy(self.db)


# Global Database Instances
db_mgr = DatabaseManager()
conn = ConnProxy(db_mgr)
cursor = CursorProxy(db_mgr)


# ---------------------------------------------------------------------------
# Schema Initialization & Migrations
# ---------------------------------------------------------------------------

def init_db():
    """Ensure all required tables, columns, and default seeds exist in the database."""
    try:
        if db_mgr.use_postgres:
            # Users table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'patient',
                full_name TEXT,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

            # Patients table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                age INTEGER,
                gender TEXT,
                blood_group TEXT,
                emergency_contact TEXT,
                allergies TEXT,
                medical_history TEXT,
                dosha_type TEXT DEFAULT 'Tridoshic',
                address TEXT,
                notes TEXT,
                symptoms TEXT,
                created_by_doctor TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

            # Appointments table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                name TEXT,
                doctor TEXT,
                appointment_time TIMESTAMP,
                user_id INTEGER,
                status TEXT DEFAULT 'Pending',
                followup_date DATE,
                symptoms TEXT,
                prescription TEXT,
                doctor_notes TEXT,
                diagnosis TEXT,
                patient_id INTEGER,
                vitals TEXT,
                dietary_advice TEXT,
                phone TEXT,
                email TEXT,
                age INTEGER,
                gender TEXT,
                dosha TEXT,
                consultation_type TEXT DEFAULT 'In-Clinic',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

            # Add potential missing columns in PostgreSQL
            pg_cols = [
                ("appointments", "email", "TEXT"),
                ("appointments", "age", "INTEGER"),
                ("appointments", "gender", "TEXT"),
                ("appointments", "dosha", "TEXT"),
                ("appointments", "patient_id", "INTEGER"),
                ("appointments", "phone", "TEXT"),
                ("appointments", "doctor_notes", "TEXT"),
                ("appointments", "diagnosis", "TEXT"),
                ("patients", "symptoms", "TEXT"),
                ("users", "role", "TEXT DEFAULT 'patient'")
            ]
            for table, col, col_type in pg_cols:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}")
                    conn.commit()
                except Exception:
                    conn.rollback()

        else:
            # SQLite Tables
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'patient',
                full_name TEXT,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                age INTEGER,
                gender TEXT,
                blood_group TEXT,
                emergency_contact TEXT,
                allergies TEXT,
                medical_history TEXT,
                dosha_type TEXT DEFAULT 'Tridoshic',
                address TEXT,
                notes TEXT,
                symptoms TEXT,
                created_by_doctor TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                doctor TEXT,
                appointment_time TIMESTAMP,
                user_id INTEGER,
                status TEXT DEFAULT 'Pending',
                followup_date DATE,
                symptoms TEXT,
                prescription TEXT,
                doctor_notes TEXT,
                diagnosis TEXT,
                patient_id INTEGER,
                vitals TEXT,
                dietary_advice TEXT,
                phone TEXT,
                email TEXT,
                age INTEGER,
                gender TEXT,
                dosha TEXT,
                consultation_type TEXT DEFAULT 'In-Clinic',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

            # SQLite Column Migrations
            sqlite_tables = {
                "appointments": [
                    ("email", "TEXT"),
                    ("age", "INTEGER"),
                    ("gender", "TEXT"),
                    ("dosha", "TEXT"),
                    ("patient_id", "INTEGER"),
                    ("phone", "TEXT"),
                    ("doctor_notes", "TEXT"),
                    ("diagnosis", "TEXT"),
                    ("prescription", "TEXT"),
                    ("symptoms", "TEXT"),
                    ("followup_date", "DATE")
                ],
                "patients": [
                    ("symptoms", "TEXT"),
                    ("dosha_type", "TEXT DEFAULT 'Tridoshic'"),
                    ("created_by_doctor", "TEXT")
                ],
                "users": [
                    ("role", "TEXT DEFAULT 'patient'"),
                    ("full_name", "TEXT"),
                    ("email", "TEXT"),
                    ("phone", "TEXT")
                ]
            }

            for table, cols in sqlite_tables.items():
                cursor.execute(f"PRAGMA table_info({table})")
                existing = {row[1] for row in cursor.fetchall()}
                for col_name, col_type in cols:
                    if col_name not in existing:
                        try:
                            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                            conn.commit()
                        except Exception as e:
                            print(f"Notice adding column {col_name} to {table}: {e}")

        # Seed initial doctor and patient accounts if not present
        cursor.execute("SELECT id, username FROM users WHERE username = 'doctor'")
        doctor_user = cursor.fetchone()
        if not doctor_user:
            cursor.execute("""
                INSERT INTO users (username, password, role, full_name, email, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                "doctor",
                generate_password_hash("doctor123"),
                "doctor",
                "Dr. Shanmuga Loga",
                "doctor@ayurveda.com",
                "+91 98765 43210"
            ))
            conn.commit()

        cursor.execute("SELECT id, username FROM users WHERE username = 'patient'")
        patient_user = cursor.fetchone()
        if not patient_user:
            cursor.execute("""
                INSERT INTO users (username, password, role, full_name, email, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                "patient",
                generate_password_hash("patient123"),
                "patient",
                "Priya Patel",
                "priya@example.com",
                "+91 98765 12345"
            ))
            conn.commit()

        # Also seed admin@gmail.com as doctor
        cursor.execute("SELECT id, username FROM users WHERE username = 'admin@gmail.com'")
        admin_user = cursor.fetchone()
        if not admin_user:
            cursor.execute("""
                INSERT INTO users (username, password, role, full_name, email, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                "admin@gmail.com",
                generate_password_hash("doctor123"),
                "doctor",
                "Dr. Shanmuga Loga",
                "admin@gmail.com",
                "+91 98765 43210"
            ))
            conn.commit()

        print("Database schema verified & seeded successfully ✅")

    except Exception as e:
        print("Schema initialization warning:", e)


# Run schema initialization once on startup
init_db()


# ---------------------------------------------------------------------------
# Core Public & Authentication Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")
    if session.get("role") == "doctor":
        return redirect("/doctor")
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password_raw = request.form.get("password", "").strip()
        role = request.form.get("role", "patient").strip().lower()
        if role not in ("patient", "doctor"):
            role = "patient"

        if not username or not password_raw:
            flash("Username and password are required")
            return redirect("/signup")

        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing = cursor.fetchone()
        if existing:
            flash("Username is already taken. Please choose another.")
            return redirect("/signup")

        password = generate_password_hash(password_raw)
        full_name = request.form.get("full_name", username).strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        cursor.execute("""
            INSERT INTO users (username, password, role, full_name, email, phone)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, password, role, full_name, email, phone))
        conn.commit()

        flash("Account created successfully! Please sign in.")
        return redirect("/login")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Please enter both username and password")
            return redirect("/login")

        cursor.execute("""
            SELECT id, username, password, role
            FROM users
            WHERE username = %s OR email = %s
        """, (username, username))

        user = cursor.fetchone()

        if user and check_password_hash(user[2], password):
            session["user"] = user[1]
            session["user_id"] = user[0]
            session["role"] = user[3]

            if user[3] == "doctor":
                return redirect("/doctor")
            return redirect("/dashboard")

        flash("Invalid username or password")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect("/")


# ---------------------------------------------------------------------------
# Doctor Dashboard & Clinical Management
# ---------------------------------------------------------------------------

@app.route("/doctor")
def doctor_dashboard():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "doctor":
        return redirect("/dashboard")

    # Aggregate Metrics
    cursor.execute("SELECT COUNT(*) FROM appointments")
    row = cursor.fetchone()
    total = row[0] if row else 0

    cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'Pending'")
    row = cursor.fetchone()
    pending = row[0] if row else 0

    cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'Completed'")
    row = cursor.fetchone()
    completed = row[0] if row else 0

    # Today's appointments count
    try:
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE DATE(appointment_time) = CURRENT_DATE")
        row = cursor.fetchone()
        today_count = row[0] if row else 0
    except Exception:
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE appointment_time LIKE %s", (f"{today_str}%",))
        row = cursor.fetchone()
        today_count = row[0] if row else 0

    # Recent Appointments with proper datetime conversion for Jinja .strftime compatibility
    cursor.execute("""
        SELECT
            id,
            name,
            doctor,
            appointment_time,
            status,
            symptoms,
            doctor_notes,
            followup_date,
            phone,
            email,
            age,
            gender,
            dosha
        FROM appointments
        ORDER BY appointment_time DESC
    """)
    raw_appointments = cursor.fetchall() or []

    appointments = []
    for appt in raw_appointments:
        item = list(appt)
        item[3] = parse_dt(item[3])
        appointments.append(item)

    # Status Distribution Chart
    cursor.execute("""
        SELECT status, COUNT(*)
        FROM appointments
        GROUP BY status
    """)
    status_chart = cursor.fetchall() or []

    # Monthly Trends Chart
    monthly_chart = []
    try:
        cursor.execute("""
            SELECT
                TO_CHAR(appointment_time, 'Mon') AS month,
                COUNT(*)
            FROM appointments
            WHERE appointment_time IS NOT NULL AND appointment_time != ''
            GROUP BY month
            ORDER BY MIN(appointment_time)
        """)
        monthly_chart = cursor.fetchall() or []
    except Exception as e:
        print("Monthly chart query fallback:", e)

    # If query returned empty, compute directly from appointments
    if not monthly_chart:
        month_counts = {}
        for appt in appointments:
            m = appt[3].strftime("%b")
            month_counts[m] = month_counts.get(m, 0) + 1
        monthly_chart = list(month_counts.items())

    # Patient Roster
    try:
        cursor.execute("""
            SELECT id, name, phone, email, age, gender, dosha_type, symptoms, notes, created_at
            FROM patients
            ORDER BY id DESC
        """)
        patients = cursor.fetchall() or []
    except Exception:
        patients = []

    return render_template(
        "doctor_dashboard.html",
        total=total,
        pending=pending,
        completed=completed,
        today=today_count,
        appointments=appointments,
        status_chart=status_chart,
        monthly_chart=monthly_chart,
        patients=patients
    )


# ---------------------------------------------------------------------------
# Add Patient Feature & Doctor API Endpoints
# ---------------------------------------------------------------------------

def handle_add_patient():
    """Shared handler for adding a new patient from doctor dashboard or API."""
    is_api = (
        request.path.startswith("/api/")
        or request.is_json
        or request.headers.get("Accept") == "application/json"
    )

    if "user" not in session:
        if is_api:
            return jsonify({"error": "Unauthorized. Please log in."}), 401
        flash("Please log in to continue")
        return redirect("/login")

    if session.get("role") != "doctor":
        if is_api:
            return jsonify({"error": "Forbidden: Doctor access required."}), 403
        flash("Doctor access required")
        return redirect("/dashboard")

    data = request.get_json(silent=True) or request.form.to_dict() or {}

    name = (
        data.get("name")
        or data.get("patient_name")
        or data.get("full_name")
        or ""
    ).strip()

    if not name:
        if is_api:
            return jsonify({"error": "Patient name is required"}), 400
        flash("Patient name is required")
        return redirect("/doctor")

    phone = (
        data.get("phone")
        or data.get("phone_number")
        or data.get("whatsapp")
        or ""
    ).strip()
    email = (data.get("email") or "").strip()

    age_raw = data.get("age")
    try:
        age = int(age_raw) if age_raw is not None and str(age_raw).strip() != "" else None
    except (ValueError, TypeError):
        age = None

    gender = (data.get("gender") or "Other").strip()
    dosha = (
        data.get("dosha")
        or data.get("constitution")
        or data.get("dosha_type")
        or data.get("prakriti")
        or "Tridoshic"
    ).strip()

    symptoms = (
        data.get("symptoms")
        or data.get("chief_complaint")
        or ""
    ).strip()
    doctor_notes = (
        data.get("doctor_notes")
        or data.get("notes")
        or ""
    ).strip()

    status = (data.get("status") or "Confirmed").strip()
    if status not in ("Pending", "Confirmed", "Completed", "Cancelled"):
        status = "Confirmed"

    raw_time = (
        data.get("appointment_time")
        or data.get("appointment_date")
        or data.get("date_time")
    )
    appt_time = parse_appointment_time(raw_time)

    doctor_name = (
        data.get("doctor")
        or session.get("user")
        or "Dr. Shanmuga Loga"
    ).strip()
    if not doctor_name.startswith("Dr.") and not doctor_name.startswith("dr."):
        doctor_name = f"Dr. {doctor_name}"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Insert into patients table
    if db_mgr.use_postgres:
        cursor.execute("""
            INSERT INTO patients (
                name, phone, email, age, gender, dosha_type, symptoms, medical_history, notes, created_by_doctor, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, phone, email, age, gender, dosha, symptoms, symptoms, doctor_notes, doctor_name, now_str))
        row = cursor.fetchone()
        patient_id = row[0] if row else None
    else:
        cursor.execute("""
            INSERT INTO patients (
                name, phone, email, age, gender, dosha_type, symptoms, medical_history, notes, created_by_doctor, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, phone, email, age, gender, dosha, symptoms, symptoms, doctor_notes, doctor_name, now_str))
        patient_id = cursor.lastrowid

    # 2. Insert corresponding appointment into appointments table
    if db_mgr.use_postgres:
        cursor.execute("""
            INSERT INTO appointments (
                name, doctor, appointment_time, user_id, status, symptoms, doctor_notes, patient_id, phone, email, age, gender, dosha, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, doctor_name, appt_time, session.get("user_id"), status, symptoms, doctor_notes, patient_id, phone, email, age, gender, dosha, now_str))
        row = cursor.fetchone()
        appointment_id = row[0] if row else None
    else:
        cursor.execute("""
            INSERT INTO appointments (
                name, doctor, appointment_time, user_id, status, symptoms, doctor_notes, patient_id, phone, email, age, gender, dosha, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, doctor_name, appt_time, session.get("user_id"), status, symptoms, doctor_notes, patient_id, phone, email, age, gender, dosha, now_str))
        appointment_id = cursor.lastrowid

    conn.commit()

    payload = {
        "success": True,
        "message": f"Patient '{name}' added successfully",
        "patient": {
            "id": patient_id,
            "name": name,
            "phone": phone,
            "email": email,
            "age": age,
            "gender": gender,
            "dosha": dosha,
            "symptoms": symptoms,
            "doctor_notes": doctor_notes
        },
        "appointment": {
            "id": appointment_id,
            "name": name,
            "doctor": doctor_name,
            "appointment_time": appt_time,
            "status": status,
            "symptoms": symptoms,
            "phone": phone,
            "dosha": dosha
        }
    }

    if is_api:
        return jsonify(payload), 201

    flash(f"Patient '{name}' added successfully!")
    return redirect("/doctor")


@app.route("/doctor/add-patient", methods=["GET", "POST"])
def doctor_add_patient():
    if request.method == "GET":
        return redirect("/doctor")
    return handle_add_patient()


@app.route("/api/doctor/patients", methods=["GET", "POST"])
def api_doctor_patients():
    if request.method == "POST":
        return handle_add_patient()

    # GET: return patient list
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if session.get("role") != "doctor":
        return jsonify({"error": "Forbidden: Doctor role required"}), 403

    cursor.execute("""
        SELECT id, name, phone, email, age, gender, dosha_type, symptoms, notes, created_by_doctor, created_at
        FROM patients
        ORDER BY id DESC
    """)
    rows = cursor.fetchall() or []
    patients = []
    for r in rows:
        patients.append({
            "id": r[0],
            "name": r[1],
            "phone": r[2] or "",
            "email": r[3] or "",
            "age": r[4],
            "gender": r[5] or "",
            "dosha": r[6] or "",
            "symptoms": r[7] or "",
            "doctor_notes": r[8] or "",
            "created_by_doctor": r[9] or "",
            "created_at": str(r[10]) if len(r) > 10 and r[10] else ""
        })

    return jsonify({
        "success": True,
        "count": len(patients),
        "patients": patients
    })


# ---------------------------------------------------------------------------
# Patient Appointments REST API
# ---------------------------------------------------------------------------

@app.route("/appointments", methods=["POST"])
def add_appointment():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = data.get("name", "").strip()
    doctor = data.get("doctor", "Dr. Shanmuga Loga").strip()
    appt_time_raw = data.get("appointment_time")
    appt_time = parse_appointment_time(appt_time_raw)
    symptoms = data.get("symptoms", "").strip()
    status = data.get("status", "Pending")

    if not name:
        return jsonify({"error": "Name is required"}), 400

    cursor.execute("""
        INSERT INTO appointments (
            name, doctor, appointment_time, user_id, symptoms, status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, doctor, appt_time, session.get("user_id"), symptoms, status))
    conn.commit()

    return jsonify({"message": "Appointment added", "success": True}), 201


@app.route("/appointments", methods=["GET"])
def get_appointments():
    if "user" not in session:
        return jsonify([]), 401

    search = request.args.get("search", "")
    search_pattern = f"%{search}%"

    if session.get("role") == "doctor":
        cursor.execute("""
            SELECT id, name, doctor, appointment_time, user_id, status, followup_date, symptoms, prescription, doctor_notes, diagnosis, phone, email, age, gender, dosha
            FROM appointments
            WHERE doctor ILIKE %s OR name ILIKE %s
            ORDER BY appointment_time DESC
        """, (search_pattern, search_pattern))
    else:
        cursor.execute("""
            SELECT id, name, doctor, appointment_time, user_id, status, followup_date, symptoms, prescription, doctor_notes, diagnosis, phone, email, age, gender, dosha
            FROM appointments
            WHERE user_id = %s
            AND (doctor ILIKE %s OR name ILIKE %s)
            ORDER BY appointment_time
        """, (session["user_id"], search_pattern, search_pattern))

    rows = cursor.fetchall() or []
    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "name": row[1],
            "doctor": row[2],
            "appointment_time": str(row[3]) if row[3] else "",
            "user_id": row[4],
            "status": row[5],
            "followup_date": str(row[6]) if row[6] else "",
            "symptoms": row[7] if len(row) > 7 and row[7] else "",
            "phone": row[11] if len(row) > 11 and row[11] else "",
            "email": row[12] if len(row) > 12 and row[12] else "",
            "age": row[13] if len(row) > 13 else None,
            "gender": row[14] if len(row) > 14 and row[14] else "",
            "dosha": row[15] if len(row) > 15 and row[15] else ""
        })

    return jsonify(result)


@app.route("/appointments/<int:id>", methods=["PUT"])
def update_appointment(id):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    name = data.get("name")
    doctor = data.get("doctor")
    appt_time = parse_appointment_time(data.get("appointment_time"))

    cursor.execute("""
        UPDATE appointments
        SET name = %s,
            doctor = %s,
            appointment_time = %s
        WHERE id = %s
    """, (name, doctor, appt_time, id))
    conn.commit()

    return jsonify({"message": "Appointment updated", "success": True})


@app.route("/appointments/<int:id>", methods=["DELETE"])
def delete_appointment(id):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if session.get("role") == "doctor":
        cursor.execute("DELETE FROM appointments WHERE id = %s", (id,))
    else:
        cursor.execute("DELETE FROM appointments WHERE id = %s AND user_id = %s", (id, session.get("user_id")))
    conn.commit()

    return jsonify({"message": "Deleted", "success": True})


@app.route("/appointments/<int:id>/status", methods=["PUT", "POST"])
def update_status(id):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    status = data.get("status")
    if not status:
        return jsonify({"error": "Status is required"}), 400

    cursor.execute("UPDATE appointments SET status = %s WHERE id = %s", (status, id))
    conn.commit()

    return jsonify({"message": "Status updated", "success": True, "status": status})


# ---------------------------------------------------------------------------
# Clinical Consultation & Medical Reports
# ---------------------------------------------------------------------------

@app.route("/consultation/<int:id>", methods=["GET", "POST"])
def consultation(id):
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "doctor":
        flash("Doctor access required")
        return redirect("/dashboard")

    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        diagnosis = data.get("diagnosis", "").strip()
        prescription = data.get("prescription", "").strip()
        doctor_notes = data.get("doctor_notes", "").strip()
        followup_date = data.get("followup_date") or None
        status = data.get("status", "Completed").strip()

        cursor.execute("""
            UPDATE appointments
            SET
                diagnosis = %s,
                prescription = %s,
                doctor_notes = %s,
                followup_date = %s,
                status = %s
            WHERE id = %s
        """, (diagnosis, prescription, doctor_notes, followup_date, status, id))
        conn.commit()

        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"success": True, "message": "Consultation saved successfully!"})

        flash("Consultation saved successfully!")
        return redirect("/doctor")

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (id,))
    appointment = cursor.fetchone()

    if not appointment:
        flash("Appointment not found")
        return redirect("/doctor")

    return render_template("consultation.html", appointment=appointment)


@app.route("/report/<int:id>")
def patient_report(id):
    if "user" not in session:
        return redirect("/login")

    is_doctor = session.get("role") == "doctor"
    if is_doctor:
        cursor.execute("SELECT * FROM appointments WHERE id = %s", (id,))
    else:
        cursor.execute("SELECT * FROM appointments WHERE id = %s AND user_id = %s", (id, session["user_id"]))

    appointment = cursor.fetchone()
    if not appointment:
        flash("Appointment not found or unauthorized access")
        return redirect("/doctor" if is_doctor else "/dashboard")

    return render_template("patient_report.html", appointment=appointment)


@app.route("/report/<int:id>/pdf")
def download_pdf(id):
    if "user" not in session:
        return redirect("/login")

    is_doctor = session.get("role") == "doctor"
    if is_doctor:
        cursor.execute("SELECT * FROM appointments WHERE id = %s", (id,))
    else:
        cursor.execute("SELECT * FROM appointments WHERE id = %s AND user_id = %s", (id, session["user_id"]))

    appointment = cursor.fetchone()
    if not appointment:
        return "Appointment not found", 404

    clean_patient_name = "".join(
        c for c in str(appointment[1] or "Patient") if c.isalnum() or c in (" ", "_", "-")
    ).strip().replace(" ", "_")
    filename = f"Medical_Report_{clean_patient_name}_{appointment[0]}.pdf"

    styles = getSampleStyleSheet()
    title = styles["Title"]
    title.alignment = 1
    title.textColor = colors.HexColor("#1b4332")

    heading = styles["Heading2"]
    heading.textColor = colors.HexColor("#2d6a4f")

    body = styles["BodyText"]
    generated_time = datetime.now().strftime("%d %b %Y %I:%M %p")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    story = [
        Paragraph("<font size='24'><b>🌿 SHAYURE AYURVEDA</b></font>", title),
        Paragraph("<font size='14'>Clinical Consultation & Health Assessment Report</font>", title),
        Spacer(1, 15),
        Paragraph(f"<b>Report Reference:</b> #{appointment[0]}", body),
        Paragraph(f"<b>Generated On:</b> {generated_time}", body),
        Spacer(1, 15),
        Paragraph("<b>Patient Demographics & Appointment</b>", heading),
        Spacer(1, 8)
    ]

    patient_data = [
        ["Patient Name", str(appointment[1] or "-")],
        ["Consulting Doctor", str(appointment[2] or "-")],
        ["Appointment Time", str(appointment[3] or "-")],
        ["Status", str(appointment[5] or "-")]
    ]

    patient_table = Table(patient_data, colWidths=[160, 320])
    patient_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#d8f3dc")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))
    story.append(patient_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Ayurvedic Clinical Assessment</b>", heading))
    story.append(Spacer(1, 8))

    symptoms_text = str(appointment[7]) if len(appointment) > 7 and appointment[7] else "-"
    diag_text = str(appointment[10]) if len(appointment) > 10 and appointment[10] else "-"
    rx_text = str(appointment[8]) if len(appointment) > 8 and appointment[8] else "-"
    notes_text = str(appointment[9]) if len(appointment) > 9 and appointment[9] else "-"
    followup_text = str(appointment[6]) if len(appointment) > 6 and appointment[6] else "-"

    clinical_data = [
        ["Symptoms / Chief Complaint", symptoms_text],
        ["Ayurvedic Diagnosis", diag_text],
        ["Prescription (Aushadha)", rx_text],
        ["Clinical & Lifestyle Notes", notes_text],
        ["Recommended Follow-up", followup_text]
    ]

    clinical_table = Table(clinical_data, colWidths=[160, 320])
    clinical_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fef3c7")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))
    story.append(clinical_table)
    story.append(Spacer(1, 30))

    story.append(Paragraph("________________________________________", body))
    story.append(Paragraph("<b>Authorized Doctor Signature & Stamp</b>", body))
    story.append(Spacer(1, 20))
    story.append(Paragraph("<font color='grey'>Generated by Shayure Ayurveda Healthcare Portal</font>", body))
    story.append(Paragraph("<font color='grey'>Wishing you vibrant health and holistic wellness 🌿</font>", body))

    doc.build(story)
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )


# ---------------------------------------------------------------------------
# Server Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
