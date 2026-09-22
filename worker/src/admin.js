/**
 * The admin: edit and publish from a browser, without ever touching git.
 *
 * THE DATABASE IS NOT THE SITE. Posts stay markdown files in the repository;
 * this writes to them through the GitHub Contents API and lets the normal
 * build deploy the result. You never make a commit — the Worker makes it for
 * you, under your Access identity — and in exchange you keep every guarantee
 * the static build has: full history, rollback, byte-identical rebuild, and a
 * site that keeps serving even if this Worker is broken.
 *
 * The cost, stated honestly: publishing takes about a minute rather than being
 * instant, because a real build and deploy happen in between.
 */

const API = "https://api.github.com";

function gh(env, path, init = {}) {
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "seanmacrae.com-admin",
      "content-type": "application/json",
      ...(init.headers || {}),
    },
  });
}

const repoPath = (env, p) =>
  `/repos/${env.GITHUB_REPO}/contents/${p}?ref=${env.GITHUB_BRANCH || "main"}`;

async function listPosts(env) {
  const res = await gh(env, repoPath(env, "content/posts"));
  if (!res.ok) throw new Error(`listing posts: HTTP ${res.status}`);
  const dirs = (await res.json()).filter((e) => e.type === "dir");
  const out = [];
  for (const d of dirs) {
    const f = await gh(env, repoPath(env, `content/posts/${d.name}/index.md`));
    if (!f.ok) continue;
    const meta = await f.json();
    const text = decodeURIComponent(escape(atob(meta.content.replace(/\n/g, ""))));
    const fm = Object.fromEntries(
      text.split("---")[1].trim().split("\n")
        .map((l) => [l.slice(0, l.indexOf(":")).trim(),
                     l.slice(l.indexOf(":") + 1).trim()]),
    );
    out.push({ slug: d.name, title: (fm.title || d.name).replace(/^"|"$/g, ""),
               date: fm.date, status: fm.status, sha: meta.sha });
  }
  out.sort((a, b) => (a.date < b.date ? 1 : -1));
  return out;
}

async function getPost(env, slug) {
  const res = await gh(env, repoPath(env, `content/posts/${slug}/index.md`));
  if (!res.ok) throw new Error(`reading ${slug}: HTTP ${res.status}`);
  const meta = await res.json();
  return {
    sha: meta.sha,
    text: decodeURIComponent(escape(atob(meta.content.replace(/\n/g, "")))),
  };
}

async function savePost(env, slug, text, sha, email) {
  const body = {
    message: `${slug}: edited from the admin`,
    content: btoa(unescape(encodeURIComponent(text))),
    sha,
    branch: env.GITHUB_BRANCH || "main",
    // The commit is attributed to whoever Access authenticated, so the
    // history says who actually published rather than "the Worker".
    committer: { name: "seanmacrae.com admin", email: email || "noreply@seanmacrae.com" },
  };
  const res = await gh(env, `/repos/${env.GITHUB_REPO}/contents/content/posts/${slug}/index.md`,
                       { method: "PUT", body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`saving ${slug}: HTTP ${res.status} ${await res.text()}`);
  return (await res.json()).commit.sha;
}

const CSS = `
*{box-sizing:border-box}body{margin:0;background:#14130f;color:#efe9dd;
font:16px/1.55 ui-sans-serif,-apple-system,system-ui,sans-serif}
.w{max-width:860px;margin:0 auto;padding:1.5rem 1rem 4rem}
h1{font:600 1.5rem/1.2 ui-serif,Georgia,serif;margin:0 0 .2rem}
.sub{color:#8b8474;font-size:.85rem;margin:0 0 1.8rem}
a{color:#e0937c;text-decoration:none}a:hover{text-decoration:underline}
ul{list-style:none;padding:0;margin:0}
li{padding:.85rem .2rem;border-bottom:1px solid #26221b;display:flex;gap:.8rem;align-items:baseline}
li b{font-weight:600;flex:1;min-width:0}
.badge{font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;padding:.1rem .45rem;
border-radius:3px;border:1px solid #4a4436;color:#a9a294;white-space:nowrap}
.published{border-color:#3f6b3f;color:#7ec77e}.staged{border-color:#7a6a3a;color:#d4af4a}
.d{color:#6f6a5e;font-size:.8rem;white-space:nowrap}
textarea{width:100%;min-height:62vh;background:#1b1914;color:#efe9dd;border:1px solid #3a352c;
border-radius:4px;padding:1rem;font:14px/1.6 ui-monospace,Menlo,monospace;resize:vertical}
button{background:#7a2e1e;color:#fff;border:0;border-radius:4px;padding:.65rem 1.4rem;
font-size:1rem;cursor:pointer}
button:hover{background:#9a3a26}
.bar{display:flex;gap:1rem;align-items:center;margin-top:1rem;flex-wrap:wrap}
.ok{color:#7ec77e}.err{color:#e0937c;white-space:pre-wrap}
`;

const page = (title, body) =>
  new Response(
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title><style>${CSS}</style></head><body><div class="w">${body}</div></body></html>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export async function handle(request, env, email) {
  const url = new URL(request.url);
  const slug = url.searchParams.get("slug");

  if (!env.GITHUB_TOKEN || !env.GITHUB_REPO) {
    return page("Admin", `<h1>Not configured</h1><p class="err">GITHUB_TOKEN or
      GITHUB_REPO is unset on the Worker. Set them with
      <code>wrangler secret put GITHUB_TOKEN</code>.</p>`);
  }

  if (request.method === "POST") {
    const form = await request.formData();
    try {
      const commit = await savePost(env, form.get("slug"), form.get("text"),
                                    form.get("sha"), email);
      return page("Saved", `<h1>Saved</h1>
        <p class="ok">Committed <code>${esc(commit.slice(0, 7))}</code>.
        The site rebuilds and redeploys in about a minute.</p>
        <p><a href="/admin">&larr; all posts</a></p>`);
    } catch (e) {
      return page("Error", `<h1>Not saved</h1><p class="err">${esc(e.message)}</p>
        <p><a href="/admin">&larr; back</a></p>`);
    }
  }

  if (slug) {
    const { text, sha } = await getPost(env, slug);
    return page(`Edit ${slug}`, `
      <h1>${esc(slug)}</h1>
      <p class="sub"><a href="/admin">&larr; all posts</a> &middot;
        <a href="/${esc(slug)}/">view</a></p>
      <form method="POST">
        <input type="hidden" name="slug" value="${esc(slug)}">
        <input type="hidden" name="sha" value="${esc(sha)}">
        <textarea name="text" spellcheck="true">${esc(text)}</textarea>
        <div class="bar"><button type="submit">Commit</button>
        <span class="sub" style="margin:0">Change <code>status: staged</code> to
        <code>status: published</code> to publish. Publishing also needs
        <code>summary</code>, <code>category</code> and <code>tags</code> —
        the build refuses without them.</span></div>
      </form>`);
  }

  const posts = await listPosts(env);
  const rows = posts.map((p) => `<li>
      <b><a href="/admin?slug=${esc(p.slug)}">${esc(p.title)}</a></b>
      <span class="badge ${esc(p.status)}">${esc(p.status)}</span>
      <span class="d">${esc(p.date)}</span></li>`).join("");
  return page("Admin", `<h1>Posts</h1>
    <p class="sub">${posts.length} in the repository &middot; signed in as
    ${esc(email || "unknown")}</p><ul>${rows}</ul>`);
}
