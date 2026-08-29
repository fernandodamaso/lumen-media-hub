/**
 * Dev proxy for live mode (`ng serve --configuration=live`).
 * Forwards /api → homepage-actions on :8085 and injects X-Actions-Token
 * on mutating requests when ACTIONS_TOKEN is set in the environment.
 *
 * Uses Vite's `configure` hook (Angular 22 / Vite proxy). Webpack-style
 * `onProxyReq` is ignored by the Vite middleware.
 */
const token = process.env.ACTIONS_TOKEN || '';
/** Host dev: 127.0.0.1:8085. Docker dev dashboard container: http://homepage-actions:8085 */
const apiTarget = process.env.LIVE_API_PROXY_TARGET || 'http://127.0.0.1:8085';
function isPrivateBrowserPath(url) {
  const path = url?.split('?', 1)[0];
  return Boolean(path?.startsWith('/api/internal/'));
}

function needsActionsToken(req) {
  const method = (req.method || 'GET').toUpperCase();
  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method)) {
    return true;
  }
  const path = req.url?.split('?', 1)[0] ?? '';
  return method === 'GET' && (path.startsWith('/api/library/items/') || path.startsWith('/library/items/'));
}

module.exports = {
  '/api': {
    target: apiTarget,
    secure: false,
    changeOrigin: true,
    pathRewrite: { '^/api': '' },
    bypass(req) {
      if (isPrivateBrowserPath(req.url)) return false;
    },
    configure(proxy) {
      proxy.on('proxyReq', (proxyReq, req) => {
        if (token && needsActionsToken(req)) {
          proxyReq.setHeader('X-Actions-Token', token);
        }
      });
    },
  },
};
