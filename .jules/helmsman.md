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

## 2024-05-18 - NetworkPolicy Health Probes
**Cluster Quirk:** Kubelet health probes might appear blocked by default-deny NetworkPolicies, leading to a temptation to add broad ingress rules.
**Learning:** Kubelet traffic is typically exempt via the CNI (e.g., Calico, Cilium).
**Resilience:** Never create an `ingress` NetworkPolicy rule with `ports` but no `from` selector just to explicitly allow health probes, as this creates a severe vulnerability by opening the port to all namespaces. Rely on the CNI exemption.
## 2024-05-15 - Redis ReadOnlyRootFilesystem

**Cluster Quirk:** The standard `redis:alpine` container images default to mounting the root filesystem as writable, even though Redis only needs write access to specific data and tmp volumes.
**Learning:** Running containers with a writable root filesystem significantly increases the blast radius if an attacker achieves remote code execution.
**Resilience:** Always set `securityContext.readOnlyRootFilesystem: true` in the pod spec. For Redis, ensure that the persistence directory (e.g., `/data`) and `/tmp` are mounted as volumes to satisfy runtime write requirements without exposing the entire OS.
## 2024-05-24 - Hardened Redis Deployment Security and Limits
**Cluster Quirk:** The `dd-redis` deployment was using a low UID/GID (999) and missing ephemeral storage limits.
**Learning:** Using a UID/GID below 10000 can conflict with host users. Missing ephemeral storage limits can lead to node disk exhaustion (resource DDOS).
**Resilience:** Always configure `runAsUser` and `runAsGroup` to a value > 10000, and explicitly define `ephemeral-storage` requests and limits to ensure node stability.
## 2026-06-21 - Hardened Deployment Probes
**Cluster Quirk:** The deployments were using identical HTTP or exec probes for liveness and readiness, triggering kube-score warnings.
**Learning:** Using the exact same probe for liveness and readiness is dangerous. Under load, a slow response might fail readiness (which should just gracefully halt incoming traffic) but will also fail the identical liveness check (which brutally kills and restarts the pod), causing a cascading failure loop.
**Resilience:** Differentiate liveness and readiness probes by using dedicated paths (like `/health/live` and `/health/ready`) or adding query parameters to allow application-aware liveness checks without downgrading to basic `tcpSocket` checks.
## 2024-06-25 - Shell Probes in Read-Only Filesystems
**Cluster Quirk:** Shell-based `exec` probes fail when the container is run with `readOnlyRootFilesystem: true`.
**Learning:** Utilities used in shell-based `exec` probes (like `sh -c`) often require temporary write access. When the root filesystem is read-only, these utilities cannot execute, causing health checks to fail.
**Resilience:** Explicitly mount an `emptyDir` volume at `/tmp` to ensure these shell probes function properly in secured containers.

## 2024-05-15 - Redis ReadOnlyRootFilesystem
**Cluster Quirk:** The standard `redis:alpine` container images default to mounting the root filesystem as writable, even though Redis only needs write access to specific data and tmp volumes.
**Learning:** Running containers with a writable root filesystem significantly increases the blast radius if an attacker achieves remote code execution.
**Resilience:** Always set `securityContext.readOnlyRootFilesystem: true` in the pod spec. For Redis, ensure that the persistence directory (e.g., `/data`) and `/tmp` are mounted as volumes to satisfy runtime write requirements without exposing the entire OS.

## 2026-07-01 - Redis emptyDir mount for exec probes
**Cluster Quirk:** The redis deployment uses readOnlyRootFilesystem but lacks an emptyDir mount at /tmp for its exec probes.
**Learning:** When securing Kubernetes containers with readOnlyRootFilesystem: true, shell-based exec probes (e.g., sh -c) often fail due to utilities requiring temporary write access.
**Resilience:** Ensure these probes function properly by explicitly mounting an emptyDir volume at /tmp.

## 2026-07-06 - Hardened Redis Liveness Probes
**Cluster Quirk:** The redis deployment was using identical resource-intensive `exec` checks for both liveness and readiness probes.
**Learning:** Under heavy load, identical resource-intensive `exec` probes can cause simultaneous failures. A slow response might fail readiness (which gracefully halts traffic) but will also fail the identical liveness check, causing a hard pod restart.
**Resilience:** Differentiate them by using a lightweight `tcpSocket` check for liveness to only restart pods on hard crashes, preserving `exec` for accurate readiness checks.

## 2024-05-24 - Hardened Redis Deployment Liveness Probe
**Cluster Quirk:** The `dd-redis` deployment was using a basic `tcpSocket` check on port 6379 for its liveness probe.
**Learning:** A TCP connection check only verifies that the port is open and accepting network connections. It passes even if the underlying Redis event loop is deadlocked or entirely unresponsive to commands, meaning a failing pod won't be restarted automatically by Kubernetes.
**Resilience:** Replaced the `tcpSocket` probe with an `exec` probe running `["redis-cli", "ping"]`. This ensures the application layer is actively processing commands, allowing the kubelet to detect actual deadlocks and restart the container when necessary.

