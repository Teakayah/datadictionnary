# Secret rotation runbook

Procedure for rotating credentials stored in the `dd-app-secrets` Kubernetes Secret without downtime. The rolling update strategy (`maxUnavailable: 0`) ensures at least one pod stays healthy throughout.

All commands assume `kubectl` is configured for the target cluster and your shell context is set to the correct namespace, or you append `-n data-dictionary` explicitly.

---

## 1. Rotate the Databricks PAT token

### When to do this

- Quarterly as a matter of policy
- Immediately if the token is suspected to be compromised
- When the token expires (PATs have a configurable TTL in Databricks)

### Steps

1. Generate a new PAT in the Databricks workspace UI under **Settings > Developer > Access tokens**.

2. Base64-encode the new token:

   ```bash
   echo -n '<new-databricks-token>' | base64
   ```

3. Patch the secret in place (no pod restart required at this step):

   ```bash
   kubectl patch secret dd-app-secrets \
     --namespace data-dictionary \
     --type='json' \
     -p='[{"op":"replace","path":"/data/DATABRICKS_TOKEN","value":"<base64-encoded-token>"}]'
   ```

4. Trigger a rolling restart so pods pick up the new value:

   ```bash
   kubectl rollout restart deployment/dd-app -n data-dictionary
   ```

5. Watch the rollout complete:

   ```bash
   kubectl rollout status deployment/dd-app -n data-dictionary
   ```

6. Verify the new token works by tailing a pod's logs and confirming no auth errors:

   ```bash
   kubectl logs -n data-dictionary -l app=dd-app -f --max-log-requests=2
   ```

7. Revoke the old token in the Databricks UI.

---

## 2. Rotate the Entra ID client secret

### When to do this

- When the secret is approaching its expiry date (check in Azure Portal > App registrations > Certificates & secrets)
- Immediately if the secret is suspected to be compromised

### Steps

1. In Azure Portal, navigate to your app registration and create a new client secret. Copy the **Value** (it is only shown once).

2. Base64-encode the new secret:

   ```bash
   echo -n '<new-client-secret>' | base64
   ```

3. Patch the Kubernetes secret:

   ```bash
   kubectl patch secret dd-app-secrets \
     --namespace data-dictionary \
     --type='json' \
     -p='[{"op":"replace","path":"/data/CLIENT_SECRET","value":"<base64-encoded-secret>"}]'
   ```

4. Restart the deployment:

   ```bash
   kubectl rollout restart deployment/dd-app -n data-dictionary
   kubectl rollout status deployment/dd-app -n data-dictionary
   ```

5. Test the OIDC login flow end-to-end by signing in as a test user.

6. Delete the old secret from the Azure Portal app registration.

---

## 3. Rotate the GHCR image pull secret

### When to do this

- When the GitHub personal access token (PAT) used for GHCR access expires or is revoked
- When rotating PATs as part of a broader credential hygiene exercise

### Steps

1. Generate a new GitHub PAT with `read:packages` scope at **GitHub > Settings > Developer settings > Personal access tokens**.

2. Delete the existing pull secret:

   ```bash
   kubectl delete secret ghcr-pull-secret -n data-dictionary
   ```

3. Recreate it with the new token:

   ```bash
   kubectl create secret docker-registry ghcr-pull-secret \
     --namespace data-dictionary \
     --docker-server=ghcr.io \
     --docker-username=<github-username> \
     --docker-password=<new-ghcr-token>
   ```

4. The secret is read at image-pull time, so a restart is only needed if the current pods are crash-looping due to `ImagePullBackOff`. In steady state, existing pods are unaffected:

   ```bash
   kubectl get pods -n data-dictionary -l app=dd-app
   ```

5. Confirm new pods (triggered by the next deploy) can pull the image:

   ```bash
   kubectl describe pod -n data-dictionary -l app=dd-app | grep -A5 "Events"
   ```

---

## Verification checklist

After any secret rotation, confirm the following before closing the change:

- [ ] `kubectl rollout status deployment/dd-app -n data-dictionary` reports `successfully rolled out`
- [ ] Pod logs show no authentication errors in the first two minutes after restart
- [ ] A test search returns results (Databricks / DuckDB connection is live)
- [ ] OIDC sign-in flow completes without errors (Entra ID rotation only)
- [ ] Old credential has been revoked in the originating system
