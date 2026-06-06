## 2024-05-15 - Hardened Deployment Probes
**Cluster Quirk:** The deployments were using identical HTTP probes for liveness and readiness, and background workers had unnecessary readiness probes.
**Learning:** Using identical liveness and readiness probes is dangerous. Under load, a slow response might fail liveness, causing the container to restart when it just needed time to process. Background daemons without services don't need readiness probes.
**Resilience:** Differentiate probes: use `tcpSocket` for liveness to check if the process is alive, and `httpGet` for readiness to check if it's ready to serve traffic. Remove readiness probes for background workers.

## 2024-05-24 - Identical Liveness and Readiness Probes (Hardening)
**Cluster Quirk:** The `dd-app` deployment uses identical `httpGet` probes for both readiness and liveness.
**Learning:** Using the same probe is dangerous because a temporary application busy state causing readiness to fail will also cause liveness to fail, resulting in a pod restart instead of gracefully halting traffic.
**Resilience:** Configure liveness probes to use `tcpSocket` to only restart pods on hard crashes, preserving `httpGet` for accurate readiness checks.

## 2024-05-24 - Streamlit Deadlock Liveness Probe
**Cluster Quirk:** TCP socket probes pass even when Streamlit's Python event loop is deadlocked.
**Learning:** A deadlocked Streamlit app remains in the cluster receiving traffic but failing to serve users, as the `tcpSocket` check does not verify internal application state.
**Resilience:** Replace `tcpSocket` with `httpGet` on `/_stcore/health` to enforce application-layer failure detection and trigger pod restarts on deadlock.

## 2024-05-24 - Differentiating Liveness and Readiness Probes in Streamlit
**Cluster Quirk:** The `dd-app` deployment was triggering a warning from `kube-score` for using identical `httpGet` probes for both readiness and liveness.
**Learning:** Using the same probe is dangerous because a temporary application busy state causing readiness to fail will also cause liveness to fail, resulting in a pod restart instead of gracefully halting traffic.
**Resilience:** Configure readiness probes to hit the application root path (`/`) to check serving ability while preserving the memory-mandated `httpGet` liveness probe on `/_stcore/health` to detect Streamlit deadlocks.

## 2026-06-01 - Prevent Streamlit Probe Re-renders
**Cluster Quirk:** The dd-app deployment was using the root path / for its readiness probe.
**Learning:** In Streamlit applications on Kubernetes, probing / triggers a full frontend re-render on every check, causing severe performance bottlenecks.
**Resilience:** Use /_stcore/health for both readiness and liveness probes to prevent unnecessary UI renders while accurately assessing pod health.

## 2026-06-03 - Streamlit Startup
**Cluster Quirk:** Streamlit initialization is slow.
**Learning:** Premature liveness probe kills can occur during heavy initial loading.
**Resilience:** Added startupProbe to accommodate the initialization burst.

## 2024-05-24 - Hardened Redis Readiness and Liveness Probes
**Cluster Quirk:** A basic `redis-cli ping` execution for readiness/liveness probes is insufficient because it returns a successful exit code (0) even when Redis is still starting up and returning `(error) LOADING`.
**Learning:** The Kubernetes scheduler relies on accurate probes to route traffic only to ready pods. A successful probe exit code during startup causes premature traffic routing and potential failure cascades.
**Resilience:** Use `sh -c "redis-cli ping | grep PONG"` to verify genuine readiness by checking for the exact `PONG` response string, preventing premature routing.
