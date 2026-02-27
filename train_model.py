import pandas as pd
import joblib
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# load dataset
data = pd.read_csv("dataset_raw.csv")

# feature engineering
data["diff"] = data["flex1"] - data["flex2"]
data["sum"] = data["flex1"] + data["flex2"]
data["ratio"] = data["flex1"] / data["flex2"]

# features
X = data[["flex1","flex2","diff","sum","ratio"]]

# labels
y = data["label"]

# split dataset
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# create model
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=6,
    random_state=42
)

# train model
model.fit(X_train, y_train)

# test model
pred = model.predict(X_test)

accuracy = accuracy_score(y_test, pred)

print("Accuracy:", accuracy)

joblib.dump(model, "posture_model.pkl")