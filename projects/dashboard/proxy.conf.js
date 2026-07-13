/**
 * Dev proxy for live mode (`ng serve --configuration=live`).
 * Forwards /api → homepage-actions on :8085 and injects X-Actions-Token
 * on mutating requests when ACTIONS_TOKEN is set in the environment.
 */
const token = process.env.ACTIONS_TOKEN || '';

module.exports = {
  '/api': {
    target: 'http://127.0.0.1:8085',
    secure: false,
    changeOrigin: true,
    pathRewrite: { '^/api': '' },
    onProxyReq(proxyReq, req) {
      const method = (req.method || 'GET').toUpperCase();
      if (token && ['POST', 'PATCH', 'PUT', 'DELETE'].includes(method)) {
        proxyReq.setHeader('X-Actions-Token', token);
      }
    },
  },
};
