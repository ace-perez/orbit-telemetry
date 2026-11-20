{{/*
Name helpers, following the layout `helm create` generates.
*/}}

{{- define "orbit-telemetry.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Full name: the release name, plus the chart name unless the release name already contains it.
Kubernetes names are capped at 63 characters.
*/}}
{{- define "orbit-telemetry.fullname" -}}
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

{{- define "orbit-telemetry.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels: must never change after the first install (Deployments cannot change them).
*/}}
{{- define "orbit-telemetry.selectorLabels" -}}
app.kubernetes.io/name: {{ include "orbit-telemetry.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "orbit-telemetry.labels" -}}
helm.sh/chart: {{ include "orbit-telemetry.chart" . }}
{{ include "orbit-telemetry.selectorLabels" . }}
app.kubernetes.io/version: {{ include "orbit-telemetry.imageTag" . | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: orbit-telemetry
{{- end }}

{{- define "orbit-telemetry.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "orbit-telemetry.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "orbit-telemetry.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{- define "orbit-telemetry.image" -}}
{{- printf "%s:%s" .Values.image.repository (include "orbit-telemetry.imageTag" .) }}
{{- end }}
