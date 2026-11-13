import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { installApiBridge } from './utils/apiBridge';

installApiBridge();

createRoot(document.getElementById('root')!).render(<App />);
