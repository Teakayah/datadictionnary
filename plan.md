1. **Fix NetworkPolicy egress rules for `dd-app`**
   - The `dd-app-network-policy` in `k8s/networkpolicies.yaml` does not have an egress rule to allow `dd-app` to communicate with `dd-api`. However, the API network policy ingress rules explicitly mention "Intra-cluster callers within this namespace (e.g. dd-app sidecar calls)", implying `dd-app` needs to communicate with `dd-api` on port 8080.
   - Without this egress rule, `dd-app` cannot make internal calls to `dd-api`, potentially breaking functionality in the UI sidecar architecture. We will add an egress rule for `dd-api` on port 8080 to `dd-app-network-policy`.

2. **Verify changes**
   - Run `kubectl apply --dry-run=client -f k8s/networkpolicies.yaml` to ensure the YAML is syntactically valid.

3. **Complete pre-commit steps**
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.

4. **Submit PR**
   - Submit the PR using the `request_code_review` tool.
