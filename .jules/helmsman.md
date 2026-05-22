## 2024-05-24 - Identical Liveness and Readiness Probes
**Cluster Quirk:** The `dd-app` deployment uses identical `httpGet` probes for both readiness and liveness.
**Learning:** Using the same probe is dangerous because a temporary application busy state causing readiness to fail will also cause liveness to fail, resulting in a pod restart instead of gracefully halting traffic.
**Resilience:** Configure liveness probes to use `tcpSocket` to only restart pods on hard crashes, preserving `httpGet` for accurate readiness checks.
