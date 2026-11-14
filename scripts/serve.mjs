import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };
const port = Number(process.env.PORT || 239);
http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const relative = pathname === '/' ? 'index.html' : pathname.slice(1);
    const filename = path.resolve(root, relative);
    // This is a static preview, not an application backend. Serve UI assets only.
    if (!filename.startsWith(root) || !(relative === 'index.html' || /^src\/[\w-]+\.(js|css)$/.test(relative))) {
      res.writeHead(404).end('Not found'); return;
    }
    const content = await readFile(filename);
    res.writeHead(200, { 'Content-Type': `${types[path.extname(filename)] || 'text/plain'}; charset=utf-8`, 'Cache-Control': 'no-cache' });
    res.end(content);
  } catch { res.writeHead(404).end('Not found'); }
}).listen(port, '127.0.0.1', () => console.log(`Sola preview: http://127.0.0.1:${port}`));
