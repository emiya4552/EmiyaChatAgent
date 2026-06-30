import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：自动附加 JWT Token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：处理 401 错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      // 路由跳转（懒加载避免循环依赖）
      import('../router').then(({ default: router }) => {
        router.push('/login')
      })
      // 清除 Pinia store（懒加载避免循环依赖）
      import('../stores/auth').then(({ useAuthStore }) => {
        useAuthStore().logout()
      })
    }
    return Promise.reject(error)
  }
)

export default api
