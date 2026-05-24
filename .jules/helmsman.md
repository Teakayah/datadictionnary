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