## 2024-05-25 - Strict podAntiAffinity for High Availability
**Cluster Quirk:** The high-availability deployments (`dd-app` and `dd-api`) lacked strict rules to prevent all replicas from scheduling on the same node, relying only on soft topology spread constraints.
**Learning:** If all replicas are scheduled onto a single node due to scheduling availability, a single node failure would cause a complete outage of the application despite the HPA minimum replica count.
**Resilience:** Added `podAntiAffinity` with `requiredDuringSchedulingIgnoredDuringExecution` to both deployments to strictly enforce that replicas are scheduled across different nodes, ensuring true HA resilience.
## 2026-08-14 - HPA and Hard podAntiAffinity Deadlock
**Cluster Quirk:** The cluster is configured with HPA capable of scaling up `dd-app` significantly, but nodes are limited.
**Learning:** Combining HPA with `topologySpreadConstraints` and a hard `podAntiAffinity` (`requiredDuringSchedulingIgnoredDuringExecution`) creates a scheduling regression. If the HPA scales the deployment beyond the cluster's available node count, pods will hang in the `Pending` state.
**Resilience:** Replaced the hard `podAntiAffinity` with a soft `preferredDuringSchedulingIgnoredDuringExecution` to allow pods to schedule even when nodes must run multiple replicas, ensuring availability during traffic spikes.

## 2024-05-25 - Soft podAntiAffinity with HPA
**Cluster Quirk:** The `dd-api` deployment uses an HPA but lacked a soft `podAntiAffinity` configuration.
**Learning:** Using a hard `podAntiAffinity` (`requiredDuringSchedulingIgnoredDuringExecution`) with HPA can cause scheduling deadlocks when nodes are limited.
**Resilience:** Apply `preferredDuringSchedulingIgnoredDuringExecution` to improve high availability without risking deadlocks.

## 2024-05-24 - Hardened Redis Deployment Liveness Probe
**Cluster Quirk:** The `dd-redis` deployment was using a basic `tcpSocket` check on port 6379 for its liveness probe.
**Learning:** A TCP connection check only verifies that the port is open and accepting network connections. It passes even if the underlying Redis event loop is deadlocked or entirely unresponsive to commands, meaning a failing pod won't be restarted automatically by Kubernetes.
**Resilience:** Replaced the `tcpSocket` probe with an `exec` probe running `["redis-cli", "ping"]`. This ensures the application layer is actively processing commands, allowing the kubelet to detect actual deadlocks and restart the container when necessary.
## 2025-01-20 - dd-api missing PVC mount for DuckDB
**Cluster Quirk:** The `dd-api` deployment missed the `dd-data` PersistentVolumeClaim mount at `/data`, causing it to crash or fail when attempting to read the sync daemon's cache at `DUCKDB_PATH` (`/data/dictionary_cache.duckdb`).
**Learning:** ConfigMaps define paths correctly, but Kubernetes pods remain blind to persistent storage until explicitly mounted in the container's `volumeMounts` and defined in the pod's `volumes`. Without this, API queries to duckdb would silently fail.
**Resilience:** Mounted `dd-data` PVC to `/data` in `k8s/deployment-api.yaml`, aligning its storage topology with `dd-app` and `dd-sync-worker` for reliable read access to the cached catalog.
## 2024-05-24 - Fix Sync Daemon Liveness Probes
**Cluster Quirk:** The Kubernetes manifests use a query parameter in health checks (e.g. `/healthz?probe=liveness`) to identify probe types, but the application's simple HTTP server strictly checks for exactly `/healthz`. This strict check causes `404` errors in Kubernetes, leading to infinite restart loops for the pod.
**Learning:** Hardcoded full-path checks in basic HTTP servers break when orchestration systems append diagnostic query string parameters to probe endpoints. When we don't control the application logic or need a quick infrastructure-level fix, we must adjust the manifest to match the application's exact requirements.
**Resilience:** Removed the `?probe=...` query parameters from the `livenessProbe` and `readinessProbe` paths in the `dd-sync-worker` deployment manifest to ensure they match the application's strict `/healthz` route.
## 2026-10-08 - Hardened dd-app for DuckDB Singleton
**Cluster Quirk:** The `dd-app` deployment uses a DuckDB file, which only allows a single writer, but the Kubernetes manifest was configured with a `RollingUpdate` strategy, HPA scaling, and a PDB with `minAvailable: 1`.
**Learning:** DuckDB requires strict singleton access. Scaling beyond 1 replica or using `RollingUpdate` (which creates a second pod before terminating the first) causes file locks and data corruption. Furthermore, a PDB with `minAvailable: 1` on a singleton deployment permanently deadlocks node drains.
**Resilience:** Reconfigured `dd-app` to strictly `replicas: 1` with `strategy: Recreate`. Removed its HPA and PDB configurations to ensure it remains a safe singleton.
## 2024-10-14 - Removed Useless ReadinessProbe on Daemon
**Cluster Quirk:** The `dd-sync-worker` deployment, a background daemon with no Service, had a `readinessProbe` identical to its `livenessProbe`.
**Learning:** Background workers and daemons that do not serve network traffic via a Kubernetes Service do not benefit from a `readinessProbe`. Having an identical readiness probe just wastes kubelet resources and triggers false-positive failure cascades if the single endpoint responds slowly.
**Resilience:** Removed the `readinessProbe` from `dd-sync-worker` entirely, relying solely on the `livenessProbe` to restart the daemon if the internal loop deadlocks.
## 2024-05-18 - Stateless Streamlit HA over DuckDB
**Cluster Quirk:** The `dd-sync-worker` acts as a singleton DuckDB writer, leaving the `dd-app` Streamlit frontend as a read-only, stateless component backed by Redis cache.
**Learning:** Because `dd-app` only reads from DuckDB, it does not require a singleton lock (unlike `dd-sync-worker`) and can safely scale horizontally across nodes.
**Resilience:** Configure stateless frontends reading from singleton databases with `replicas: 2`, a `RollingUpdate` strategy, and a `PodDisruptionBudget` to ensure high availability during node drains.
