import joblib
import pandas as pd

# Load trained ML model
model = joblib.load("posture_model.pkl")

# Minimal meaningful classes
ml_classes = {
    0: "Good Posture",
    1: "Slouching",
    4: "Forward Bend"
}


def predict_posture(flex1, flex2):

    # -------- FEATURE ENGINEERING --------
    diff = flex1 - flex2
    ratio = flex1 / flex2 if flex2 != 0 else 0
    total = flex1 + flex2

    input_data = pd.DataFrame(
        [[flex1, flex2, diff, total, ratio]],
        columns=["flex1", "flex2", "diff", "sum", "ratio"]
    )

    # -------- ML PREDICTION --------
    prediction = model.predict(input_data)[0]
    ml_result = ml_classes.get(prediction, "Good Posture")

    # -------- RULE-BASED LOGIC --------

    # Severe posture
    if flex1 > 1200 or flex2 > 1200:
        return "Severe Bad Posture"

    # Both bad → slouch
    if flex1 > 700 and flex2 > 700:
        return "Slouching"

    # Neck forward
    if flex2 > 700 and flex1 <= 700:
        return "Neck Forward"

    # Back slouch
    if flex1 > 700 and flex2 <= 700:
        return "Back Slouch"

    # Mild issue
    if 300 < flex1 <= 700 or 300 < flex2 <= 700:
        return "Slightly Poor Posture"

    # Otherwise → good / ML result
    return ml_result