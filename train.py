import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from feature_engineering import load_data, clean_data, get_features_and_target

print("Loading and cleaning data...")
df = load_data("data/telco_churn.csv")
df = clean_data(df)
X, y = get_features_and_target(df)

print("Splitting into train/test...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

print("Training model...")
model = RandomForestClassifier(n_estimators=200, max_depth=6, class_weight='balanced', random_state=42)
model.fit(X_train, y_train)

print("Evaluating model...")
preds = model.predict(X_test)
probs = model.predict_proba(X_test)[:, 1]

accuracy = accuracy_score(y_test, preds)
print(f"Overall Accuracy: {accuracy * 100:.2f}%")

results = pd.DataFrame({'actual': y_test.values, 'prob': probs})
results['actual_label'] = results['actual'].map({1: 'Churn', 0: 'Not Churn'})
results = results.sort_values('prob', ascending=False)

overall_churn_rate = y_test.mean()
k_values = [500]

for k in k_values:
    if len(results) < k:
        print(f"Skipping k={k}: only {len(results)} customers in test set, fewer than requested k.")
        continue

    top_k = results.head(k)
    precision_at_k = top_k['actual'].mean()
    lift_at_k = precision_at_k / overall_churn_rate
    print(f"Precision@{k}: {precision_at_k:.2f}")
    print(f"Lift@{k}: {lift_at_k:.2f}x")

importance = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
print("\nFeature Importance:")
print(importance)

print("Saving model...")
joblib.dump(model, "model.pkl")
print("Model saved to model.pkl")