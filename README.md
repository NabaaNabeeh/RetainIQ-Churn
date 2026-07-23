# RetainIQ — Customer Churn Prediction

Predicts which active customers are likely to churn, so the retention team can focus outreach on the top 500 highest-risk customers.

## What's inside
- `feature_engineering.py` — cleans and encodes the Telco Customer Churn dataset
- `train.py` — trains a Random Forest (class-balanced), evaluates with Precision@500 and Lift@500, saves `model.pkl`
- `api.py` — FastAPI server with `/predict` (single customer) and `/batch_predict` (many customers, ranked by risk)
- `ui.py` — Streamlit interface for manual predictions, admin dashboard, and batch CSV upload with insights
- `monitor.py` — checks prediction logs for drift (compares last 7 days vs. older average churn probability)

## How to run

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Train the model (creates `model.pkl`):
```bash
python train.py
```

3. Start the API (leave running):
```bash
python api.py
```

4. In a new terminal, start the UI:
```bash
python -m streamlit run ui.py
```

5. Log in with `admin` / `admin`

6. To check monitoring/drift:
```bash
python monitor.py
```
   (Can also be run directly from inside the UI — see the Monitoring tab in the Admin Dashboard.)
