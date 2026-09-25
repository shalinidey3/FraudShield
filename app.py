import io
import importlib
import importlib.util
import os
import smtplib
import sqlite3
import threading
import traceback
import hashlib
import hmac
import binascii
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo


def load_dotenv(dotenv_path):
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "EMAIL_PASSWORD":
                normalized_password = value.replace(" ", "")
                if normalized_password.isalnum():
                    value = normalized_password
            if key and os.getenv(key) is None:
                os.environ[key] = value

from decimal import Decimal, InvalidOperation
from functools import wraps
from email.message import EmailMessage

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file,
)
import logging
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import joblib

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fraud-detection-secret-key")
try:
    APP_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    APP_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True

# Setup file logging for requests and errors
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(BASE_DIR, "server.log")
file_handler = logging.FileHandler(log_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
if not app.logger.handlers:
    app.logger.addHandler(file_handler)
else:
    # ensure file handler is added
    app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# Ensure log files exist
for _fname in ("server.log", "error.log"):
    try:
        open(os.path.join(BASE_DIR, _fname), "a", encoding="utf-8").close()
    except Exception:
        pass

@app.before_request
def log_request_info():
    try:
        app.logger.info(f"REQUEST {request.method} {request.path} from {request.remote_addr} data={dict(request.values)}")
    except Exception:
        app.logger.exception("Failed to log request info")

from flask import got_request_exception

def log_exception(sender, exception, **extra):
    try:
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    except Exception:
        tb = str(exception)
    try:
        with open(os.path.join(BASE_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - Exception on {request.path}\n{tb}\n")
    except Exception:
        pass
    app.logger.error(f"Exception on {request.path}: {tb}")

got_request_exception.connect(log_exception, app)

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DB_PATH = os.path.join(BASE_DIR, "database", "fraud.db")
MODEL_PATH = os.path.join(BASE_DIR, "models", "model.pkl")
ENCODER_PATH = os.path.join(BASE_DIR, "models", "merchant_encoder.pkl")

os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)

model = joblib.load(MODEL_PATH)
encoder = joblib.load(ENCODER_PATH)
MERCHANT_CATEGORIES = list(getattr(encoder, "classes_", []))
FEATURE_NAMES = [
    "Transaction Amount",
    "Transaction Hour",
    "Merchant Category",
    "Country Risk",
    "Card Present",
    "Online Transaction",
    "Failed PIN Attempts",
    "Transactions Last Hour",
    "Account Age Days",
]

EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip() or None
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587").strip() or "587")
EMAIL_USER = os.getenv("EMAIL_USER", "").strip() or None
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "").strip() or None
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip() or EMAIL_USER


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_columns(table_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cur.fetchall()}
    conn.close()
    return columns


def add_column_if_missing(cur, table_name, column_sql):
    column_name = column_sql.split()[0]
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in existing:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def get_now():
    return datetime.now(APP_TIMEZONE)


def get_today_date():
    return get_now().date().isoformat()


def get_timezone_sql_offset():
    offset = APP_TIMEZONE.utcoffset(get_now()) or timedelta(0)
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def to_local_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(APP_TIMEZONE)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=APP_TIMEZONE)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(APP_TIMEZONE)
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                if fmt == "%Y-%m-%d":
                    parsed = datetime(parsed.year, parsed.month, parsed.day, tzinfo=APP_TIMEZONE)
                else:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(APP_TIMEZONE)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(APP_TIMEZONE)
        except Exception:
            return None
    return None


def get_datetime_column(table_name, preferred="created_at", fallback="timestamp"):
    columns = get_columns(table_name)
    if preferred in columns and fallback in columns:
        return f"COALESCE({preferred}, {fallback})"
    if preferred in columns:
        return preferred
    if fallback in columns:
        return fallback
    return preferred


def get_row_timestamp(row, table_name="transactions"):
    if "display_date" in row.keys() and row["display_date"]:
        return row["display_date"]
    if "created_at" in row.keys() and row["created_at"]:
        return row["created_at"]
    if "timestamp" in row.keys() and row["timestamp"]:
        return row["timestamp"]
    if "updated_at" in row.keys() and row["updated_at"]:
        return row["updated_at"]
    if "created_at" in row.keys():
        return row["created_at"]
    if "timestamp" in row.keys():
        return row["timestamp"]
    if "updated_at" in row.keys():
        return row["updated_at"]
    return None


