import pyrebase
import csv
import time
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Firebase configuration
config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DB_URL"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
}

# Initialize Firebase
firebase = pyrebase.initialize_app(config)
db = firebase.database()

RAW_FILE = "data_raw.csv"

# Create CSV if not exists
if not os.path.exists(RAW_FILE):
    with open(RAW_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "flex1", "flex2"])


def collect_data():
    try:
        data = db.child("PostureData").get().val()

        if not data:
            return None

        today = datetime.now().strftime("%Y-%m-%d")

        # -------- FILTER TODAY'S DATA --------
        today_items = [
            (key, value)
            for key, value in data.items()
            if value.get("timestamp", "").startswith(today)
        ]

        if not today_items:
            print("⚠️ No data for today")
            return None

        # -------- SORT BY TIMESTAMP --------
        sorted_items = sorted(
            today_items,
            key=lambda x: x[1].get("timestamp", "")
        )

        latest_key, latest_data = sorted_items[-1]

        # -------- SKIP IF ALREADY PROCESSED --------
        if "posture" in latest_data:
            return None

        flex1 = latest_data["sensor1"]["adc"]
        flex2 = latest_data["sensor2"]["adc"]

        timestamp = time.time()

        # Save raw data
        with open(RAW_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, flex1, flex2])

        return latest_key, timestamp, flex1, flex2

    except Exception as e:
        print("❌ Error fetching Firebase data:", e)

    return None