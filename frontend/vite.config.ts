import { defineConfig } from 'vite';
export default defineConfig({server:{proxy:{'/api':{target:'http://127.0.0.1:8010',ws:true},'/health':'http://127.0.0.1:8010'}},build:{sourcemap:false}});