def format_timestamp(value):
    if not value:
        return None
    parsed = to_local_datetime(value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalize_timestamp_rows(rows):
    normalized = []
    for row in rows:
        data = dict(row)
        ts = get_row_timestamp(data)
        formatted = format_timestamp(ts) if ts else "N/A"
        data["display_date"] = formatted[:10] if formatted != "N/A" and len(formatted) >= 10 else formatted
        normalized.append(data)
    return normalized


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            card_number TEXT NOT NULL,
            account_number TEXT NOT NULL,
            balance REAL NOT NULL,
            daily_limit INTEGER NOT NULL,
            max_transaction_amount REAL NOT NULL,
            transaction_count_today INTEGER DEFAULT 0,
            last_transaction_date TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_hour INTEGER NOT NULL,
            transaction_place TEXT NOT NULL,
            transactions_last_hour INTEGER NOT NULL,
            failed_pin_attempts INTEGER NOT NULL,
            account_age_days INTEGER NOT NULL,
            merchant_category TEXT NOT NULL,
            country_risk INTEGER NOT NULL,
            card_present INTEGER NOT NULL,
            online_transaction INTEGER NOT NULL,
            risk_score REAL NOT NULL,
            fraud_probability REAL NOT NULL,
            prediction TEXT NOT NULL,
            status TEXT NOT NULL,
            rule_reason TEXT,
            balance_after REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            transaction_id INTEGER,
            alert_level TEXT NOT NULL,
            message TEXT NOT NULL,
            reason TEXT,
            status TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute("DROP TABLE IF EXISTS otp_logs")

    add_column_if_missing(cur, "users", "balance REAL DEFAULT 0")
    add_column_if_missing(cur, "users", "daily_limit INTEGER DEFAULT 5")
    add_column_if_missing(cur, "users", "max_transaction_amount REAL DEFAULT 20000")
    add_column_if_missing(cur, "users", "transaction_count_today INTEGER DEFAULT 0")
    add_column_if_missing(cur, "users", "last_transaction_date TEXT")
    add_column_if_missing(cur, "users", "otp_preference INTEGER DEFAULT 0")
    cur.execute("UPDATE users SET otp_preference = 0 WHERE otp_preference IS NULL")

    add_column_if_missing(cur, "transactions", "user_id INTEGER")
    add_column_if_missing(cur, "transactions", "transaction_hour INTEGER DEFAULT 0")
    add_column_if_missing(cur, "transactions", "transaction_place TEXT DEFAULT 'Unknown'")
    add_column_if_missing(cur, "transactions", "transactions_last_hour INTEGER DEFAULT 0")
    add_column_if_missing(cur, "transactions", "failed_pin_attempts INTEGER DEFAULT 0")
    add_column_if_missing(cur, "transactions", "account_age_days INTEGER DEFAULT 0")
    add_column_if_missing(cur, "transactions", "merchant_category TEXT DEFAULT 'Unknown'")
    add_column_if_missing(cur, "transactions", "country_risk INTEGER DEFAULT 0")
    add_column_if_missing(cur, "transactions", "card_present INTEGER DEFAULT 1")
    add_column_if_missing(cur, "transactions", "online_transaction INTEGER DEFAULT 1")
    add_column_if_missing(cur, "transactions", "status TEXT DEFAULT 'APPROVED'")
    add_column_if_missing(cur, "transactions", "rule_reason TEXT")
    add_column_if_missing(cur, "transactions", "balance_after REAL")
    add_column_if_missing(cur, "transactions", "created_at DATETIME")
    add_column_if_missing(cur, "transactions", "updated_at DATETIME")
    add_column_if_missing(cur, "transactions", "timestamp DATETIME")

    add_column_if_missing(cur, "alerts", "user_id INTEGER")
    add_column_if_missing(cur, "alerts", "reason TEXT")
    add_column_if_missing(cur, "alerts", "status TEXT DEFAULT 'OPEN'")

    conn.commit()
    conn.close()


init_db()


def hash_password(password):
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return f"{salt.hex()}${binascii.hexlify(key).decode()}"


def verify_password(password, stored_hash):
    try:
        salt, stored_key = stored_hash.split("$")
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100000)
        return hmac.compare_digest(stored_key, binascii.hexlify(key).decode())
    except Exception:
        return False


