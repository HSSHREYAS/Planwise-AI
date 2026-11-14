import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  // The backend port comes from the environment (set by start.ps1) or from
  // the project's root .env file, so the proxy always follows the backend.
  const rootEnv = loadEnv(mode, '..', '');
  const backendPort = process.env.BACKEND_PORT || rootEnv.BACKEND_PORT || '8000';

  return {
    server: {
      port: 3000,
      host: true,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  };
});
