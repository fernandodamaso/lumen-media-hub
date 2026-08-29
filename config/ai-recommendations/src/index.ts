import { createServer } from 'node:http';
import { createModel } from './providers.js';
import { generatePicks } from './recommend.js';
import { processOnce } from './worker.js';

const port = Number(process.env.PORT ?? '8090');
const baseUrl = (process.env.HOMEPAGE_ACTIONS_URL ?? 'http://homepage-actions:8085').replace(/\/$/, '');
const token = process.env.ACTIONS_TOKEN ?? '';
const pollMs = Number(process.env.AI_POLL_INTERVAL_MS ?? '2000');
const timeoutMs = Number(process.env.AI_MODEL_TIMEOUT_MS ?? '60000');
const model = createModel();

if (!token) throw new Error('ACTIONS_TOKEN is required');

createServer((request, response) => {
  if (request.url === '/health') {
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ ok: true }));
    return;
  }
  response.writeHead(404, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify({ ok: false }));
}).listen(port, '0.0.0.0');

async function loop(): Promise<void> {
  try {
    await processOnce({
      baseUrl,
      token,
      recommend: job => generatePicks(job, model, timeoutMs),
    });
  } catch (error) {
    console.error(`[ai-recommendations] poll failed code=${error instanceof Error ? error.name : 'unknown'}`);
  } finally {
    setTimeout(loop, pollMs);
  }
}

void loop();
