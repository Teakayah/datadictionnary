{{/*
Expand the name of the chart.
*/}}
{{- define "data-dictionary.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "data-dictionary.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "data-dictionary.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Image tag defaults to Chart.AppVersion.
*/}}
{{- define "data-dictionary.imageTag" -}}
{{- default .Chart.AppVersion .Values.image.tag }}
{{- end }}

{{/*
Full container image reference.
*/}}
{{- define "data-dictionary.image" -}}
{{- printf "%s:%s" .Values.image.repository (include "data-dictionary.imageTag" .) }}
{{- end }}

{{/*
Common labels shared across all resources.
*/}}
{{- define "data-dictionary.labels" -}}
helm.sh/chart: {{ include "data-dictionary.chart" . }}
app.kubernetes.io/name: {{ include "data-dictionary.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ include "data-dictionary.imageTag" . | quote }}
app.kubernetes.io/part-of: {{ include "data-dictionary.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Component-specific selector labels. Call with dict "ctx" . "component" "app".
*/}}
{{- define "data-dictionary.selectorLabels" -}}
app.kubernetes.io/name: {{ include "data-dictionary.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "data-dictionary.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "data-dictionary.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
ConfigMap name.
*/}}
{{- define "data-dictionary.configMapName" -}}
{{- printf "%s-config" (include "data-dictionary.fullname" .) }}
{{- end }}

{{/*
Secret name.
*/}}
{{- define "data-dictionary.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- printf "%s-secrets" (include "data-dictionary.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Data PVC name.
*/}}
{{- define "data-dictionary.pvcName" -}}
{{- if .Values.storage.existingClaim }}
{{- .Values.storage.existingClaim }}
{{- else }}
{{- printf "%s-data" (include "data-dictionary.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Component resource full names.
*/}}
{{- define "data-dictionary.appFullname" -}}
{{- printf "%s-app" (include "data-dictionary.fullname" .) }}
{{- end }}

{{- define "data-dictionary.apiFullname" -}}
{{- printf "%s-api" (include "data-dictionary.fullname" .) }}
{{- end }}

{{- define "data-dictionary.syncWorkerFullname" -}}
{{- printf "%s-sync-worker" (include "data-dictionary.fullname" .) }}
{{- end }}

{{- define "data-dictionary.cronJobFullname" -}}
{{- printf "%s-sync" (include "data-dictionary.fullname" .) }}
{{- end }}

{{- define "data-dictionary.redisFullname" -}}
{{- printf "%s-redis" (include "data-dictionary.fullname" .) }}
{{- end }}

{{/*
Resolved REDIS_URL (externalUrl takes precedence over in-chart Redis service).
*/}}
{{- define "data-dictionary.redisUrl" -}}
{{- if .Values.redis.externalUrl }}
{{- .Values.redis.externalUrl }}
{{- else if .Values.redis.enabled }}
{{- printf "redis://%s:%d" (include "data-dictionary.redisFullname" .) (int .Values.redis.port) }}
{{- end }}
{{- end }}
