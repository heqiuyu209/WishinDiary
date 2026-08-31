import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router' // 引入路由
import './style.css'
import App from './App.vue'

const app = createApp(App)

app.use(createPinia())
app.use(router) // 挂载路由
app.mount('#app')