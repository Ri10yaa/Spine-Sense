import joblib
import pandas as pd

model = joblib.load("posture_model.pkl")

posture_classes = {
    0:"normal",
    1:"slouch",
    2:"left tilt",
    3:"right tilt",
    4:"forward bend"
}


def predict_posture(flex1, flex2):

    input_data = pd.DataFrame([[flex1,flex2]],columns=["flex1","flex2"])

    prediction = model.predict(input_data)[0]

    return posture_classes[prediction]