import pyrebase
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

import json

nodes = ["postureresult", "PostureResult", "PostureData", "Stats"]

for node in nodes:
    data = db.child(node).get().val()
    if not data:
        print(f"\n[{node}] — No data found")
    else:
        print(f"\n{'='*50}")
        print(f"[{node}]")
        print('='*50)
        print(json.dumps(data, indent=2))
