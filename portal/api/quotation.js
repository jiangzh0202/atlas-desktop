/**
 * quotation API routes — proxy to Python :3095
 */
const { proxyAuto } = require("./_proxy");

function handle(req, res, API_HOST, API_PORT) {
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    proxyAuto(req, res, body || undefined, API_HOST, API_PORT);
  });
}

module.exports = { handle };