def _send_email(subject, body, recipient):
    recipient = recipient.strip() if recipient else None
    if not EMAIL_HOST or not EMAIL_USER or not EMAIL_PASSWORD or not recipient:
        msg = "Email not sent: SMTP configuration is incomplete."
        print(msg)
        return False, msg

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = EMAIL_FROM or EMAIL_USER
    message["To"] = recipient
    message.set_content(body)

    password = EMAIL_PASSWORD
    if EMAIL_HOST == "smtp.gmail.com" and " " in password and password.replace(" ", "").isalnum():
        password = password.replace(" ", "")

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_USER, password)
            server.send_message(message)
        msg = f"Email sent to {recipient}: {subject}"
        print(msg)
        return True, None
    except Exception as exc:
        msg = f"Failed to send email: {exc}"
        print(msg)
        return False, str(exc)


def smtp_configured():
    return bool(EMAIL_HOST and EMAIL_USER and EMAIL_PASSWORD and EMAIL_FROM)


def send_email(subject, body, recipient):
    if not smtp_configured() or not recipient:
        msg = "Email not sent: SMTP configuration is incomplete."
        print(msg)
        return False, msg
    return _send_email(subject, body, recipient)


def build_blocked_transaction_email(user, amount, transaction_time, risk_score, reason):
    return (
        f"Hello {user['full_name']},\n\n"
        f"Your transaction has been blocked.\n\n"
        f"User Name: {user['full_name']}\n"
        f"Account Number: {user['account_number']}\n"
        f"Transaction Amount: ₹{amount}\n"
        f"Transaction Time: {transaction_time}\n"
        f"Risk Score: {risk_score}%\n"
        f"Reason for blocking: {reason}\n\n"

    )


