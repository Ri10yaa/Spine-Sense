import joblib
import pandas as pd

model = joblib.load("posture_model.pkl")

posture_classes = {
    0: "normal",
    1: "slouch",
    2: "left tilt",
    3: "right tilt",
    4: "forward bend"
}

def predict_posture(flex1, flex2):

    diff = flex1 - flex2
    ratio = flex1 / flex2 if flex2 != 0 else 0
    total = flex1 + flex2

    # enforce same feature order as training
    input_data = pd.DataFrame(
        [[flex1, flex2, diff, total, ratio]],
        columns=["flex1", "flex2", "diff", "sum", "ratio"]
    )

    prediction = model.predict(input_data)[0]

    return posture_classes[prediction]