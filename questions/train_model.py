"""
Train the decision tree classifier.

Loads the synthetic data, fits a DecisionTreeClassifier with constraints
that prevent it from memorizing synthetic noise, evaluates on a held-out
split, and saves the trained model as a pickle.

Constraints worth knowing:
  * max_depth=12        - tree can't grow deeper than the feature/question budget
  * min_samples_leaf=15 - every leaf reflects at least 15 cases (smoothing)
  * class_weight="balanced" - rare plans (like Emergency Shelter) don't
    get drowned by common ones during training.

Run from the embpath_intake directory:
    python synthetic_data.py
    python train_model.py
"""

import pickle

import numpy as np
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier


def main():
    print("Loading synthetic data...")
    data = np.load("synthetic_data.npz")
    X, y = data["X"], data["y"]
    print(f"  Loaded {len(X)} examples with {X.shape[1]} features.")

    print("Splitting train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print("Training DecisionTreeClassifier...")
    clf = DecisionTreeClassifier(
        max_depth=12,
        min_samples_leaf=15,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Held-out accuracy: {acc:.3f}")
    print()
    print("Per-plan performance:")
    print(classification_report(y_test, y_pred, zero_division=0))

    with open("intake_model.pkl", "wb") as f:
        pickle.dump(clf, f)  # nosemgrep: python.lang.security.deserialization.pickle.avoid-pickle
    print("Saved trained model to intake_model.pkl")


if __name__ == "__main__":
    main()
