{{- define "pdf-editor.name" -}}
{{- default .Chart.Name .Values.nameOverride -}}
{{- end -}}

{{- define "pdf-editor.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "pdf-editor.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pdf-editor.labels" -}}
app.kubernetes.io/name: {{ include "pdf-editor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "pdf-editor.secretName" -}}
{{ .Release.Name }}-secrets
{{- end -}}

{{- define "pdf-editor.configName" -}}
{{ .Release.Name }}-config
{{- end -}}
