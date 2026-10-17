import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import en from 'element-plus/es/locale/lang/en'
import 'element-plus/dist/index.css'
import '@fontsource-variable/inter'
import './index.css'
import App from './App.vue'
import { router } from './router'

createApp(App).use(ElementPlus, { locale: en }).use(router).mount('#app')
