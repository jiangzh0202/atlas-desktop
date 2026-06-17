/**
 * Shared HTTP proxy helpers for API route handlers.
 * Proxies requests from Node portal :3093 to Python API :3095.
 */
const http = require('http');

function proxyAuto(req, res, body, API_HOST, API_PORT) {
  const isDownload = req.url.includes('/export') || req.url.includes('/download');
  const opts = {
    hostname: API_HOST,
    port: API_PORT,
    path: req.url,
    method: req.method,
    headers: { 'Content-Type': 'application/json' },
  };
  const proxy = http.request(opts, (presp) => {
    const ct = presp.headers['content-type'] || '';
    if (isDownload || ct.includes('spreadsheet') || ct.includes('octet-stream') || ct.includes('excel')) {
      const rheaders = {
        'Content-Type': ct,
        'Content-Disposition': presp.headers['content-disposition'] || 'attachment',
      };
      res.writeHead(presp.statusCode, rheaders);
      presp.pipe(res);
    } else {
      let data = '';
      presp.on('data', (c) => (data += c));
      presp.on('end', () => {
        res.writeHead(presp.statusCode, { 'Content-Type': 'application/json' });
        res.end(data);
      });
    }
  });
  proxy.on('error', () => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: false, error: 'API 服务暂不可用' }));
  });
  if (body) proxy.write(body);
  proxy.end();
}

function proxyUpload(req, res, API_HOST, API_PORT) {
  let chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks);
    const opts = {
      hostname: API_HOST,
      port: API_PORT,
      path: req.url,
      method: 'POST',
      headers: {
        'Content-Type': req.headers['content-type'] || 'multipart/form-data',
        'Content-Length': body.length,
      },
    };
    const proxy = http.request(opts, (presp) => {
      let data = '';
      presp.on('data', (c) => (data += c));
      presp.on('end', () => {
        res.writeHead(presp.statusCode, { 'Content-Type': 'application/json' });
        res.end(data);
      });
    });
    proxy.on('error', () => {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: false, error: 'API 服务暂不可用' }));
    });
    proxy.write(body);
    proxy.end();
  });
}

module.exports = { proxyAuto, proxyUpload };