def require_login(route_function):
    @wraps(route_function)
    def wrapped_route(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return route_function(*args, **kwargs)

    return wrapped_route


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def get_user_by_id(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return dict(user) if user is not None else None


def get_user_by_email(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()
    return dict(user) if user is not None else None


def normalize_user(user):
    if isinstance(user, sqlite3.Row):
        return dict(user)
    return user


def get_today_transaction_count(user_id):
    today = get_today_date()
    conn = get_db_connection()
    cur = conn.cursor()
    date_col = get_datetime_column("transactions")
    offset = get_timezone_sql_offset()
    cur.execute(
        f"SELECT COUNT(*) FROM transactions WHERE user_id = ? AND date(datetime({date_col}, '{offset}')) = ?",
        (user_id, today),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_pin_uses_today(user):
    user = normalize_user(user)
    if not user:
        return 0
    today = get_today_date()
    count = get_today_transaction_count(user["id"])
    if count > 0:
        return count
    if user.get("last_transaction_date") == today:
        return int(user.get("transaction_count_today") or 0)
    return 0


def increment_analysis_clicks(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return
    today = get_today_date()
    count_today = int(user.get("transaction_count_today") or 0)
    if user.get("last_transaction_date") != today:
        count_today = 0
    count_today += 1
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET transaction_count_today = ?, last_transaction_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (count_today, today, user_id),
    )
    conn.commit()
    conn.close()


def create_alert(user_id, transaction_id, alert_level, message, reason, status):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alerts(user_id, transaction_id, alert_level, message, reason, status) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, transaction_id, alert_level, message, reason, status),
    )
    conn.commit()
    conn.close()


def explain_transaction(features, user, transaction_data):
    explanations = []

    try:
        shap_spec = importlib.util.find_spec("shap")
        if shap_spec is not None:
            shap = importlib.import_module("shap")
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values([features])
            contributions = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
            impact = sorted(
                zip(FEATURE_NAMES, contributions), key=lambda item: abs(item[1]), reverse=True
            )
            for feature_name, contribution in impact[:4]:
                sign = "increases" if contribution > 0 else "decreases"
                explanations.append(f"{feature_name} {sign} risk by {abs(round(contribution, 2))}")
            if explanations:
                return explanations
    except Exception:
        pass

    amount = transaction_data["amount"]
    try:
        user_balance = float(user.get("balance") or 0)
    except Exception:
        try:
            user_balance = float(str(user.get("balance") or 0))
        except Exception:
            user_balance = 0.0
    if amount >= user_balance * 0.8:
        explanations.append("High Amount compared to available balance")
    if transaction_data["transaction_hour"] >= 22 or transaction_data["transaction_hour"] < 5:
        explanations.append("Late night transaction hour")
    if transaction_data["failed_pin_attempts"] > 3:
        explanations.append("Multiple failed PIN attempts")
    if transaction_data["transactions_last_hour"] >= 4:
        explanations.append("Multiple transactions in the last hour")
    try:
        user_max_tx = float(user.get("max_transaction_amount") or 0)
    except Exception:
        try:
            user_max_tx = float(str(user.get("max_transaction_amount") or 0))
        except Exception:
            user_max_tx = 0.0
    if transaction_data["amount"] > user_max_tx:
        explanations.append("Amount exceeds user maximum transaction limit")
    if transaction_data["country_risk"] == 1:
        explanations.append("Transaction from a high-risk country")
    if not explanations:
        explanations.append("Transaction is within normal behavior patterns")
    return explanations[:4]


def build_report_query(user_id, args):
    date_col = get_datetime_column("transactions")
    offset = get_timezone_sql_offset()
    local_date_expr = f"date(datetime({date_col}, '{offset}'))"
    query = "SELECT *, COALESCE(created_at, timestamp, updated_at) AS display_date FROM transactions WHERE user_id = ?"
    params = [user_id]

    start_date = args.get("start_date")
    end_date = args.get("end_date")
    status = args.get("status")
    risk_level = args.get("risk_level")

    if start_date:
        query += f" AND {local_date_expr} >= ?"
        params.append(start_date)
    if end_date:
        query += f" AND {local_date_expr} <= ?"
        params.append(end_date)
    if status:
        query += " AND status = ?"
        params.append(status)
    if risk_level == "SAFE":
        query += " AND risk_score < 40"
    elif risk_level == "MEDIUM":
        query += " AND risk_score >= 40 AND risk_score < 80"
    elif risk_level == "HIGH":
        query += " AND risk_score >= 80"

    date_col = get_datetime_column("transactions")
    query += f" ORDER BY {date_col} DESC"
    return query, params


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("transaction"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        bank_name = request.form.get("bank_name", "").strip()
        card_number = request.form.get("card_number", "").strip()
        account_number = request.form.get("account_number", "").strip()
        initial_balance = request.form.get("initial_balance", "0").strip()
        daily_limit = request.form.get("daily_limit", "0").strip()
        max_transaction_amount = request.form.get("max_transaction_amount", "0").strip()

        if not all([full_name, email, phone, password, confirm_password, bank_name, card_number, account_number, initial_balance, daily_limit, max_transaction_amount]):
            flash("Please fill in all registration fields.")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.")
            return render_template("register.html")

        if get_user_by_email(email):
            flash("An account with this email already exists.")
            return render_template("register.html")

        password_hash = hash_password(password)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(full_name, email, phone, password_hash, bank_name, card_number, account_number, balance, daily_limit, max_transaction_amount, transaction_count_today, last_transaction_date, otp_preference) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                full_name,
                email,
                phone,
                password_hash,
                bank_name,
                card_number,
                account_number,
                float(initial_balance),
                int(daily_limit),
                float(max_transaction_amount),
                0,
                get_today_date(),
                0,
            ),
        )
        conn.commit()
        conn.close()

        flash("Registration successful. Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if user and verify_password(password, user["password_hash"]):
            session.clear()
            session["user_id"] = user["id"]
            flash("Successfully logged in.")
            return redirect(url_for("transaction"))

        flash("Invalid email or password.")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


@app.route("/transaction", methods=["GET", "POST"])
@require_login
def transaction():
    user = current_user()
    transactions_today = get_pin_uses_today(user)
    # Count of actual transactions performed today (clamped to the user's daily limit)
    used_today = min(get_today_transaction_count(user["id"]), int(user.get("daily_limit") or 0))
    result = None
    explanation = []
    if request.method == "POST":
        if transactions_today >= user["daily_limit"]:
            flash("Daily transaction analysis limit reached. Please try again tomorrow.")
            return render_template(
                "index.html",
                user=user,
                transactions_today=transactions_today,
                used_today=used_today,
                merchant_categories=MERCHANT_CATEGORIES,
                result=result,
            )
        increment_analysis_clicks(user["id"])
        user = get_user_by_id(user["id"])
        transactions_today = get_pin_uses_today(user)
        used_today = min(get_today_transaction_count(user["id"]), int(user.get("daily_limit") or 0))
        try:
            try:
                amount = float(request.form.get("transaction_amount", "0"))
                transaction_hour = int(request.form.get("transaction_hour", "0"))
                if transaction_hour < 0 or transaction_hour > 23:
                    raise ValueError("Transaction hour must be between 0 and 23.")
                transaction_place = request.form.get("transaction_place", "Unknown").strip()
                transactions_last_hour = int(request.form.get("transactions_last_hour", "0"))
                failed_pin_attempts = int(request.form.get("failed_pin_attempts", "0"))
                account_age_days = int(request.form.get("account_age_days", "0"))
                merchant_category = request.form.get("merchant_category", MERCHANT_CATEGORIES[0])
                country_risk = int(request.form.get("country_risk", "0"))
                card_present = int(request.form.get("card_present", "1"))
                online_transaction = int(request.form.get("online_transaction", "1"))
            except ValueError:
                flash("Invalid transaction values. Please use numeric fields correctly.")
                return render_template(
                    "index.html",
                    user=user,
                    transactions_today=transactions_today,
                    used_today=used_today,
                    merchant_categories=MERCHANT_CATEGORIES,
                )

            if not MERCHANT_CATEGORIES:
                merchant_category = "Unknown"
            elif merchant_category not in MERCHANT_CATEGORIES:
                merchant_category = MERCHANT_CATEGORIES[0]

            reasons = []
            status = "APPROVED"
            prediction_label = "SAFE"
            rule_reason = ""
            # Defensive: ensure balance is numeric even if DB has NULL or unexpected value
            try:
                current_balance = float(user.get("balance") or 0)
            except Exception:
                try:
                    current_balance = float(str(user.get("balance") or 0))
                except Exception:
                    current_balance = 0.0
            transactions_today = get_pin_uses_today(user)

            transaction_time = get_now().strftime("%Y-%m-%d %H:%M:%S")
            rule_alert = None

            if amount > current_balance:
                status = "BLOCKED"
                rule_reason = "Insufficient Balance"
                reasons.append(rule_reason)
                rule_alert = {
                    "alert_level": "BLOCKED",
                    "message": "Transaction blocked because the account has insufficient balance.",
                    "reason": rule_reason,
                    "status": status,
                }
                flash("Transaction has been blocked and an email has been sent")
                email_success, email_error = send_email(
                    "Transaction Blocked: Insufficient Balance",
                    build_blocked_transaction_email(
                        user,
                        amount,
                        transaction_time,
                        0,
                        rule_reason,
                    ),
                    user["email"],
                )
                if not email_success:
                    print(f"Email notification failed: {email_error}")

            elif transactions_today >= user["daily_limit"]:
                status = "BLOCKED"
                rule_reason = "Daily Transaction Limit Exceeded"
                reasons.append(rule_reason)
                rule_alert = {
                    "alert_level": "BLOCKED",
                    "message": "Transaction blocked because the daily transaction limit was exceeded.",
                    "reason": rule_reason,
                    "status": status,
                }
                flash("Transaction has been blocked and an email has been sent")
                email_success, email_error = send_email(
                    "Transaction Blocked: Daily Limit Exceeded",
                    build_blocked_transaction_email(
                        user,
                        amount,
                        transaction_time,
                        0,
                        rule_reason,
                    ),
                    user["email"],
                )
                if not email_success:
                    print(f"Email notification failed: {email_error}")

            elif amount > user["max_transaction_amount"]:
                status = "BLOCKED"
                rule_reason = "Maximum Transaction Amount Exceeded"
                reasons.append(rule_reason)
                rule_alert = {
                    "alert_level": "BLOCKED",
                    "message": "Transaction amount exceeds the maximum permitted transaction amount. Transaction blocked.",
                    "reason": rule_reason,
                    "status": status,
                }
                flash("Transaction has been blocked and an email has been sent")
                email_success, email_error = send_email(
                    "Transaction Blocked: Maximum Amount Exceeded",
                    build_blocked_transaction_email(
                        user,
                        amount,
                        transaction_time,
                        0,
                        rule_reason,
                    ),
                    user["email"],
                )
                if not email_success:
                    print(f"Email notification failed: {email_error}")

            if failed_pin_attempts > 3:
                prediction_label = "HIGH_RISK"
                reasons.append("Multiple failed PIN attempts")

            try:
                merchant_encoded = int(encoder.transform([merchant_category])[0])
            except Exception:
                traceback.print_exc()
                merchant_encoded = 0

            features = [
                amount,
                transaction_hour,
                merchant_encoded,
                country_risk,
                card_present,
                online_transaction,
                failed_pin_attempts,
                transactions_last_hour,
                account_age_days,
            ]

            try:
                prediction = model.predict([features])[0]
                probability = model.predict_proba([features])[0][1]
            except Exception:
                traceback.print_exc()
                prediction = 0
                probability = 0.0
            risk_score = round(probability * 100, 2)

            if status == "APPROVED":
                if prediction == 1:
                    prediction_label = "FRAUD"
                    status = "FRAUD"
                    rule_reason = "Machine learning fraud detection triggered"
                    reasons.append(rule_reason)
                    rule_alert = {
                        "alert_level": "FRAUD",
                        "message": "Transaction blocked because the fraud model flagged suspicious behavior.",
                        "reason": rule_reason,
                        "status": status,
                    }
                    flash("Transaction has been blocked and an email has been sent")
                    email_success, email_error = send_email(
                        "Fraud Alert: Transaction Blocked",
                        build_blocked_transaction_email(
                            user,
                            amount,
                            transaction_time,
                            risk_score,
                            rule_reason,
                        ),
                        user["email"],
                    )
                    if not email_success:
                        print(f"Email notification failed: {email_error}")
                elif risk_score > 80:
                    prediction_label = "FRAUD"
                    status = "FRAUD"
                    rule_reason = "High fraud probability"
                    reasons.append(rule_reason)
                    rule_alert = {
                        "alert_level": "FRAUD",
                        "message": "Transaction blocked because the fraud probability exceeded 80%.",
                        "reason": rule_reason,
                        "status": status,
                    }
                    flash("Transaction has been blocked and an email has been sent")
                    email_success, email_error = send_email(
                        "Fraud Alert: High Risk Transaction Blocked",
                        build_blocked_transaction_email(
                            user,
                            amount,
                            transaction_time,
                            risk_score,
                            rule_reason,
                        ),
                        user["email"],
                    )
                    if not email_success:
                        print(f"Email notification failed: {email_error}")

            if not rule_reason:
                rule_reason = "; ".join(reasons) if reasons else "No rule violation"

            balance_after = current_balance if status != "APPROVED" else round(current_balance - amount, 2)

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO transactions(
                    user_id,
                    amount,
                    transaction_hour,
                    transaction_place,
                    transactions_last_hour,
                    failed_pin_attempts,
                    account_age_days,
                    merchant_category,
                    country_risk,
                    card_present,
                    online_transaction,
                    risk_score,
                    fraud_probability,
                    prediction,
                    status,
                    rule_reason,
                    balance_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    amount,
                    transaction_hour,
                    transaction_place,
                    transactions_last_hour,
                    failed_pin_attempts,
                    account_age_days,
                    merchant_category,
                    country_risk,
                    card_present,
                    online_transaction,
                    risk_score,
                    round(probability * 100, 2),
                    prediction_label,
                    status,
                    rule_reason,
                    balance_after,
                ),
            )
            transaction_id = cur.lastrowid
            conn.commit()
            conn.close()

            if rule_alert:
                create_alert(
                    user["id"],
                    transaction_id,
                    rule_alert["alert_level"],
                    rule_alert["message"],
                    rule_alert["reason"],
                    rule_alert["status"],
                )

            if status == "APPROVED":
                new_balance = round(current_balance - amount, 2)
                update_user_balance(user["id"], new_balance)

            explanation = explain_transaction(features, user, {
                "amount": amount,
                "transaction_hour": transaction_hour,
                "failed_pin_attempts": failed_pin_attempts,
                "transactions_last_hour": transactions_last_hour,
                "account_age_days": account_age_days,
                "country_risk": country_risk,
                "merchant_category": merchant_category,
                "online_transaction": online_transaction,
                "card_present": card_present,
            })

            result = {
                "amount": amount,
                "status": status,
                "prediction": prediction_label,
                "risk_score": risk_score,
                "fraud_probability": round(probability * 100, 2),
                "rule_reason": rule_reason,
                "balance_after": balance_after,
                "explanations": explanation,
            }
            user = get_user_by_id(user["id"])
            transactions_today = get_pin_uses_today(user)
            used_today = min(get_today_transaction_count(user["id"]), int(user.get("daily_limit") or 0))

        except Exception:
            traceback.print_exc()
            flash("An internal error occurred while analyzing the transaction. Please try again.")
            result = None
            explanation = []

    return render_template(
        "index.html",
        user=user,
        transactions_today=transactions_today,
        used_today=used_today,
        merchant_categories=MERCHANT_CATEGORIES,
        result=result,
    )


def update_user_balance(user_id, new_balance):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_balance, user_id),
    )
    conn.commit()
    conn.close()


