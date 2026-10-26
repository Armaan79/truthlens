import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os


# ==============================
# 1. LOAD DATASETS
# ==============================

fake = pd.read_csv("data/Fake.csv")
true = pd.read_csv("data/True.csv")


# Add labels
fake["label"] = 0
true["label"] = 1


# Combine datasets
data = pd.concat([fake, true], ignore_index=True)


# ==============================
# 2. PREPARE TEXT
# ==============================

data["content"] = (
    data["title"].fillna("") + " " +
    data["text"].fillna("")
)


# Keep only required columns
data = data[["content", "label"]]


# Remove empty articles
data = data[data["content"].str.strip() != ""]


# Remove duplicate articles
before = len(data)

data = data.drop_duplicates(
    subset=["content"]
).reset_index(drop=True)

after = len(data)

print(f"Removed {before - after} duplicate articles.")
print(f"Total articles used: {after}")


# ==============================
# 3. SPLIT DATA
# ==============================

X_train, X_test, y_train, y_test = train_test_split(
    data["content"],
    data["label"],
    test_size=0.20,
    random_state=42,
    stratify=data["label"]
)


# ==============================
# 4. TF-IDF
# ==============================

vectorizer = TfidfVectorizer(
    stop_words="english",
    max_features=100000,
    ngram_range=(1, 2),
    min_df=2,
    max_df=0.95,
    sublinear_tf=True
)


X_train_vectorized = vectorizer.fit_transform(X_train)
X_test_vectorized = vectorizer.transform(X_test)


print(
    f"Training features: "
    f"{X_train_vectorized.shape[1]}"
)


# ==============================
# 5. TRAIN MODEL
# ==============================

model = LogisticRegression(
    max_iter=2000,
    class_weight="balanced"
)

model.fit(X_train_vectorized, y_train)


# ==============================
# 6. EVALUATE MODEL
# ==============================

predictions = model.predict(X_test_vectorized)

accuracy = accuracy_score(
    y_test,
    predictions
)

print()
print("==============================")
print("MODEL EVALUATION")
print("==============================")
print(f"Accuracy: {accuracy * 100:.2f}%")
print()
print(classification_report(
    y_test,
    predictions,
    target_names=["Fake", "Real"]
))


# ==============================
# 7. SAVE MODEL
# ==============================

os.makedirs("model", exist_ok=True)


joblib.dump(
    model,
    "model/fake_news_model.pkl"
)

joblib.dump(
    vectorizer,
    "model/vectorizer.pkl"
)


print("==============================")
print("MODEL SAVED SUCCESSFULLY")
print("==============================")