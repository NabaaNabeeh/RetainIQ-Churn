# Handoff Notes — Feature Engineering & Training (done by Nabaa)

## How to get the model
1. Install dependencies: `pip install -r requirements.txt`
2. Make sure `data/telco_churn.csv` exists in the project folder
3. Run: `python train.py`
4. This produces `model.pkl` in the project root — this is the trained model your API will load

## What `api.py` needs to do
- Load `model.pkl` once when the API starts (not on every request)
- Define a `/predict` endpoint that:
  - Accepts one customer's raw data (same 19 fields, before encoding)
  - Runs it through `clean_data()` from `feature_engineering.py`
  - Calls `model.predict_proba()` to get the churn probability
  - Returns the probability (e.g., `{"churn_probability": 0.78}`)
- Use Pydantic input validation (defined directly in `api.py`) so bad/missing fields are rejected clearly
- Basic error handling for missing model file or bad input

## What `monitor.py` needs to do
- Log each prediction request + the probability returned (so we can review later)
- Track basic drift: compare average predicted churn probability over time (e.g., this week vs. last month) to catch if the model's behavior is shifting
- Doesn't need to be complex — a simple log file and a basic comparison check is enough for this assignment