def deposit_user_balance(user_id, amount):
    user = get_user_by_id(user_id)
    if not user:
        return None
    try:
        current_balance = Decimal(str(user.get("balance") or 0))
    except Exception:
        current_balance = Decimal("0.00")
    new_balance = (current_balance + amount).quantize(Decimal("0.01"))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (float(new_balance), user_id),
    )
    conn.commit()
    conn.close()
    return new_balance


@app.route("/deposit", methods=["GET", "POST"])
@require_login
def deposit():
    if request.method == "GET":
        return redirect(url_for("transaction"))

    user = current_user()
    raw_amount = request.form.get("deposit_amount", "0").strip().replace(",", "")
    try:
        deposit_amount = Decimal(raw_amount)
    except (InvalidOperation, ValueError):
        flash("Invalid deposit amount. Please enter a valid number.")
        return redirect(url_for("transaction"))

    if deposit_amount <= 0:
        flash("Deposit amount must be greater than 0.")
        return redirect(url_for("transaction"))

    deposit_amount = deposit_amount.quantize(Decimal("0.01"))
    try:
        previous_balance = Decimal(str(user.get("balance") or 0))
    except Exception:
        previous_balance = Decimal("0.00")
    new_balance = deposit_user_balance(user["id"], deposit_amount)
    flash(
        f"₹{deposit_amount} added successfully. Previous balance: ₹{previous_balance}. New balance: ₹{new_balance}."
    )
    return redirect(url_for("transaction"))




