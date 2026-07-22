// @ts-check
const { defineConfig } = require('eslint/config');
const rootConfig = require('../../eslint.config.js');

// Extends the workspace root ESLint config (fast day-to-day profile).
// Typed/commit profile is eslint.typed.config.js via `npm run lint:typed`.
module.exports = defineConfig([...rootConfig]);
