import axios from 'axios'

const DEFAULT_TIMEOUT = 10_000
const MAX_RETRIES = 2

function createInstance(baseURL) {
  const instance = axios.create({ baseURL, timeout: DEFAULT_TIMEOUT })

  // Request interceptor — attach correlation ID
  instance.interceptors.request.use((config) => {
    config.headers['X-Dashboard-Request'] = 'true'
    return config
  })

  // Response interceptor — normalise errors
  instance.interceptors.response.use(
    (res) => res,
    async (error) => {
      const config = error.config
      if (!config) return Promise.reject(error)

      config._retryCount = config._retryCount || 0

      // Retry on 503 Service Unavailable up to MAX_RETRIES times
      if (error.response?.status === 503 && config._retryCount < MAX_RETRIES) {
        config._retryCount++
        await new Promise((r) => setTimeout(r, 1000 * config._retryCount))
        return instance(config)
      }

      // Normalise error message
      const message =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        'Unknown error'
      error.userMessage = message
      return Promise.reject(error)
    }
  )

  return instance
}

export default createInstance
