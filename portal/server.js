/**
 * 元策·擎天 操作台 — Node.js HTTP Server :3093
 * 纯标准库，零依赖。代理 API 到 Python :3092
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = 3093;
const API_HOST = "localhost";
const API_PORT = 3095;
const JWT_SECRET = "atlas-engine-2026";
const STATIC = path.join(__dirname, "public");

// ─── MIME ───
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "application/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

// ─── JWT ───
function base64url(str) {
  return Buffer.from(str).toString("base64url");
}
function signJWT(payload) {
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64url(JSON.stringify(payload));
  const h = crypto.createHmac("sha256", JWT_SECRET);
  h.update(header + "." + body);
  return header + "." + body + "." + h.digest("base64url");
}
function verifyJWT(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
    const h = crypto.createHmac("sha256", JWT_SECRET);
    h.update(parts[0] + "." + parts[1]);
    if (h.digest("base64url") !== parts[2]) return null;
    return payload;
  } catch (e) {
    return null;
  }
}

// ─── API Proxy ───
function proxyAPI(req, res, body) {
  const opts = {
    hostname: API_HOST,
    port: API_PORT,
    path: req.url,
    method: req.method,
    headers: { "Content-Type": "application/json" },
  };
  const proxy = http.request(opts, (presp) => {
    let data = "";
    presp.on("data", (c) => (data += c));
    presp.on("end", () => {
      res.writeHead(presp.statusCode, { "Content-Type": "application/json" });
      res.end(data);
    });
  });
  proxy.on("error", () => {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "API 服务暂不可用" }));
  });
  if (body) proxy.write(body);
  proxy.end();
}

function proxyUpload(req, res) {
  let chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const body = Buffer.concat(chunks);
    const boundary = req.headers["content-type"]?.split("boundary=")[1];
    const opts = {
      hostname: API_HOST,
      port: API_PORT,
      path: req.url,
      method: "POST",
      headers: { "Content-Type": req.headers["content-type"] || "multipart/form-data", "Content-Length": body.length },
    };
    const proxy = http.request(opts, (presp) => {
      let data = "";
      presp.on("data", (c) => (data += c));
      presp.on("end", () => {
        res.writeHead(presp.statusCode, { "Content-Type": "application/json" });
        res.end(data);
      });
    });
    proxy.on("error", () => {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: "API 服务暂不可用" }));
    });
    proxy.write(body);
    proxy.end();
  });
}

// ─── Static Files ───
function serveStatic(req, res, filePath) {
  const ext = path.extname(filePath);
  const mime = MIME[ext] || "application/octet-stream";
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("Not Found");
    } else {
      res.writeHead(200, { "Content-Type": mime });
      res.end(data);
    }
  });
}

// ─── Server ───
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = url.pathname;

  // API proxy
  if (pathname.startsWith("/api/")) {
    if (req.method === "POST" && pathname === "/api/parse") {
      return proxyUpload(req, res);
    }
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => proxyAPI(req, res, body || undefined));
    return;
  }

  // Login
  if (pathname === "/login" && req.method === "POST") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const { user, pass } = JSON.parse(body);
        if (user === "admin" && pass === "admin123") {
          const token = signJWT({ user, role: "admin", iat: Date.now() });
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: true, token }));
        } else {
          res.writeHead(401, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: "用户名或密码错误" }));
        }
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ ok: false, error: "格式错误" }));
      }
    });
    return;
  }

  // Static files
  let filePath = pathname === "/" ? "/index.html" : pathname;
  if (filePath === "/login") filePath = "/login.html";
  // Clean URLs: /stock → /stock.html, /agents → /agents.html, etc.
  if (!path.extname(filePath)) filePath += ".html";
  serveStatic(req, res, path.join(STATIC, filePath));
});

server.listen(PORT, () => {
  console.log(`🚀 元策·擎天 操作台 :${PORT}`);
});
