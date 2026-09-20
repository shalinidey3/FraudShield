# FraudShield – Credit Card Fraud Detection & Transaction Monitoring System

## Overview

**FraudShield** is a Machine Learning-based Credit Card Fraud Detection and Transaction Monitoring System designed to identify fraudulent transactions and enhance banking security. The system combines predictive machine learning with rule-based validation to monitor transactions, generate alerts, and provide detailed reporting for administrators and users.

This project was developed as a Bachelor of Technology (B.Tech.) project in the Department of Computer Science & Engineering at Techno Institute of Engineering & Management.

---

## Features

* 🔐 User Authentication & Management
* 💳 Banking Profile Management
* 🤖 Machine Learning-based Fraud Detection
* 📊 Real-time Transaction Monitoring
* ⚠️ Rule-based Security Validation
* 📈 Dashboard and Reporting System
* 📧 Automated Email Notifications
* 📝 Transaction History Management

---

## Project Objectives

* Detect fraudulent credit card transactions with high accuracy.
* Monitor transactions in real time.
* Apply rule-based validation for enhanced security.
* Generate alerts for suspicious activities.
* Maintain complete transaction records.
* Provide dashboards and analytical reports.
* Improve banking security through intelligent fraud detection.

---

## Technology Stack

### Frontend

* HTML
* CSS
* JavaScript

### Backend

* Python
* Flask

### Machine Learning

* Scikit-learn
* Random Forest Classifier
* Pandas
* NumPy

### Database

* SQLite

### Reporting

* ReportLab
* OpenPyXL

---

## Machine Learning Model

The fraud detection module uses the **Random Forest** algorithm to classify transactions as either:

* Legitimate
* Fraudulent

The model analyzes transaction features and generates a risk prediction to assist in identifying suspicious activities.

---

## System Modules

### User Management

* User Registration
* Login Authentication
* Profile Management

### Banking Profile

* Store and manage banking information
* Transaction records

### Fraud Detection

* Machine Learning prediction
* Rule-based validation
* Risk score generation

### Transaction Monitoring

* Real-time transaction analysis
* Suspicious activity tracking

### Reporting

* Dashboard visualization
* Transaction reports
* Fraud analytics

### Notification System

* Email alerts for suspicious transactions
* Fraud warning notifications

---

## Project Workflow

1. User logs into the system.
2. Transaction details are submitted.
3. Rule-based security validation is performed.
4. The Machine Learning model predicts fraud probability.
5. Suspicious transactions trigger alerts.
6. Transactions are stored in the database.
7. Reports and dashboards are updated.

---

## Future Enhancements

The project can be further improved with:

* Integration with Plaid Sandbox API
* Support for live banking APIs
* Real-time monitoring using webhooks
* OTP verification for medium-risk transactions
* SMS notifications
* Mobile push notifications
* Advanced ML models (XGBoost, LightGBM, Deep Learning)
* User behavioral analytics
* Device fingerprinting
* Cloud deployment (AWS, Azure, Google Cloud)

---

## Project Structure

```text
FraudShield/
│
├── app.py
├── model/
│   ├── fraud_model.pkl
│   └── train_model.py
├── templates/
├── static/
├── database/
├── reports/
├── notifications/
├── dataset/
├── requirements.txt
└── README.md
```

> *The folder structure above is a suggested organization and may vary depending on your implementation.*

---

## Installation

1. Clone the repository

```bash
git clone https://github.com/your-username/FraudShield.git
```

2. Navigate to the project directory

```bash
cd FraudShield
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Run the application

```bash
python app.py
```

5. Open your browser and visit

```
http://127.0.0.1:5000/
```

---

## Expected Results

* Accurate fraud prediction using Machine Learning.
* Faster detection of suspicious transactions.
* Improved transaction monitoring.
* Automated notification system.
* Better banking security and fraud prevention.

---

## References

* Scikit-learn Documentation
* Flask Documentation
* SQLite Documentation
* Pandas Documentation
* NumPy Documentation
* ReportLab Documentation
* OpenPyXL Documentation
* Kaggle Credit Card Fraud Detection Dataset
* IEEE Xplore Research Papers
* GitHub Open Source Projects

---

## Contributors

* Gargi Chatterjee
* Shalini Dey
* Sneha Debnath
* Promita Roy
* Mitali Si

---

## License

This project was developed for educational and academic purposes. Feel free to use and modify it for learning and research.
