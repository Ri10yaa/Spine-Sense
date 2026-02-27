import time
import csv
import os

from get_data import collect_data
from predict_posture import predict_posture

OUTPUT_FILE = "flex_data.csv"

if not os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE,"w",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","flex1","flex2","posture"])


while True:

    result = collect_data()

    if result:

        timestamp, flex1, flex2 = result

        posture = predict_posture(flex1, flex2)

        print("Flex1:",flex1,"Flex2:",flex2,"Posture:",posture)

        with open(OUTPUT_FILE,"a",newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp,flex1,flex2,posture])

    time.sleep(2)