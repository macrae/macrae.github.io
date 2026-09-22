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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname);

    if (path.startsWith("/mana-map/data/")) {
      return serveFromR2(request, env, path.slice("/mana-map/data/".length));
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

    return env.ASSETS.fetch(request);
  },
};
