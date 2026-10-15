# Minikube demo: deploying ML services with kubectl, Kustomize and Helm

Companion demo for **MLOps CI/CD, Lesson 6** (Helm, Kustomize, MLflow in Kubernetes).
Everything runs locally on minikube. No AWS account is needed.

| Part | What it shows | Folder |
|------|---------------|--------|
| 1 | Manual deploy with `kubectl apply` | `01-kubectl/` |
| 2 | Environments with Kustomize overlays (dev / staging) | `02-kustomize/` |
| 3 | Your own Helm chart: install, upgrade, rollback, uninstall, optional HPA | `03-helm/my-chart/` |
| 4 | MLflow from a public Helm chart + `port-forward` | `04-mlflow/` |

Estimated time: 25 to 35 minutes. Run all commands from the folder that contains this README.

---

## 0. Prerequisites

You need `minikube`, `kubectl` and `helm` (v3) installed, plus Docker (or another minikube driver).

```bash
minikube start --cpus=2 --memory=4096
kubectl get nodes          # should show one node in Ready state
helm version
```

The demo app is `hashicorp/http-echo`. It is a tiny container that returns a fixed text, so you can see
at once which YAML or values produced the answer.

---

## 1. Manual deploy with `kubectl apply`

```bash
kubectl apply -f 01-kubectl/deployment.yaml
kubectl apply -f 01-kubectl/service.yaml

kubectl get deploy,pods,svc -l app=hello-ml
kubectl rollout status deploy/hello-ml
```

Open the app (leave the port-forward running in one terminal, call it from another):

```bash
kubectl port-forward svc/hello-ml 8080:80
curl http://localhost:8080          # Hello from plain kubectl apply
```

Talking point: to change anything (replicas, text, image) you edit YAML by hand and re-apply.
There is no parameterisation, so a second environment means copying the files.

Clean up:

```bash
kubectl delete -f 01-kubectl/
```

---

## 2. Kustomize: one base, several environments

Preview what Kustomize generates (nothing is applied yet):

```bash
kubectl kustomize 02-kustomize/overlays/dev
kubectl kustomize 02-kustomize/overlays/staging
```

Apply both environments (each overlay also creates its own namespace):

```bash
kubectl apply -k 02-kustomize/overlays/dev
kubectl apply -k 02-kustomize/overlays/staging

kubectl get deploy,pods -n demo-dev
kubectl get deploy,pods -n demo-staging
```

dev runs 1 replica, staging runs 3 replicas, and each has its own text.

```bash
kubectl -n demo-dev     port-forward svc/hello-ml 8081:80    # curl localhost:8081 -> "...Kustomize DEV"
kubectl -n demo-staging port-forward svc/hello-ml 8082:80    # curl localhost:8082 -> "...Kustomize STAGING"
```

Talking point: the base YAML is written once, and overlays only describe the differences (DRY).
`kubectl apply -k` works because Kustomize is built into kubectl.

Clean up:

```bash
kubectl delete -k 02-kustomize/overlays/dev
kubectl delete -k 02-kustomize/overlays/staging
```

---

## 3. Your own Helm chart (`03-helm/my-chart`)

The chart has the same structure as in the lesson: `Chart.yaml`, `values.yaml`, `templates/`
(`deployment.yaml`, `service.yaml`, `_helpers.tpl`, plus an optional `hpa.yaml`).

### 3.1 Check before deploying

```bash
helm lint 03-helm/my-chart
helm template demo 03-helm/my-chart        # prints the rendered Kubernetes YAML
```

Look at the output: `{{ .Values.message }}`, `{{ .Values.replicaCount }}` etc. are now plain values.

### 3.2 Install

```bash
helm install demo 03-helm/my-chart -n demo-helm --create-namespace
helm list -n demo-helm
kubectl get deploy,pods,svc -n demo-helm

kubectl -n demo-helm port-forward svc/demo-my-chart 8080:80
curl http://localhost:8080          # Hello from Helm chart v1
```

Resource names come from the release name (`demo-my-chart`), so you can install the same chart twice
in one namespace without collisions:

```bash
helm install demo2 03-helm/my-chart -n demo-helm --set replicaCount=1 --set message="second release"
helm list -n demo-helm
helm uninstall demo2 -n demo-helm
```

### 3.3 Upgrade and rollback

```bash
helm upgrade demo 03-helm/my-chart -n demo-helm --set message="Hello from Helm chart v2" --set replicaCount=3
kubectl rollout status deploy/demo-my-chart -n demo-helm
curl http://localhost:8080     # restart the port-forward first; pods were replaced -> "...chart v2"

helm history demo -n demo-helm
helm rollback demo 1 -n demo-helm
helm history demo -n demo-helm          # revision 3 is a copy of revision 1
```

The idiom used in CI/CD pipelines is a single command that works for both the first install and later updates:

```bash
helm upgrade --install demo 03-helm/my-chart -n demo-helm --create-namespace --atomic
```