@app.route("/dashboard")
@require_login
def dashboard():
    user = current_user()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user["id"],))
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND prediction = 'FRAUD'", (user["id"],)
    )
    frauds = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = 'BLOCKED'", (user["id"],)
    )
    blocked = cur.fetchone()[0]

    date_col = get_datetime_column("transactions")

    cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND prediction = 'SAFE' AND status = 'APPROVED'", (user["id"],)
    )
    safe = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND risk_score < 40", (user["id"],)
    )
    low_risk = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND risk_score >= 40 AND risk_score < 80", (user["id"],)
    )
    medium_risk = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND risk_score >= 80", (user["id"],)
    )
    high_risk = cur.fetchone()[0]

    cur.execute(
        f"SELECT date({date_col}) AS day, SUM(amount) AS total_amount FROM transactions WHERE user_id = ? GROUP BY day ORDER BY day DESC LIMIT 10",
        (user["id"],),
    )
    chart_data = cur.fetchall()

    cur.execute(
        "SELECT merchant_category, AVG(risk_score) AS avg_risk, COUNT(*) AS category_count "
        "FROM transactions WHERE user_id = ? GROUP BY merchant_category "
        "ORDER BY category_count DESC LIMIT 10",
        (user["id"],),
    )
    category_data = cur.fetchall()
    conn.close()

    chart_labels = [row["day"] for row in reversed(chart_data)]
    chart_amounts = [row["total_amount"] for row in reversed(chart_data)]
    category_labels = [row["merchant_category"] for row in category_data]
    category_risks = [round(row["avg_risk"], 2) for row in category_data]

    return render_template(
        "dashboard.html",
        user=user,
        total=total,
        frauds=frauds,
        blocked=blocked,
        safe=safe,
        current_balance=round(float(user.get("balance") or 0), 2),
        transactions_today=get_today_transaction_count(user["id"]),
        fraud_rate=round((frauds / total) * 100, 2) if total else 0,
        low_risk=low_risk,
        medium_risk=medium_risk,
        high_risk=high_risk,
        category_labels=category_labels,
        category_risks=category_risks,
    )


