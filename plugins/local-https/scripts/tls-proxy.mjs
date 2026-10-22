#!/usr/bin/env node
// tls-proxy.mjs — terminate TLS with a local cert and forward to a plain-HTTP
// dev server on the same machine.
//
//   node tls-proxy.mjs --cert <pem> --key <pem> --listen <port> --target <port> [--host <bind-host>]
//
// Every request goes to http://127.0.0.1:<target> with Host preserved and
// X-Forwarded-Proto: https, X-Forwarded-For and X-Forwarded-Host added.
// WebSocket upgrades (dev-server HMR) are forwarded with their original
// headers and the two sockets piped. --host is the TLS bind address only
// (default 127.0.0.1); the upstream is always loopback. Node built-ins only.

import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';

const UPSTREAM = '127.0.0.1';

function fail(msg) {
  process.stderr.write(`tls-proxy: ${msg}\n`);
  process.exit(1);
}

function parseArgs(argv) {
  const opts = { host: '127.0.0.1' };
  const known = new Set(['--cert', '--key', '--listen', '--target', '--host']);
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    if (!known.has(flag)) fail(`unknown argument: ${flag}`);
    if (i + 1 >= argv.length) fail(`${flag} needs a value`);
    opts[flag.slice(2)] = argv[i + 1];
  }
  for (const req of ['cert', 'key', 'listen', 'target']) {
    if (!opts[req]) fail(`missing --${req}`);
  }
  for (const p of ['listen', 'target']) {
    if (!/^[1-9][0-9]{0,4}$/.test(opts[p]) || Number(opts[p]) > 65535) {
      fail(`--${p} must be an integer 1-65535, got: ${opts[p]}`);
    }
    opts[p] = Number(opts[p]);
  }
  return opts;
}

function readPem(kind, path) {
  try {
    return fs.readFileSync(path);
  } catch (err) {
    fail(`cannot read ${kind} ${path} (${err.code || err.message}); run: local-https setup`);
  }
}

function forwardHeaders(req) {
  const headers = { ...req.headers };
  const peer = req.socket.remoteAddress || '';
  headers['x-forwarded-for'] = headers['x-forwarded-for'] ? `${headers['x-forwarded-for']}, ${peer}` : peer;
  headers['x-forwarded-proto'] = 'https';
  if (headers.host && !headers['x-forwarded-host']) headers['x-forwarded-host'] = headers.host;
  return headers;
}

function upstreamOptions(req, port) {
  return { host: UPSTREAM, port, method: req.method, path: req.url, headers: forwardHeaders(req) };
}

// Status line plus raw headers, for writing a response onto a bare socket.
function rawHead(res) {
  let head = `HTTP/${res.httpVersion} ${res.statusCode} ${res.statusMessage}\r\n`;
  for (let i = 0; i < res.rawHeaders.length; i += 2) {
    head += `${res.rawHeaders[i]}: ${res.rawHeaders[i + 1]}\r\n`;
  }
  return `${head}\r\n`;
}

const opts = parseArgs(process.argv.slice(2));
const tlsOpts = { cert: readPem('cert', opts.cert), key: readPem('key', opts.key) };

const server = https.createServer(tlsOpts, (req, res) => {
  const up = http.request(upstreamOptions(req, opts.target), (upRes) => {
    res.writeHead(upRes.statusCode, upRes.statusMessage, upRes.headers);
    upRes.pipe(res);
  });
  up.on('error', (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'text/plain' });
      res.end(`tls-proxy: upstream http://${UPSTREAM}:${opts.target} unavailable (${err.code || err.message})\n`);
    } else {
      res.destroy();
    }
  });
  req.on('error', () => up.destroy());
  req.pipe(up);
});

server.on('upgrade', (req, socket, head) => {
  socket.on('error', () => {});
  const up = http.request(upstreamOptions(req, opts.target));
  up.on('upgrade', (upRes, upSocket, upHead) => {
    upSocket.on('error', () => socket.destroy());
    socket.on('error', () => upSocket.destroy());
    socket.write(rawHead(upRes));
    if (upHead && upHead.length) socket.write(upHead);
    if (head && head.length) upSocket.write(head);
    upSocket.pipe(socket);
    socket.pipe(upSocket);
  });
  up.on('response', (upRes) => {
    // The upstream declined the upgrade: relay its answer and close.
    socket.write(rawHead(upRes));
    upRes.pipe(socket);
  });
  up.on('error', () => {
    socket.end('HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n');
  });
  up.end();
});

server.on('clientError', (err, socket) => {
  if (socket.writable) socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');
  else socket.destroy();
});

server.on('error', (err) => fail(`cannot listen on ${opts.host}:${opts.listen} (${err.code || err.message})`));

server.listen(opts.listen, opts.host, () => {
  process.stdout.write(`tls-proxy: https://${opts.host}:${opts.listen} -> http://${UPSTREAM}:${opts.target}\n`);
});

for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => process.exit(0));
