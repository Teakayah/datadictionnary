## 2024-05-15 - Hardened Deployment Probes
**Cluster Quirk:** The deployments were using identical HTTP probes for liveness and readiness, and background workers had unnecessary readiness probes.
**Learning:** Using identical liveness and readiness probes is dangerous. Under load, a slow response might fail liveness, causing the container to restart when it just needed time to process. Background daemons without services don't need readiness probes.
**Resilience:** Differentiate probes: use `tcpSocket` for liveness to check if the process is alive, and `httpGet` for readiness to check if it's ready to serve traffic. Remove readiness probes for background workers.
