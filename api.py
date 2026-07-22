"""
RetainIQ — Customer Churn Prediction API

A complete FastAPI serving pipeline with:
  • Single + Batch prediction endpoints
  • Pydantic validation
  • MLflow experiment tracking
  • Structured JSON prediction logging
  • Health checks

Run:
    uvicorn api:app --reload --port 8000

Docs:
    http://localhost:8000/docs
"""

import json
import logging
import logging.handlers
import math
import os
import random
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
import pandas as pd
import joblib
from feature_engineering import clean_data

import mlflow
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# ============================================================================
# CONFIG
# ============================================================================

APP_NAME = "RetainIQ"
APP_VERSION = "0.1.0"
MODEL_VERSION = "1.0.0"
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "./mlruns")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT_NAME", "retainiq-churn")
BATCH_MAX = int(os.getenv("BATCH_MAX_CUSTOMERS", "1000"))
BATCH_DEFAULT_TOP_N = int(os.getenv("BATCH_DEFAULT_TOP_N", "10"))

# ============================================================================
# LOGGING
# ============================================================================


def _setup_logging() -> None:
    """Configure console + rotating JSON file logging."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    root.addHandler(ch)

    # File (JSON lines, 10 MB rotation)
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=10_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(fh)

    for name in ("uvicorn.access", "mlflow", "git"):
        logging.getLogger(name).setLevel(logging.WARNING)


log = logging.getLogger("retainiq")

# Prediction logger — writes to logs/predictions.log
_pred_logger = logging.getLogger("retainiq.predictions")
_pred_logger.propagate = False
_pred_handler = logging.FileHandler(LOG_DIR / "predictions.log", encoding="utf-8")
_pred_handler.setFormatter(logging.Formatter("%(message)s"))
_pred_logger.addHandler(_pred_handler)
_pred_logger.setLevel(logging.INFO)


def log_prediction(record: dict) -> None:
    """Write one JSON line to predictions.log."""
    try:
        _pred_logger.info(json.dumps(record, default=str))
    except Exception:
        log.warning("Failed to write prediction log")


# ============================================================================
# SCHEMAS  (Pydantic request / response models)
# ============================================================================


class Gender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"


class ContractType(str, Enum):
    MONTH_TO_MONTH = "Month-to-month"
    ONE_YEAR = "One year"
    TWO_YEAR = "Two year"


class InternetService(str, Enum):
    DSL = "DSL"
    FIBER_OPTIC = "Fiber optic"
    NO = "No"


class PaymentMethod(str, Enum):
    ELECTRONIC_CHECK = "Electronic check"
    MAILED_CHECK = "Mailed check"
    BANK_TRANSFER = "Bank transfer (automatic)"
    CREDIT_CARD = "Credit card (automatic)"


class CustomerData(BaseModel):
    """One customer's features for churn prediction."""
    customerID: str
    gender: str
    SeniorCitizen: int
    Partner: str
    Dependents: str
    tenure: int
    PhoneService: str
    MultipleLines: str
    InternetService: str
    OnlineSecurity: str
    OnlineBackup: str
    DeviceProtection: str
    TechSupport: str
    StreamingTV: str
    StreamingMovies: str
    Contract: str
    PaperlessBilling: str
    PaymentMethod: str
    MonthlyCharges: float
    TotalCharges: str  # Kept as str to handle blank spaces from raw data


class BatchRequest(BaseModel):
    """Batch of customers + optional top-N filter."""
    customers: list[CustomerData] = Field(..., min_length=1)
    top_n: Optional[int] = Field(default=None, ge=1)


class PredictionOut(BaseModel):
    """Single prediction result."""
    customer_id: str
    churn_probability: float
    prediction: str
    confidence: float
    model_version: str
    timestamp: datetime
    request_id: str


class BatchOut(BaseModel):
    """Batch prediction result."""
    predictions: list[PredictionOut]
    total_processed: int
    total_returned: int
    model_version: str
    timestamp: datetime
    request_id: str


# ============================================================================
# MODEL INTERFACE  (ABC — the swap point)
# ============================================================================


