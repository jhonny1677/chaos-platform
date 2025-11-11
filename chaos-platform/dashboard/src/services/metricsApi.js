import createInstance from './api'

const PROMETHEUS_URL = import.meta.env.VITE_PROMETHEUS_URL || 'http://localhost:9090'
const ALERTMANAGER_URL = import.meta.env.VITE_ALERTMANAGER_URL || 'http://localhost:9093'

const prometheusApi = createInstance(PROMETHEUS_URL)
const alertmanagerApi = createInstance(ALERTMANAGER_URL)

// ── Prometheus queries ────────────────────────────────────────────────────────

const query = (promql) => prometheusApi.get('/api/v1/query', { params: { query: promql } })
const queryRange = (promql, start, end, step = '15s') =>
  prometheusApi.get('/api/v1/query_range', { params: { query: promql, start, end, step } })

export const fetchPodStatus = (namespace = 'target-app') =>
  query(`kube_pod_info{namespace="${namespace}"}`)

export const fetchPodReadiness = (namespace = 'target-app') =>
  query(`kube_pod_status_ready{namespace="${namespace}",condition="true"}`)

export const fetchPodRestarts = (namespace = 'target-app') =>
  query(`kube_pod_container_status_restarts_total{namespace="${namespace}"}`)

export const fetchCpuUsage = (namespace = 'target-app') =>
  query(
    `sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="${namespace}",container!=""}[2m]))`
  )

export const fetchMemoryUsage = (namespace = 'target-app') =>
  query(
    `sum by (pod) (container_memory_working_set_bytes{namespace="${namespace}",container!=""})`
  )

export const fetchRequestRate = (namespace = 'target-app', minutes = 5) => {
  const end = Math.floor(Date.now() / 1000)
  const start = end - minutes * 60
  return queryRange(
    `sum(rate(http_requests_total{namespace="${namespace}"}[1m]))`,
    start, end, '15s'
  )
}

export const fetchErrorRate = (namespace = 'target-app', minutes = 5) => {
  const end = Math.floor(Date.now() / 1000)
  const start = end - minutes * 60
  return queryRange(
    `100 * sum(rate(http_requests_total{namespace="${namespace}",status_code=~"5.."}[1m])) / sum(rate(http_requests_total{namespace="${namespace}"}[1m]))`,
    start, end, '15s'
  )
}

// ── Alertmanager ──────────────────────────────────────────────────────────────

export const fetchAlerts = () => alertmanagerApi.get('/api/v2/alerts')