### 3.4 Bonus: autoscaling (the "scale with load" question from the lesson)

```bash
minikube addons enable metrics-server
helm upgrade demo 03-helm/my-chart -n demo-helm --set autoscaling.enabled=true
kubectl get hpa -n demo-helm            # TARGETS may show <unknown> for ~1 minute
```

Optional load generator (stop it with Ctrl+C):

```bash
kubectl run load -n demo-helm --rm -it --image=busybox:1.36 --restart=Never -- \
  /bin/sh -c "while true; do wget -q -O- http://demo-my-chart; done"
# in another terminal:
kubectl get hpa -n demo-helm -w
```

### 3.5 Uninstall

```bash
helm uninstall demo -n demo-helm
kubectl delete ns demo-helm
```

---

## 4. MLflow via Helm + port-forward

This part uses the public **community-charts/mlflow** chart. It is lightweight and its images pull without
registry changes. The metadata store is in memory, so runs disappear if the pod restarts. An optional
PostgreSQL variant is at the end.

### 4.1 Get the chart and look at its values (same flow as in the lesson)

```bash
helm repo add community-charts https://community-charts.github.io/helm-charts
helm repo update
helm show values community-charts/mlflow | less        # all available settings
# optional: unpack the chart to browse it like in the slides
helm pull community-charts/mlflow --untar
```

`04-mlflow/values-minikube.yaml` holds the only overrides we need (service port, resources).

### 4.2 Install

```bash
helm install mlflow community-charts/mlflow \
  -n mlflow --create-namespace \
  -f 04-mlflow/values-minikube.yaml

kubectl get pods -n mlflow -w            # wait for 1/1 Running, then Ctrl+C
kubectl logs deploy/mlflow -n mlflow
```

### 4.3 Open the UI

```bash
kubectl port-forward svc/mlflow 5000:80 -n mlflow
```

Open http://localhost:5000 in the browser.

### 4.4 Log a test run (optional)

```bash
pip install mlflow
python 04-mlflow/log_run.py
```

Refresh the UI: you should see the `helm-demo` experiment with one run and a `loss` metric curve.
The script logs only parameters and metrics, not artifacts. Artifact storage (S3/MinIO) needs extra values
and is out of scope for this demo.

### 4.5 Upgrade with different values

```bash
helm upgrade mlflow community-charts/mlflow -n mlflow -f 04-mlflow/values-minikube.yaml --set replicaCount=1 --set log.level=debug
helm history mlflow -n mlflow
```

### 4.6 Optional: persistent metadata in PostgreSQL

```bash
helm upgrade mlflow community-charts/mlflow -n mlflow -f 04-mlflow/values-postgres.yaml
kubectl get pods -n mlflow -w            # mlflow-postgresql-0 and the mlflow pod
```

Runs created before the upgrade are lost (they lived in memory). New runs survive pod restarts.
The password in `values-postgres.yaml` is a demo value. Real clusters should use Kubernetes Secrets.

### 4.7 Clean up

```bash
helm uninstall mlflow -n mlflow
kubectl delete pvc --all -n mlflow       # only needed if you used PostgreSQL
kubectl delete ns mlflow
```

---

## Full cleanup

```bash
minikube delete          # removes the whole local cluster
```

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| `ImagePullBackOff` | `kubectl describe pod <name>` shows the registry error. Check your internet connection or proxy. |
| `port-forward` stops after `helm upgrade` | The old pod was replaced. Run the port-forward command again. |
| HPA shows `<unknown>` | Wait about a minute and make sure `minikube addons enable metrics-server` succeeded. |
| MLflow pod `CrashLoopBackOff` | `kubectl logs deploy/mlflow -n mlflow`. Low memory is the usual cause, so start minikube with `--memory=4096`. |
| `localhost:5000` is already in use (macOS) | Use another local port, for example `kubectl port-forward svc/mlflow 5001:80 -n mlflow`, and change the URL in `log_run.py`. |

## Differences from the slides (on purpose)

- **Chart template:** the demo chart names resources with the release name, not `.Chart.Name`, and keeps the
  Service port and the container port as separate values (`service.port` / `service.targetPort`).
  The image tag is pinned instead of `latest`.
- **MLflow chart:** community-charts is used instead of Bitnami, because Bitnami's public catalog has changed.
  The values keys on the MLflow slides (`backendStore.database`, `defaultArtifactRoot` at top level) do not
  match either chart. For this chart the correct keys are `backendStore.postgres.*` or `postgresql.*` and
  `artifactRoot.defaultArtifactRoot`.
- **Service port:** the MLflow service listens on port 80, so the port-forward is `5000:80`, not `5000:5000`.

## Validation status

The files were validated offline: `helm lint`, `helm template` (including the HPA branch and the published
MLflow chart with both values files) and `kubectl kustomize` for both overlays. They have not been run
against a live minikube cluster, so run through the steps once before presenting.
