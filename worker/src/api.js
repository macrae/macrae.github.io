/**
 * The read-only data API behind the visualisations.
 *
 * This exists for the one thing a static site genuinely cannot do: let a chart
 * ASK a question of a dataset too large or too many-shaped to ship as a JSON
 * file. Everything else on this site is still precomputed and committed.
 *
 * READ-ONLY, AND SHAPED SO IT CANNOT BECOME OTHERWISE. Every handler is a
 * named query with bound parameters; there is no endpoint that accepts SQL,
 * and D1 is bound without any write path from here. A public API that can be
 * coaxed into writing is how a personal site becomes someone else's problem.
 */

const json = (data, status = 200) =>
  new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      // Cached at the edge: these answers change only when the data is
      // reloaded, and the whole point is that a chart can ask freely.
      "cache-control": "public, max-age=300, s-maxage=3600",
    },
  });

const clamp = (v, lo, hi, dflt) => {
  const n = Number.parseInt(v ?? "", 10);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt;
};

/** Named queries. Adding a dataset means adding a row here, never a route. */
const QUERIES = {
  datasets: async (env) => {
    const { results } = await env.DB.prepare(
      "SELECT name, description, rows, updated FROM datasets ORDER BY name",
    ).all();
    return { datasets: results };
  },

  series: async (env, url) => {
    const name = url.searchParams.get("dataset");
    if (!name) return { error: "dataset is required" };
    const limit = clamp(url.searchParams.get("limit"), 1, 5000, 1000);
    const { results } = await env.DB.prepare(
      `SELECT t, key, value FROM series
        WHERE dataset = ?1
        ORDER BY t
        LIMIT ?2`,
    ).bind(name, limit).all();
    return { dataset: name, n: results.length, limit, points: results };
  },
};

export async function handle(request, env) {
  if (request.method !== "GET") {
    return json({ error: "read-only" }, 405);
  }
  if (!env.DB) {
    return json({ error: "no database bound to this Worker" }, 503);
  }
  const url = new URL(request.url);
  const name = url.pathname.replace(/^\/api\/?/, "").split("/")[0] || "datasets";
  const handler = QUERIES[name];
  if (!handler) {
    return json({ error: `unknown endpoint ${name}`,
                  available: Object.keys(QUERIES) }, 404);
  }
  try {
    return json(await handler(env, url));
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
