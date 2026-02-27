import pyrebase
import csv
import time
import os

config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DB_URL"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
}

firebase = pyrebase.initialize_app(config)
db = firebase.database()

RAW_FILE = "dataset_raw.csv"

if not os.path.exists(RAW_FILE):
    with open(RAW_FILE,"w",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","flex1","flex2"])


def collect_data():

    data = db.child("posture").get().val()

    if data:

        flex1 = data.get("flex1")
        flex2 = data.get("flex2")

        timestamp = time.time()

        with open(RAW_FILE,"a",newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp,flex1,flex2])

        return timestamp, flex1, flex2

    return None