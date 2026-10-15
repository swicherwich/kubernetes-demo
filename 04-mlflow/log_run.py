"""Logs one demo run (params + metrics only) to MLflow behind port-forward.

Usage:
    pip install mlflow
    kubectl port-forward svc/mlflow 5000:80     # in another terminal
    python log_run.py
"""
import math
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("helm-demo")

with mlflow.start_run(run_name="minikube-smoke-test"):
    mlflow.log_param("model", "demo")
    mlflow.log_param("learning_rate", 0.01)
    for step in range(10):
        mlflow.log_metric("loss", math.exp(-step / 3), step=step)
print("Done. Open http://localhost:5000 and look at the 'helm-demo' experiment.")
