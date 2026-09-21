import os
import sqlite3

os.makedirs("database", exist_ok=True)
conn = sqlite3.connect("database/fraud.db")
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

conn.commit()
conn.close()
print("Database created successfully!")
