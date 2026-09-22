/**
 * Cloudflare Access verification, and it FAILS CLOSED.
 *
 * Access injects a signed JWT as `Cf-Access-Jwt-Assertion` on every request it
 * lets through. Trusting the companion `Cf-Access-Authenticated-User-Email`
 * header on its own would be a mistake: headers are only trustworthy if the
 * request cannot reach the Worker any other way, and a Worker route is
 * directly addressable. So the signature is actually verified, against the
 * team's published keys, every time.
 *
 * If ACCESS_TEAM or ACCESS_AUD is unset, /admin is refused outright rather
 * than left open. An admin endpoint that is accidentally public is the worst
 * failure this codebase could have.
 */

const CACHE = { keys: null, fetchedAt: 0 };
const KEY_TTL_MS = 60 * 60 * 1000;

function b64urlToBytes(s) {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function publicKeys(team) {
  const now = Date.now();
  if (CACHE.keys && now - CACHE.fetchedAt < KEY_TTL_MS) return CACHE.keys;
  const url = `https://${team}.cloudflareaccess.com/cdn-cgi/access/certs`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Access certs: HTTP ${res.status}`);
  const { keys } = await res.json();
  const imported = {};
  for (const jwk of keys) {
    imported[jwk.kid] = await crypto.subtle.importKey(
      "jwk",
      { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
  }
  CACHE.keys = imported;
  CACHE.fetchedAt = now;
  return imported;
}

/** Returns the authenticated email, or null. Never throws past the caller. */
export async function identify(request, env) {
  if (!env.ACCESS_TEAM || !env.ACCESS_AUD) return null;

  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return null;

  const [headB64, bodyB64, sigB64] = token.split(".");
  if (!headB64 || !bodyB64 || !sigB64) return null;

  let head, body;
  try {
    head = JSON.parse(new TextDecoder().decode(b64urlToBytes(headB64)));
    body = JSON.parse(new TextDecoder().decode(b64urlToBytes(bodyB64)));
  } catch {
    return null;
  }

  const keys = await publicKeys(env.ACCESS_TEAM);
  const key = keys[head.kid];
  if (!key) return null;

  const ok = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlToBytes(sigB64),
    new TextEncoder().encode(`${headB64}.${bodyB64}`),
  );
  if (!ok) return null;

  const now = Math.floor(Date.now() / 1000);
  if (body.exp && body.exp < now) return null;
  if (body.nbf && body.nbf > now) return null;

  const aud = Array.isArray(body.aud) ? body.aud : [body.aud];
  if (!aud.includes(env.ACCESS_AUD)) return null;
  if (body.iss !== `https://${env.ACCESS_TEAM}.cloudflareaccess.com`) return null;

  return body.email || null;
}

export function refuse(reason) {
  return new Response(
    `403 — ${reason}\n\n` +
      "This endpoint is protected by Cloudflare Access and refuses requests it\n" +
      "cannot verify. If you are seeing this while logged in, ACCESS_TEAM or\n" +
      "ACCESS_AUD is unset on the Worker.\n",
    { status: 403, headers: { "content-type": "text/plain; charset=utf-8" } },
  );
}
