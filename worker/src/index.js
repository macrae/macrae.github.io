/**
 * seanmacrae.com — one Worker in front of everything.
 *
 *   /mana-map/data/*  -> R2      the 238 MiB of artifacts, same origin
 *   /api/*            -> D1      the queryable data behind the visualisations
 *   /admin*           -> GitHub  edit and publish, gated by Cloudflare Access
 *   everything else   -> assets  the committed static site
 *
 * THE R2 ROUTE IS THE LOAD-BEARING ONE. Mana Map's JavaScript hardcodes
 * `../data/<file>` in a dozen places and its own docs call that a hard
 * constraint. Serving R2 at `/mana-map/data/*` — the same origin, the exact
 * path those relative links already resolve to — means the entire workbench
 * moves hosts without a single line of it changing.
 */

import * as access from "./access.js";
import * as admin from "./admin.js";
import * as api from "./api.js";

const TYPES = {
  json: "application/json; charset=utf-8",
  bin: "application/octet-stream",
  txt: "text/plain; charset=utf-8",
  csv: "text/csv; charset=utf-8",
  html: "text/html; charset=utf-8",
  css: "text/css; charset=utf-8",
  js: "text/javascript; charset=utf-8",
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
  webp: "image/webp", gif: "image/gif", svg: "image/svg+xml",
  mp4: "video/mp4", webm: "video/webm", gz: "application/gzip",
};

function contentType(key) {
  return TYPES[key.split(".").pop().toLowerCase()] || TYPES.bin;
}

async function serveFromR2(request, env, key) {
  if (!env.DATA) {
    return new Response("R2 bucket not bound to this Worker\n", { status: 503 });
  }

  // Range support matters here: the largest artifact is 26.78 MiB, and a
  // browser that has to restart a whole download on a dropped connection is
  // the difference between the atlas loading and the atlas hanging.
  const range = request.headers.get("range");
  const opts = {};
  if (range) {
    const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
    if (m) {
      const [, start, end] = m;
      if (start) opts.range = { offset: +start, length: end ? +end - +start + 1 : undefined };
      else if (end) opts.range = { suffix: +end };
    }
  }
  const onlyIf = request.headers.get("if-none-match");
  if (onlyIf) opts.onlyIf = { etagDoesNotMatch: onlyIf };

  const obj = await env.DATA.get(key, opts);
  if (obj === null) {
    return new Response(`Not found in R2: ${key}\n`, { status: 404 });
  }

  const headers = new Headers({
    "content-type": contentType(key),
    etag: obj.httpEtag,
    // These artifacts are content-addressed by the viz's own ?v= parameter,
    // so they can be cached hard.
    "cache-control": "public, max-age=31536000, immutable",
    "accept-ranges": "bytes",
  });

  if (!obj.body) return new Response(null, { status: 304, headers });

  if (obj.range && range) {
    const off = obj.range.offset ?? 0;
    const len = obj.range.length ?? obj.size - off;
    headers.set("content-range", `bytes ${off}-${off + len - 1}/${obj.size}`);
    return new Response(obj.body, { status: 206, headers });
  }
  return new Response(obj.body, { headers });
}

/**
 * Serve a static asset at EXACTLY the path asked for.
 *
 * Cloudflare's default asset handling redirects /foo.html to /foo, which is
 * wrong here: mana-map links to `.html` explicitly everywhere -- its nav, its
 * deck pages, and every link to a rendered handbook -- so the default turned
 * every one of those into a 307 and an extra round trip. html_handling is set
 * to "none" in wrangler.toml and the two behaviours we actually want are done
 * here instead: a directory serves its index.html, and nothing redirects.
 */
async function serveAsset(request, env, path) {
  const direct = await env.ASSETS.fetch(request);
  if (direct.status !== 404) return direct;

  // A directory: serve its index.html without bouncing the browser.
  const candidates = [];
  if (path.endsWith("/")) candidates.push(path + "index.html");
  else if (!path.split("/").pop().includes(".")) candidates.push(path + "/index.html");

  for (const candidate of candidates) {
    const url = new URL(request.url);
    url.pathname = candidate;
    const res = await env.ASSETS.fetch(new Request(url, request));
    if (res.status !== 404) return res;
  }

  // The site's own 404 page, with the right status on it.
  const url = new URL(request.url);
  url.pathname = "/404.html";
  const notFound = await env.ASSETS.fetch(new Request(url, request));
  return new Response(notFound.body, {
    status: 404,
    headers: notFound.headers,
  });
}

/**
 * Mana Map's artifacts.
 *
 * These ship as ordinary static assets. Cloudflare refuses any single asset at
 * or over 25 MiB and exactly one file in this corpus is over it --
 * synergy_graph.json at 26.78 MiB -- so tools/assemble.py stores that one
 * gzipped and this serves it with `content-encoding: gzip`, which every
 * browser unpacks transparently. The reader gets 2.28 MiB instead of 26.78,
 * so the cap is worked around AND the atlas loads faster.
 *
 * R2 is still supported and still the better answer if this ever outgrows the
 * asset limits -- it syncs only what changed instead of re-uploading -- but it
 * requires a payment method on the account, which is a real cost for something
 * 217 MiB does not need.
 */
async function serveData(request, env, path) {
  const direct = await env.ASSETS.fetch(request);
  if (direct.status !== 404) return direct;

  // The compressed form of an oversized artifact.
  const url = new URL(request.url);
  url.pathname = path + ".gz";
  const packed = await env.ASSETS.fetch(new Request(url, request));
  if (packed.status !== 404) {
    // DECOMPRESSED HERE, not handed to the browser still compressed.
    //
    // The obvious approach -- serve the .gz bytes with `content-encoding:
    // gzip` -- does not work on Workers: the runtime manages encoding itself
    // and strips that header, so the browser receives gzip bytes labelled as
    // JSON and fails. Verified: 2,389,033 bytes arrived with no
    // content-encoding at all.
    //
    // DecompressionStream is native and streaming, so this neither buffers 26
    // MiB nor burns the 10 ms CPU budget on a JS loop. Cloudflare then applies
    // its own compression on the way out, so the reader still gets ~2.3 MiB
    // over the wire -- the same win, arrived at honestly.
    return new Response(
      packed.body.pipeThrough(new DecompressionStream("gzip")),
      {
        status: packed.status,
        headers: {
          "content-type": contentType(path),
          // Content-addressed by the viz's own ?v= parameter.
          "cache-control": "public, max-age=31536000, immutable",
        },
      },
    );
  }

  if (env.DATA) {
    return serveFromR2(request, env, path.slice("/mana-map/data/".length));
  }
  return new Response(`Not found: ${path}\n`, { status: 404 });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname);

    if (path.startsWith("/mana-map/data/")) {
      return serveData(request, env, path);
    }

    if (path === "/api" || path.startsWith("/api/")) {
      return api.handle(request, env);
    }

    if (path === "/admin" || path.startsWith("/admin/")) {
      // Fails closed: unset Access config means refused, never open.
      if (!env.ACCESS_TEAM || !env.ACCESS_AUD) {
        return access.refuse("admin is not protected yet, so it is closed");
      }
      const email = await access.identify(request, env);
      if (!email) return access.refuse("not signed in");
      if (env.ADMIN_EMAILS && !env.ADMIN_EMAILS.split(",")
            .map((s) => s.trim().toLowerCase()).includes(email.toLowerCase())) {
        return access.refuse(`${email} is not on the admin list`);
      }
      return admin.handle(request, env, email);
    }

    return serveAsset(request, env, path);
  },
};
