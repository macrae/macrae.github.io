"""Markdown -> HTML, over one configured markdown-it-py instance.

WHY markdown-it-py AND NOT Python-Markdown OR MISTUNE. Two criteria decided it.
Its output is pinned to the CommonMark specification, which has a public
conformance suite, so a version bump produces a diff you can reason about
rather than a surprise in a committed file. And it hands you a TOKEN STREAM:
figures, heading anchors, internal-link rewriting through spec.url_for and the
maths pass all want to operate on structure, not on rendered HTML. The
alternatives make you regex over HTML or subclass a renderer and hope.

Everything here is a render-rule override on that token stream. No
post-processing of the output string, because a regex over HTML is exactly the
class of fix this module exists to avoid.

MATHS ARE MathML, RENDERED AT BUILD TIME. The 102 equations recovered from
WordPress were QuickLaTeX bitmaps served from a CDN that dies with the hosting
account. MathML renders natively in every current browser, needs no
JavaScript, scales with the text, prints, and can be read aloud — so the
migration ends with better mathematics than it started with. A client-side
renderer such as KaTeX was rejected: it would put a script on the one kind of
page whose argument most needs to survive with scripts off.
"""

import html as _html
import re

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

from . import _imgsize, spec

MATH_RE = re.compile(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$")


class MarkdownError(ValueError):
    pass


def esc(text):
    return _html.escape(str(text), quote=True)


def latex_to_mathml(latex, where="<unknown>"):
    """One inline formula -> MathML. Never silently degrades.

    QuickLaTeX left stray `$$` inside some alt attributes and at least one
    formula in the corpus is malformed LaTeX as typed. Both are stripped and
    converted; anything that still fails raises, because an equation that
    quietly becomes literal text is a post losing its argument without anyone
    noticing.
    """
    import latex2mathml.converter as converter
    cleaned = latex.replace("$$", "").strip()
    if not cleaned:
        raise MarkdownError(f"{where}: empty formula")
    try:
        return converter.convert(cleaned)
    except Exception as exc:
        raise MarkdownError(
            f"{where}: cannot convert LaTeX to MathML: {latex!r}\n  {exc}") from exc


def _slug_ids():
    """Heading ids, deduped deterministically within one document."""
    seen = {}

    def make(text):
        base = spec.slugify(text) or "section"
        seen[base] = seen.get(base, 0) + 1
        return base if seen[base] == 1 else f"{base}-{seen[base]}"
    return make


class Renderer:
    def __init__(self, *, base_url="", asset_url=None, where="<doc>", ns=""):
        self.base_url = base_url
        self.asset_url = asset_url or (lambda rel: rel)
        self.where = where
        self.ns = ns                      # namespaces footnote ids per entry
        self.math_count = 0
        self.md = (
            MarkdownIt("commonmark", {"html": True, "typographer": True})
            .enable(["table", "strikethrough", "smartquotes", "replacements"])
            .use(footnote_plugin)
        )
        self._install_rules()

    # ------------------------------------------------------------- the rules

    def _install_rules(self):
        md, rules = self.md, self.md.renderer.rules
        make_id = _slug_ids()
        self._make_id = make_id

        def heading_open(tokens, idx, options, env):
            tok = tokens[idx]
            text = tokens[idx + 1].content
            hid = make_id(text)
            tok.attrSet("id", hid)
            return f"<{tok.tag} id=\"{esc(hid)}\">"

        def heading_close(tokens, idx, options, env):
            tok = tokens[idx]
            hid = tokens[idx - 2].attrGet("id") or ""
            # The anchor is invisible until the heading is hovered; it exists so
            # a reader can link to a section, which is the one thing they cannot
            # do by scrolling.
            link = (f'<a class="sm-anchor" href="#{esc(hid)}" '
                    f'aria-label="Link to this section">¶</a>')
            return f"{link}</{tok.tag}>"

        def image(tokens, idx, options, env):
            tok = tokens[idx]
            src = tok.attrGet("src") or ""
            alt = tok.content or ""
            title = tok.attrGet("title")
            out_src = self.asset_url(src)
            dims = ""
            local = env.get("resolve") and env["resolve"](src)
            if local and local.exists():
                wh = _imgsize.size(local)
                if wh:
                    dims = f' width="{wh[0]}" height="{wh[1]}"'
            img = (f'<img src="{esc(out_src)}" alt="{esc(alt)}"{dims} loading="lazy" '
                   f'decoding="async">')
            if title:
                # A caption has no slot in markdown, which is why the converter
                # keeps captioned figures as raw HTML. This path covers the ones
                # written by hand with a markdown title.
                return (f'<figure>{img}<figcaption>{esc(title)}</figcaption></figure>')
            return img

        def fence(tokens, idx, options, env):
            tok = tokens[idx]
            info = (tok.info or "").strip()
            lang = info.split()[0] if info else ""
            code = tok.content
            if lang:
                try:
                    from pygments import highlight
                    from pygments.formatters import HtmlFormatter
                    from pygments.lexers import get_lexer_by_name
                    lexer = get_lexer_by_name(lang)
                    fmt = HtmlFormatter(cssclass="hl", wrapcode=True, nowrap=False)
                    return highlight(code, lexer, fmt)
                except Exception as exc:
                    raise MarkdownError(
                        f"{self.where}: code fence declares language {lang!r}, which "
                        f"pygments cannot load ({exc}). Languages are declared by "
                        "hand in migrate/overrides/, never guessed — fix the "
                        "declaration rather than removing it.") from exc
            return f"<pre><code>{esc(code)}</code></pre>"

        def link_open(tokens, idx, options, env):
            tok = tokens[idx]
            href = tok.attrGet("href") or ""
            if href.startswith(("http://", "https://")):
                tok.attrSet("rel", "noopener")
                if not href.startswith(spec.SITE_URL):
                    tok.attrSet("class", "sm-external")
            elif href.startswith("/"):
                checker = env.get("check_internal")
                if checker:
                    checker(href)
            return md.renderer.renderToken(tokens, idx, options, env)

        def table_open(tokens, idx, options, env):
            return '<div class="sm-table-scroll"><table>'

        def table_close(tokens, idx, options, env):
            return "</table></div>"

        rules["heading_open"] = heading_open
        rules["heading_close"] = heading_close
        rules["image"] = image
        rules["fence"] = fence
        rules["link_open"] = link_open
        rules["table_open"] = table_open
        rules["table_close"] = table_close

    # ------------------------------------------------------------------ math

    def _render_math(self, text):
        """`$...$` -> MathML, outside code spans and pre blocks.

        Split on the code/pre regions first and only substitute in between, so
        a dollar sign inside a shell example is never eaten.
        """
        parts = re.split(r"(<pre\b.*?</pre>|<code\b.*?</code>)", text, flags=re.S)
        out = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                out.append(part)
                continue

            def sub(m):
                self.math_count += 1
                mathml = latex_to_mathml(m.group(1), self.where)
                return f'<span class="sm-math">{mathml}</span>'
            out.append(MATH_RE.sub(sub, part))
        return "".join(out)

    # ----------------------------------------------------------------- entry

    def render(self, text, *, resolve=None, check_internal=None):
        env = {"resolve": resolve, "check_internal": check_internal}
        html_out = self.md.render(text, env)
        html_out = self._render_math(html_out)
        if self.ns:
            # Two entries can appear on one page (an index with inline bodies),
            # and CommonMark footnote ids are per-document, so they would
            # collide. Namespace them by slug.
            html_out = re.sub(r'(id|href)="#?(fn|fnref)(\d+)"',
                              lambda m: f'{m.group(1)}="'
                                        f'{"#" if m.group(1) == "href" else ""}'
                                        f'{m.group(2)}-{self.ns}-{m.group(3)}"',
                              html_out)
        return html_out


def render(text, *, where="<doc>", ns="", resolve=None, asset_url=None,
           check_internal=None):
    r = Renderer(where=where, ns=ns, asset_url=asset_url)
    out = r.render(text, resolve=resolve, check_internal=check_internal)
    return out, r.math_count
