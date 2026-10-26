import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from phishing_detector import extract_features

df = pd.read_csv("data/raw_data.csv")
df["label"] = df["label"].map({"legitimate": 0, "phishing": 1})
X = df["url"].apply(extract_features).tolist()
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=.2, random_state=42, stratify=y
)

model = RandomForestClassifier(
    n_estimators=100, random_state=42, n_jobs=-1
)
model.fit(X_train, y_train)

print("Accuracy:", model.score(X_test, y_test)*100,"%")
joblib.dump(model, "model/phishing_model.pkl")
print("Model saved!")