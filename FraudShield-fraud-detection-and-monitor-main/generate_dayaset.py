import pandas as pd
import random

records = []

merchant_categories = [
    "Grocery",
    "Electronics",
    "Travel",
    "Restaurant",
    "Fuel",
    "Shopping",
    "Entertainment"
]

for _ in range(300000):

    amount = round(random.uniform(10, 5000), 2)

    transaction_hour = random.randint(0, 23)

    merchant_category = random.choice(merchant_categories)

    country_risk = random.randint(0, 1)

    card_present = random.randint(0, 1)

    online_transaction = random.randint(0, 1)

    failed_attempts = random.randint(0, 5)

    transactions_last_hour = random.randint(1, 20)

    account_age_days = random.randint(30, 3650)

    fraud_score = 0

    if amount > 2000:
        fraud_score += 1

    if transaction_hour >= 22 or transaction_hour <= 4:
        fraud_score += 1

    if country_risk == 1:
        fraud_score += 1

    if online_transaction == 1:
        fraud_score += 1

    if failed_attempts >= 3:
        fraud_score += 1

    if transactions_last_hour >= 10:
        fraud_score += 1

    fraud = 1 if fraud_score >= 3 else 0

    records.append([
        amount,
        transaction_hour,
        merchant_category,
        country_risk,
        card_present,
        online_transaction,
        failed_attempts,
        transactions_last_hour,
        account_age_days,
        fraud
    ])

df = pd.DataFrame(
    records,
    columns=[
        "transaction_amount",
        "transaction_hour",
        "merchant_category",
        "country_risk",
        "card_present",
        "online_transaction",
        "failed_attempts",
        "transactions_last_hour",
        "account_age_days",
        "fraud"
    ]
)

df.to_csv("dataset/fraud_data.csv", index=False)

print("Dataset generated successfully!")
print("Rows:", len(df))