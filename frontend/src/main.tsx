import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from './app'
import './style.css'

document.documentElement.dataset.theme = localStorage.getItem('theme') === 'light' ? 'light' : 'dark'

createRoot(document.getElementById('root')!).render(<BrowserRouter><App /></BrowserRouter>)
