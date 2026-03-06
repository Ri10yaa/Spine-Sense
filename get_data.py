import pyrebase
import csv
import time
import os
from dotenv import load_dotenv

load_dotenv()

config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DB_URL"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
}

firebase = pyrebase.initialize_app(config)
db = firebase.database()

RAW_FILE = "data_raw.csv"

if not os.path.exists(RAW_FILE):
    with open(RAW_FILE,"w",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","flex1","flex2"])


def collect_data():

    data = db.child("PostureData").get().val()

    if data:

        latest_key = list(data.keys())[-1]
        latest_data = data[latest_key]

        flex1 = latest_data["sensor1"]["adc"]
        flex2 = latest_data["sensor2"]["adc"]

        timestamp = time.time()

        with open(RAW_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, flex1, flex2])

        return timestamp, flex1, flex2

    return None