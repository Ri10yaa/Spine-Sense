import time
import csv
import os
import pyrebase
from dotenv import load_dotenv

from get_data import collect_data
from predict_posture import predict_posture

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

OUTPUT_FILE = "flex_data.csv"

# Create CSV if not exists
if not os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "flex1", "flex2", "posture"])


# -------- UPDATE POSTURE IN SAME FIREBASE ENTRY --------
def update_posture_firebase(key, posture):
    try:
        db.child("PostureData").child(key).update({
            "posture": posture
        })

        print(f"✅ Posture updated for {key}")

    except Exception as e:
        print("❌ Firebase update failed:", e)


# -------- MAIN LOOP --------
while True:

    result = collect_data()

    if result:
        key, timestamp, flex1, flex2 = result

        posture = predict_posture(flex1, flex2)

        print(f"Flex1: {flex1} | Flex2: {flex2} | Posture: {posture}")

        # Save processed data
        with open(OUTPUT_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, flex1, flex2, posture])

        # Update Firebase
        update_posture_firebase(key, posture)

    time.sleep(2)