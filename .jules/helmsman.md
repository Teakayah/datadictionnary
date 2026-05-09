## 2026-05-09 - [Streamlit ReadOnly Filesystem]
**Cluster Quirk:** Streamlit applications crash or fail health probes if the container's root filesystem is entirely read-only because it needs to write temporary runtime caches and multipart upload buffers.
**Learning:** You cannot simply set `readOnlyRootFilesystem: true` on Streamlit Pods without providing an alternative writable path for temporary files.
**Resilience:** Always mount an `emptyDir` volume specifically to `/tmp` in the container specification to satisfy Streamlit's runtime write requirements while keeping the primary OS filesystem locked down.