class ChurnModel(ABC):
    """Any model (mock or real) must implement these 3 methods."""

    @abstractmethod
    def predict(self, features: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def predict_batch(self, features_list: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_info(self) -> dict[str, str]: ...

    @abstractmethod
    def is_ready(self) -> bool: ...


# ============================================================================
# REAL MODEL  (replace this class with your real model later)
# ============================================================================


class RealChurnModel(ChurnModel):
    def __init__(self):
        try:
            self.model = joblib.load("model.pkl")
        except Exception:
            self.model = None

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        # 1. Convert incoming dict to DataFrame
        df_raw = pd.DataFrame([features])
        
        # 2. Add dummy target column because clean_data expects it to exist for encoding
        df_raw['Churn'] = 'No'
        
        # 3. Clean and engineer features
        df_clean = clean_data(df_raw)
        
        # 4. Drop target to get final features
        X = df_clean.drop(columns=['Churn'])
        
        # 5. Get probability
        prob = self.model.predict_proba(X)[0][1]

        return {
            "churn_probability": float(prob),
            "prediction": "Yes" if prob >= 0.5 else "No",
            "confidence": float(abs(prob - 0.5) * 2),
        }

    def predict_batch(self, features_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not features_list:
            return []
            
        df_raw = pd.DataFrame(features_list)
        df_raw['Churn'] = 'No'
        df_clean = clean_data(df_raw)
        X = df_clean.drop(columns=['Churn'])
        
        # Vectorized probability prediction
        probs = self.model.predict_proba(X)[:, 1]
        
        results = []
        for prob in probs:
            results.append({
                "churn_probability": float(prob),
                "prediction": "Yes" if prob >= 0.5 else "No",
                "confidence": float(abs(prob - 0.5) * 2),
            })
        return results

    def get_info(self) -> dict[str, str]:
        return {"name": "real_rf_model", "version": MODEL_VERSION, "type": "random_forest"}

    def is_ready(self) -> bool:
        return self.model is not None


# ============================================================================
# MLFLOW HELPER
# ============================================================================


class MLflowTracker:
    """Thin wrapper around MLflow — failures never crash predictions."""

    def __init__(self) -> None:
        self._ok = False

    def init(self) -> None:
        try:
            mlflow.set_tracking_uri(MLFLOW_URI)
            if not mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT):
                mlflow.create_experiment(MLFLOW_EXPERIMENT)
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
            self._ok = True
            log.info("MLflow ready  → %s", MLFLOW_URI)
        except Exception as e:
            log.warning("MLflow init failed: %s", e)

    def track(self, *, tags: dict, params: dict, metrics: dict, run_name: str) -> None:
        if not self._ok:
            return
        try:
            with mlflow.start_run(run_name=run_name):
                mlflow.set_tags(tags)
                mlflow.log_params({k: str(v) for k, v in params.items()})
                mlflow.log_metrics(metrics)
        except Exception as e:
            log.warning("MLflow tracking failed: %s", e)


# ============================================================================
# APPLICATION STATE  (singletons created at startup)
# ============================================================================

model: ChurnModel = RealChurnModel()
tracker = MLflowTracker()
_start_time: float = 0.0


# ============================================================================
# FASTAPI APP
# ============================================================================


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    global _start_time
    _setup_logging()
    _start_time = time.time()
    tracker.init()
    log.info("🚀 %s v%s started", APP_NAME, APP_VERSION)
    yield
    log.info("👋 %s shutting down", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "**RetainIQ** — Customer Churn Prediction API.\n\n"
        "⚠️ Currently using a **Real Model**. "
        "The real trained model will replace it with zero API changes."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get("/", tags=["Status"], summary="Service status")
def root():
    """Basic service status."""
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Status"], summary="Health check")
def health():
    """Model status, uptime, version."""
    info = model.get_info()
    return {
        "status": "healthy" if model.is_ready() else "degraded",
        "model_loaded": model.is_ready(),
        "model_version": info["version"],
        "uptime_seconds": round(time.time() - _start_time, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/predict", response_model=PredictionOut, tags=["Predictions"], summary="Single prediction")
def predict(customer: CustomerData):
    """Predict churn for one customer."""
    if not model.is_ready():
        raise HTTPException(503, "Model not loaded")

    rid = str(uuid.uuid4())
    start = time.perf_counter()

    features = customer.model_dump()
    cid = features["customerID"]

    result = model.predict(features)
    latency = (time.perf_counter() - start) * 1000
    info = model.get_info()
    now = datetime.now(timezone.utc)

    # Log prediction
    log_prediction({
        "timestamp": now.isoformat(), "request_id": rid, "customerID": cid,
        "prediction": result["prediction"], "churn_probability": result["churn_probability"],
        "confidence": result["confidence"], "latency_ms": round(latency, 2),
        "model_version": info["version"],
    })

    # Track in MLflow
    tracker.track(
        run_name=f"predict_{cid}",
        tags={"request_id": rid, "customerID": cid, "type": "single"},
        params=features,
        metrics={"churn_probability": result["churn_probability"], "confidence": result["confidence"]},
    )

    log.info("predict | %s | prob=%.4f | %.1fms", cid, result["churn_probability"], latency)

    return PredictionOut(
        customerID=cid, **result,
        model_version=info["version"], timestamp=now, request_id=rid,
    )


@app.post("/batch_predict", response_model=BatchOut, tags=["Predictions"], summary="Batch prediction")
def batch_predict(req: BatchRequest):
    """
    Predict churn for a batch of customers.

    Returns the **top N highest-risk** customers sorted by churn probability.

    **Why Batch Scoring?**
    Retention campaigns run daily/weekly, not in real-time.
    Batch scoring processes everyone at once, ranks them by risk,
    and feeds a prioritised list to the retention team.
    """
    if len(req.customers) > BATCH_MAX:
        raise HTTPException(400, f"Batch size {len(req.customers)} exceeds max {BATCH_MAX}")
    if not model.is_ready():
        raise HTTPException(503, "Model not loaded")

    rid = str(uuid.uuid4())
    start = time.perf_counter()
    info = model.get_info()
    now = datetime.now(timezone.utc)

    predictions = []
    features_list = []
    cids = []
    
    for c in req.customers:
        features = c.model_dump()
        cid = features["customerID"]
        for k, v in features.items():
            if hasattr(v, "value"):
                features[k] = v.value
        features_list.append(features)
        cids.append(cid)
        
    results = model.predict_batch(features_list)
    
    for cid, result in zip(cids, results):
        predictions.append(PredictionOut(
            customer_id=cid, **result,
            model_version=info["version"], timestamp=now, request_id=rid,
        ))

    # Sort highest risk first, take top N
    predictions.sort(key=lambda p: p.churn_probability, reverse=True)
    top_n = req.top_n or BATCH_DEFAULT_TOP_N
    returned = predictions[:top_n]
    latency = (time.perf_counter() - start) * 1000

    # Log
    log_prediction({
        "timestamp": now.isoformat(), "request_id": rid, "event": "batch",
        "total": len(req.customers), "returned": len(returned),
        "latency_ms": round(latency, 2), "model_version": info["version"],
    })

    # Track
    avg_prob = sum(p.churn_probability for p in predictions) / len(predictions)
    tracker.track(
        run_name=f"batch_{rid[:8]}",
        tags={"request_id": rid, "type": "batch"},
        params={"total": str(len(req.customers)), "top_n": str(top_n)},
        metrics={"avg_churn_prob": avg_prob, "high_risk": sum(1 for p in predictions if p.prediction == "Yes"), "latency_ms": latency},
    )

    log.info("batch | total=%d | returned=%d | %.1fms", len(req.customers), len(returned), latency)

    return BatchOut(
        predictions=returned,
        total_processed=len(req.customers),
        total_returned=len(returned),
        model_version=info["version"],
        timestamp=now, request_id=rid,
    )


# ============================================================================
# RUN DIRECTLY:  python api.py
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