@app.route("/alerts")
@require_login
def alerts():
    user = current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    date_col = get_datetime_column("transactions")
    cur.execute(
        f"SELECT *, COALESCE(created_at, timestamp, updated_at) AS display_date FROM transactions WHERE user_id = ? AND (prediction = 'FRAUD' OR status IN ('BLOCKED', 'REJECTED', 'FRAUD')) ORDER BY {date_col} DESC",
        (user["id"],),
    )
    alerts_data = normalize_timestamp_rows(cur.fetchall())
    conn.close()
    return render_template("alerts.html", user=user, alerts=alerts_data)


@app.route("/history")
@require_login
def history():
    user = current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    date_col = get_datetime_column("transactions")
    cur.execute(
        f"SELECT *, COALESCE(created_at, timestamp, updated_at) AS display_date FROM transactions WHERE user_id = ? ORDER BY {date_col} DESC",
        (user["id"],),
    )
    # cur.execute(
    #     f"SELECT *, timestamp AS display_date FROM transactions WHERE user_id = ? ORDER BY {date_col} DESC",
    #     (user["id"],),
    # )
    transactions = normalize_timestamp_rows(cur.fetchall())
    conn.close()
    return render_template(
        "history.html",
        user=user,
        transactions=transactions,
    )

@app.route("/report")
@require_login
def report():
    user = current_user()
    query, params = build_report_query(user["id"], request.args)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    data = normalize_timestamp_rows(cur.fetchall())

    total = len(data)
    frauds = sum(1 for row in data if row["prediction"] == "FRAUD")
    safe = sum(1 for row in data if row["prediction"] == "SAFE")
    blocked = sum(1 for row in data if row["status"] in ("BLOCKED", "REJECTED"))
    fraud_rate = round((frauds / total) * 100, 2) if total else 0

    conn.close()
    return render_template(
        "report.html",
        user=user,
        data=data,
        total=total,
        frauds=frauds,
        safe=safe,
        blocked=blocked,


        
        fraud_rate=fraud_rate,
        filters=request.args,
    )


