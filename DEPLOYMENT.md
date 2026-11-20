# Deployment runbook

Operations reference for the `data-dictionary` Kubernetes deployment.

---

## 1. First-time cluster setup

Apply manifests in dependency order so each resource exists before the next references it.

```bash
# 1. Namespace — must exist before everything else
kubectl apply -f k8s/namespace.yaml

# 2. Default ServiceAccount (disables automounted token)
kubectl apply -f k8s/serviceaccount.yaml

# 3. Network policies — restrict ingress/egress before workloads start
kubectl apply -f k8s/networkpolicies.yaml

# 4. Resource quota — enforce namespace-level limits
kubectl apply -f k8s/resourcequota.yaml

# 5. Persistent volume claims (DuckDB cache file + Redis cache)
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/pvc-redis.yaml

# 6. Secrets (Databricks creds, Entra ID, GHCR pull secret)
kubectl apply -f k8s/secret.yaml

# 7. ConfigMap (non-sensitive env vars)
kubectl apply -f k8s/configmap.yaml

# 8. Deployments — Redis, Streamlit UI, REST/MCP API, and sidecar sync worker
kubectl apply -f k8s/deployment-redis.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/deployment-sync-worker.yaml

# 9. PodDisruptionBudget (keep ≥1 dd-api replica during node drains)
kubectl apply -f k8s/pdb.yaml

# 10. Services
kubectl apply -f k8s/service-redis.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/service-api.yaml

# 11. Ingress
kubectl apply -f k8s/ingress.yaml

# 12. Horizontal Pod Autoscaler (dd-api)
kubectl apply -f k8s/hpa.yaml

# 13. CronJob (nightly full catalog rebuild)
kubectl apply -f k8s/cronjob.yaml
```

Or apply everything at once after the first run:

```bash
kubectl apply -f k8s/
```

**Two sync paths, intentionally distinct.** `dd-sync-worker`
(`python -m src.sync.daemon`) is the long-lived in-cluster process that
drains `user_data.pending_sync` to Databricks on a 5–30 s cadence and
runs DR resync every ~10 minutes. The `dd-sync` CronJob is a separate
nightly rebuild of the catalog cache (`scripts/sync_metadata.py` —
full re-crawl of Unity Catalog). They run at different cadences and
solve different problems. See `docs/runbooks/sync-worker.md` for the
daemon's operations runbook (healthz, queue inspection, common failure
modes).

### Populating secrets

Create the application secret from literal values:

```bash
kubectl create secret generic dd-secrets \
  --namespace data-dictionary \
  --from-literal=DATABRICKS_HOST="https://<workspace>.azuredatabricks.net" \
  --from-literal=DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/<id>" \
  --from-literal=DATABRICKS_TOKEN="<pat>" \
  --from-literal=TENANT_ID="<entra-tenant-id>" \
  --from-literal=CLIENT_ID="<app-registration-client-id>" \
  --from-literal=CLIENT_SECRET="<app-registration-secret>" \
  --from-literal=REDIRECT_URI="https://datadictionary.internal/"
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
kubectl patch secret dd-secrets \
  --namespace data-dictionary \
  --type='json' \
  -p='[{"op":"replace","path":"/data/DATABRICKS_TOKEN","value":"'"$(echo -n '<new-token>' | base64)"'"}]'
```

Or delete and recreate (causes a brief pod restart):

```bash
kubectl delete secret dd-secrets -n data-dictionary
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

The rollback does not affect the CronJob or the DuckDB cache on the PVC. If the metadata in the cache is also suspect, trigger a manual sync after the rollback:

```bash
kubectl create job --from=cronjob/dd-sync post-rollback-sync-$(date +%s) \
  -n data-dictionary
```

---

## 5. Scaling manually

`dd-app` is intentionally kept at `replicas: 1` until mutable `user_data` storage is moved off shared DuckDB files (see `TODO.md`). `dd-api` is stateless/read-only and is autoscaled by `k8s/hpa.yaml`.

Override the `dd-api` HPA and set a fixed replica count:

```bash
kubectl scale deployment/dd-api --replicas=4 -n data-dictionary
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

---

## 9. Local development quickstart

This section covers running the app on a laptop without a Kubernetes cluster or Databricks connection.

### Generate the test dataset

The test dataset is a pre-populated DuckDB file that seeds the app with realistic demo data across four departments.

```bash
python scripts/generate_test_data.py --seed 42 --out data/test_data.duckdb
```

The `--seed 42` flag produces a deterministic dataset (800 tables, four departments: finance, research, hr, it). Use a different seed to vary the data. Add `--with-data` to include sample row data that enables the data preview dialog.

### Configure the local environment

Add the following to your `.env` file (or export as shell variables):

```bash
DUCKDB_PATH=data/test_data.duckdb
ENABLE_MOCK_AUTH=true
ENVIRONMENT=development
DEMO_DATA=true
EDITOR_GROUPS=finance_dept_id
ADMIN_GROUPS=finance_dept_id
```

`DUCKDB_PATH` tells the app to serve all queries from the local file instead of opening a network connection to Databricks.

### Start the app

```bash
streamlit run app.py
```

### Mock authentication

When `ENABLE_MOCK_AUTH=true` and `ENVIRONMENT=development` are set, the sign-in page renders four department login buttons instead of the Entra ID redirect:

| Button | Groups injected | Visible tables |
|--------|----------------|----------------|
| Finance | `finance_dept_id`, `all_employees_id` | Finance + public |
| Research | `research_dept_id`, `all_employees_id` | Research + public |
| HR | `hr_dept_id`, `all_employees_id` | HR + public |
| IT | `it_dept_id`, `all_employees_id` | IT + public |

Each button sets `st.session_state.user_groups` to the corresponding list. The permission JOIN in every search query then filters results to only the tables those groups are authorized to see, exactly as in production.

No Databricks credentials are needed for local development. The sync job does not need to run if `DUCKDB_PATH` points to the pre-generated test file.
