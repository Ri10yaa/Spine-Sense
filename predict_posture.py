import joblib
import pandas as pd
import warnings

warnings.filterwarnings(
    "ignore",
    message="Trying to unpickle estimator.*",
    category=UserWarning,
    module="sklearn"
)

model = joblib.load("posture_model.pkl")

ml_classes = {
    0: "Good Posture",
    1: "Slouching",
    2: "Neck Forward",
    3: "Back Slouch",
    4: "Forward Bend",
    5: "Slightly Poor Posture"
}

# Only truly extreme values that the ML will never have
# seen enough of to classify reliably
SEVERE_THRESHOLD = 1200


def predict_posture(flex1, flex2):

    # ---- FEATURE ENGINEERING ----
    diff = flex1 - flex2
    ratio = flex1 / flex2 if flex2 != 0 else 0
    total = flex1 + flex2

    input_data = pd.DataFrame(
        [[flex1, flex2, diff, total, ratio]],
        columns=["flex1", "flex2", "diff", "sum", "ratio"]
    )

    # ---- ML PREDICTION (primary) ----
    prediction = model.predict(input_data)[0]
    confidence = max(model.predict_proba(input_data)[0])
    ml_result = ml_classes.get(prediction, "Good Posture")

    # ---- RULE-BASED OVERRIDE (only for extreme/unsafe readings) ----
    # These are values far outside normal training range where
    # the ML model cannot be trusted.
    if flex1 > SEVERE_THRESHOLD or flex2 > SEVERE_THRESHOLD:
        return "Severe Bad Posture"

    # ---- CONFIDENCE FALLBACK ----
    # If the ML model is uncertain, use rules as a safety net
    if confidence < 0.60:
        if flex1 > 700 and flex2 > 700:
            return "Slouching"
        if flex2 > 700 and flex1 <= 700:
            return "Neck Forward"
        if flex1 > 700 and flex2 <= 700:
            return "Back Slouch"
        if 300 < flex1 <= 700 or 300 < flex2 <= 700:
            return "Slightly Poor Posture"
        return "Good Posture"

    # ML result is confident — trust it
    return ml_result