@app.route("/download_report")
@require_login
def download_report():
    user = current_user()
    query, params = build_report_query(user["id"], request.args)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    content = []

    content.append(Paragraph("Credit Card Fraud Report", styles["Title"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    content.append(Spacer(1, 12))

    summary = [
        ["User", user["full_name"]],
        ["Total Transactions", str(len(rows))],
        ["Fraud Transactions", str(sum(1 for row in rows if row["prediction"] == "FRAUD"))],
        ["Blocked Transactions", str(sum(1 for row in rows if row["status"] in ("BLOCKED", "REJECTED")))],
        ["Current Balance", f"₹{round(user['balance'], 2)}"],
    ]
    table = Table(summary, colWidths=[180, 280])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.gray),
        ])
    )
    content.append(table)
    content.append(Spacer(1, 18))

    heading = Paragraph("Transactions", styles["Heading2"])
    content.append(heading)
    content.append(Spacer(1, 10))

    transaction_table = [
        ["Date", "Amount", "Prediction", "Risk Score", "Status", "Balance After"],
    ]
    for row in rows:
        transaction_table.append(
            [
                get_row_timestamp(row),
                f"₹{row['amount']}",
                row["prediction"],
                f"{row['risk_score']}",
                row["status"],
                f"₹{row['balance_after'] if row['balance_after'] is not None else 'N/A'}",
            ]
        )

    table = Table(transaction_table, colWidths=[100, 80, 90, 80, 90, 90])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.gray),
        ])
    )
    content.append(table)
    doc.build(content)

    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        download_name="fraud_report.pdf",
        as_attachment=True,
    )


@app.route("/download_excel")
@require_login
def download_excel():
    user = current_user()
    query, params = build_report_query(user["id"], request.args)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fraud Report"
    sheet.append([
        "ID",
        "Date",
        "Amount",
        "Prediction",
        "Risk Score",
        "Status",
        "Balance After",
    ])
    for row in rows:
        sheet.append(
            [
                row["id"],
                get_row_timestamp(row),
                row["amount"],
                row["prediction"],
                row["risk_score"],
                row["status"],
                row["balance_after"],
            ]
        )

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="fraud_report.xlsx",
        as_attachment=True,
    )


@app.route("/__dev_logs__")
def dev_logs():
    # Local-only helper to fetch recent logs for debugging.
    if request.remote_addr not in ("127.0.0.1", "::1", "localhost"):
        return "Forbidden", 403
    out = []
    for name in ("server.log", "error.log"):
        path = os.path.join(BASE_DIR, name)
        out.append(f"--- {name} ---")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    out.append(f.read())
            except Exception as e:
                out.append(f"Failed to read {name}: {e}")
        else:
            out.append("(no file)")
    return "\n".join(out), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route('/__debug_run__')
def debug_run():
    # Local-only: simulate a logged-in user session for the given email and GET /transaction
    if request.remote_addr not in ("127.0.0.1", "::1", "localhost"):
        return "Forbidden", 403
    email = request.args.get('email')
    if not email:
        return "Provide ?email=...", 400
    try:
        user = get_user_by_email(email)
        if not user:
            return f"No user with email {email}", 404

        # Use test_client to simulate session and request
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['user_id'] = user['id']
            resp = c.get('/transaction')
            return (f"STATUS {resp.status_code}\n\n" + resp.data.decode('utf-8', errors='replace')[:4000]), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        return (f"EXCEPTION:\n{tb}"), 500, {'Content-Type': 'text/plain; charset=utf-8'}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


@app.errorhandler(500)
def internal_server_error(e):
    # Log full traceback to error.log for easier debugging when debug mode is off
    try:
        tb = traceback.format_exc()
    except Exception:
        tb = str(e)
    try:
        with open(os.path.join(BASE_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - 500 Error:\n{tb}\n")
    except Exception:
        pass
    return (
        "The server encountered an internal error and the exception was logged to error.log.",
        500,
    )
