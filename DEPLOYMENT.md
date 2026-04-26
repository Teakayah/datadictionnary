# Deployment runbook

Operations reference for the `data-dictionary` Kubernetes deployment.

---

## 1. First-time cluster setup

Apply manifests in dependency order so each resource exists before the next references it.

```bash
# 1. Namespace — must exist before everything else
kubectl apply -f k8s/namespace.yaml

# 2. Persistent volume claim (DuckDB cache file)
kubectl apply -f k8s/pvc.yaml

# 3. Secrets (Databricks creds, Entra ID, GHCR pull secret)
kubectl apply -f k8s/secret.yaml

# 4. ConfigMap (non-sensitive env vars)
kubectl apply -f k8s/configmap.yaml

# 5. Deployment
kubectl apply -f k8s/deployment.yaml

# 6. Service
kubectl apply -f k8s/service.yaml

# 7. Ingress
kubectl apply -f k8s/ingress.yaml

# 8. Horizontal Pod Autoscaler
kubectl apply -f k8s/hpa.yaml

# 9. CronJob (metadata sync)
kubectl apply -f k8s/cronjob.yaml
```

Or apply everything at once after the first run:

```bash
kubectl apply -f k8s/
```

### Populating secrets

Create the application secret from literal values:

```bash
kubectl create secret generic dd-app-secrets \
  --namespace data-dictionary \
  --from-literal=DATABRICKS_HOST="https://<workspace>.azuredatabricks.net" \
  --from-literal=DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/<id>" \
  --from-literal=DATABRICKS_TOKEN="<pat>" \
  --from-literal=TENANT_ID="<entra-tenant-id>" \
  --from-literal=CLIENT_ID="<app-registration-client-id>" \
  --from-literal=CLIENT_SECRET="<app-registration-secret>" \
  --from-literal=REDIRECT_URI="https://data-dictionary.your-domain.com/callback"
```

Create the GHCR image pull secret:

```bash
kubectl create secret docker-registry ghcr-pull-secret \
  --namespace data-dictionary \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<GHCR_TOKEN>
```

---

## 2. Updating secrets

Patch a single key without recreating the whole secret:

```bash
kubectl patch secret dd-app-secrets \
  --namespace data-dictionary \
  --type='json' \
  -p='[{"op":"replace","path":"/data/DATABRICKS_TOKEN","value":"'"$(echo -n '<new-token>' | base64)"'"}]'
```

Or delete and recreate (causes a brief pod restart):

```bash
kubectl delete secret dd-app-secrets -n data-dictionary
# Re-run the kubectl create secret ... command from section 1
kubectl rollout restart deployment/dd-app -n data-dictionary
```

---

## 3. Triggering a manual metadata sync

Create a one-off Job from the existing CronJob definition:

```bash
kubectl create job --from=cronjob/dd-sync manual-sync-$(date +%s) \
  -n data-dictionary
```

Watch the job logs:

```bash
kubectl logs -n data-dictionary -l job-name=manual-sync-<timestamp> -f
```

Delete the job once done:

```bash
kubectl delete job manual-sync-<timestamp> -n data-dictionary
```

---

## 4. Rolling back a deployment

Undo to the previous ReplicaSet revision:

```bash
kubectl rollout undo deployment/dd-app -n data-dictionary
```

Undo to a specific revision (list history first):

```bash
kubectl rollout history deployment/dd-app -n data-dictionary
kubectl rollout undo deployment/dd-app -n data-dictionary --to-revision=<N>
```

Confirm the rollback completed:

```bash
kubectl rollout status deployment/dd-app -n data-dictionary
kubectl get pods -n data-dictionary -l app=dd-app
```

---

## 5. Scaling manually

Override the HPA and set a fixed replica count:

```bash
kubectl scale deployment/dd-app --replicas=4 -n data-dictionary
```

To re-enable autoscaling after a manual override, patch the HPA min/max or simply delete and re-apply `k8s/hpa.yaml`.

---

## 6. Port-forwarding for local debug

Forward the Streamlit port (default 8501) to localhost:

```bash
kubectl port-forward deployment/dd-app 8501:8501 -n data-dictionary
```

Then open `http://localhost:8501` in your browser. The app runs with whatever env vars are injected into the pod — including real Databricks credentials.

To forward to a specific pod:

```bash
POD=$(kubectl get pod -n data-dictionary -l app=dd-app -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward pod/$POD 8501:8501 -n data-dictionary
```

---

## 7. Monitoring

### Health check

Streamlit exposes a built-in health endpoint:

```
GET /_stcore/health
```

Expected response: `ok` (HTTP 200).

```bash
curl -sf https://data-dictionary.your-domain.com/_stcore/health && echo "healthy"
```

### Load test smoke command

Quick sanity check (requires `hey` or `wrk`):

```bash
# 50 concurrent users, 200 total requests
hey -c 50 -n 200 https://data-dictionary.your-domain.com/_stcore/health
```

### Streaming pod logs

```bash
# All pods matching the app label
kubectl logs -n data-dictionary -l app=dd-app -f --max-log-requests=10

# Single pod, previous container (after a crash)
kubectl logs -n data-dictionary <pod-name> --previous
```

### Events (useful after a failed rollout)

```bash
kubectl get events -n data-dictionary --sort-by='.lastTimestamp' | tail -30
```

---

## 8. Release process

1. Merge all changes to `main`. The `test → build → deploy` pipeline runs automatically and deploys the `sha-<commit>` image to the cluster.

2. When ready to cut a versioned release, tag `main`:

   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

3. The `release` job in GitHub Actions triggers automatically, builds the image tagged `v1.2.0` and `stable`, and creates a GitHub Release with an auto-generated changelog.

4. To deploy the release image to the cluster, update `k8s/deployment.yaml` to reference the new tag and push to `main` (or apply directly):

   ```bash
   sed -i 's|image: ghcr.io/org/data-dictionary:.*|image: ghcr.io/org/data-dictionary:v1.2.0|' k8s/deployment.yaml
   git commit -am "chore: deploy v1.2.0"
   git push
   ```
