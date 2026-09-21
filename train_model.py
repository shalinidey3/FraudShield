import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score

print("Loading dataset...")

df = pd.read_csv("dataset/fraud_data.csv")

print("Encoding merchant categories...")

encoder = LabelEncoder()

df["merchant_category"] = encoder.fit_transform(
    df["merchant_category"]
)

X = df.drop("fraud", axis=1)
y = df["fraud"]

print("Splitting dataset...")

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

print("Training Random Forest...")

model = RandomForestClassifier(
    n_estimators=100,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

pred = model.predict(X_test)

accuracy = accuracy_score(y_test, pred)

print("Accuracy:", accuracy)

joblib.dump(model, "models/model.pkl")

joblib.dump(encoder, "models/merchant_encoder.pkl")

print("Model saved successfully!")