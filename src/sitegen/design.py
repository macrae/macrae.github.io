"""The stylesheet, as one Python constant.

CSS lives here rather than in a .css file so that `stylesheet_version()` can
content-hash it and every page's <link> is cache-busted automatically. There is
no version integer for anyone to forget to bump; the committed docs/site.css is
a build artifact, and a test asserts it matches this constant so a hand-edit to
the output is caught rather than silently overwritten on the next build.

EVERY TOKEN IS NAMESPACED --sm-*, AND THAT IS ENFORCED BY A TEST.

The sibling mana-map repo carries two token sets — a dark web one in
viz/css/tokens.css and a light print one in pilot/poh_design.py — with a
comment insisting one is "a port, not a fork" of the other. That comment is a
scar: keeping them in sync by hand has already gone wrong twice, inside a
single repository where at least `grep` reaches both copies. Across two
repositories it is strictly worse.

So this is a PERMANENT FORK, and the namespace is what makes the decision
enforceable rather than documentary: a `--poh-` or a bare `--paper` pasted in
from either of those files fails tests/test_design_tokens.py immediately.

The register is editorial. A warm off-white ground, a serif for reading, a
measure around 46rem, figures that carry real captions, and print rules that
are actually print rules rather than @media print cosmetics — because 17,000
words of technical writing is the job, and some of it people will want on
paper.
"""

import hashlib

from . import spec

_TOKENS = """
:root {
  /* Ground and ink. Warm, not blue-white: a paper-like ground is easier on the
     eye for long-form than #fff, and it photographs and prints honestly. */
  --sm-paper:      #fbfaf7;
  --sm-paper-sunk: #f3f1ea;
  --sm-ink:        #1b1a17;
  --sm-ink-soft:   #5f5b52;
  --sm-ink-faint:  #8c877c;
  --sm-rule:       #ddd8cc;
  --sm-rule-soft:  #ebe7dd;

  /* One accent, used sparingly: links, the current nav item, figure numbers. */
  --sm-accent:      #7a2e1e;
  --sm-accent-soft: #a8543e;

  /* A departure -- a link that leaves this site entirely, such as /mana-map/.
     Styled to say so rather than pretending to be internal navigation. */
  --sm-depart:     #2f4858;

  --sm-serif: ui-serif, "Iowan Old Style", "Palatino Linotype", Palatino,
              Georgia, Cambria, "Times New Roman", serif;
  --sm-sans:  ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
              Roboto, Helvetica, Arial, sans-serif;
  --sm-mono:  ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas,
              "Liberation Mono", monospace;

  --sm-measure: MEASURE;
  --sm-wide:    62rem;
  --sm-gallery: 108rem;
  --sm-step:    1.55;
}

/* A restrained dark variant. The light palette above stays canonical -- it is
   what prints and what the design was drawn against -- but a site people read
   at night should not flashbang them. Only tokens are redefined; no rule below
   this point knows which scheme it is in. */
@media (prefers-color-scheme: dark) {
  :root {
    --sm-paper:      #161513;
    --sm-paper-sunk: #1e1c19;
    --sm-ink:        #ece7dc;
    --sm-ink-soft:   #a9a294;
    --sm-ink-faint:  #7d7668;
    --sm-rule:       #3a352c;
    --sm-rule-soft:  #2a261f;
    --sm-accent:     #e0937c;
    --sm-accent-soft:#c9755c;
    --sm-depart:     #8fb3c7;
  }
}
"""

_BASE = """
*, *::before, *::after { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--sm-paper);
  color: var(--sm-ink);
  font-family: var(--sm-serif);
  font-size: 1.125rem;
  line-height: var(--sm-step);
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

.sm-trim { max-width: var(--sm-measure); margin: 0 auto; padding: 0 1.5rem; }
.sm-wide { max-width: var(--sm-wide);    margin: 0 auto; padding: 0 1.5rem; }

a { color: var(--sm-accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--sm-accent-soft); }

hr { border: 0; border-top: 1px solid var(--sm-rule); margin: 2.5rem 0; }

img, video { max-width: 100%; height: auto; }

/* THE hidden ATTRIBUTE ONLY WORKS IF NOTHING OVERRIDES IT.
   `hidden` hides an element because the BROWSER's stylesheet says
   [hidden] { display: none }. Any author rule that sets display on the same
   element wins, because author origin beats user-agent origin -- so
   `.sm-lightbox { display: flex }` left a fixed, full-screen, opaque overlay
   permanently on top of the gallery, and `.sm-tile { display: block }` made
   the filter buttons do nothing visible while the JS dutifully set
   tile.hidden. One missing line, three broken features, and every one of them
   looked like a JavaScript bug.
   !important because the whole point is to beat every later display rule. */
[hidden] { display: none !important; }
"""

_CHROME = """
.sm-head { border-bottom: 1px solid var(--sm-rule); margin-bottom: 3rem; }
.sm-head-inner {
  display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 0.6rem 1.6rem; padding: 1.4rem 1.5rem;
  max-width: var(--sm-wide); margin: 0 auto;
}
.sm-wordmark {
  font-family: var(--sm-serif); font-size: 1.15rem; font-weight: 600;
  letter-spacing: 0.01em; color: var(--sm-ink); text-decoration: none;
  margin-right: auto;
}
.sm-nav { display: flex; flex-wrap: wrap; gap: 1.25rem; }
.sm-nav a {
  font-family: var(--sm-sans); font-size: 0.82rem; letter-spacing: 0.06em;
  text-transform: uppercase; text-decoration: none; color: var(--sm-ink-soft);
}
.sm-nav a:hover { color: var(--sm-accent); }
.sm-nav a[aria-current="page"] { color: var(--sm-ink); border-bottom: 2px solid var(--sm-accent); }

/* A DEPARTURE, not navigation. /mana-map/ is a different repository and a
   different visual world; the arrow and the colour say you are leaving. */
.sm-nav a.sm-depart { color: var(--sm-depart); }
.sm-nav a.sm-depart::after { content: " \\2197"; font-size: 0.9em; }

.sm-foot {
  border-top: 1px solid var(--sm-rule); margin-top: 5rem; padding: 2rem 1.5rem 3rem;
  font-family: var(--sm-sans); font-size: 0.82rem; color: var(--sm-ink-faint);
}
.sm-foot-inner { max-width: var(--sm-wide); margin: 0 auto;
                 display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; }
.sm-foot a { color: var(--sm-ink-soft); }
"""

_PROSE = """
.sm-title {
  font-size: clamp(2rem, 5vw, 2.9rem); line-height: 1.12; font-weight: 600;
  letter-spacing: -0.015em; margin: 0 0 0.6rem;
}
.sm-dateline {
  font-family: var(--sm-sans); font-size: 0.8rem; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--sm-ink-faint); margin: 0 0 2.5rem;
}
.sm-dateline a { color: var(--sm-ink-soft); text-decoration: none; }
.sm-dateline a:hover { color: var(--sm-accent); }

.sm-lede { font-size: 1.24rem; line-height: 1.5; color: var(--sm-ink-soft); margin: 0 0 2.5rem; }

.sm-prose > * + * { margin-top: 1.35em; }
.sm-prose h2 {
  font-size: 1.6rem; line-height: 1.2; font-weight: 600; letter-spacing: -0.01em;
  margin-top: 2.8em; margin-bottom: 0.2em;
}
.sm-prose h3 { font-size: 1.25rem; font-weight: 600; margin-top: 2.2em; margin-bottom: 0.2em; }
.sm-prose h4 { font-size: 1.05rem; font-weight: 600; margin-top: 2em; margin-bottom: 0.2em; }
.sm-prose h2 + *, .sm-prose h3 + *, .sm-prose h4 + * { margin-top: 0.4em; }

/* A heading anchor that is invisible until you want it. */
.sm-anchor {
  float: left; margin-left: -1.1em; padding-right: 0.35em;
  color: var(--sm-rule); text-decoration: none; opacity: 0;
  transition: opacity 0.12s ease-in;
}
:is(h2, h3, h4):hover .sm-anchor, .sm-anchor:focus { opacity: 1; }

.sm-prose blockquote {
  margin-left: 0; margin-right: 0; padding-left: 1.2rem;
  border-left: 2px solid var(--sm-rule); color: var(--sm-ink-soft); font-style: italic;
}
.sm-prose ul, .sm-prose ol { padding-left: 1.4rem; }
.sm-prose li + li { margin-top: 0.4em; }

.sm-prose table {
  width: 100%; border-collapse: collapse; font-size: 0.94rem;
  font-family: var(--sm-sans);
}
.sm-prose th, .sm-prose td {
  text-align: left; padding: 0.5rem 0.7rem; border-bottom: 1px solid var(--sm-rule-soft);
}
.sm-prose th { font-weight: 600; border-bottom: 1px solid var(--sm-rule); }
.sm-table-scroll { overflow-x: auto; }

.sm-prose :not(pre) > code {
  font-family: var(--sm-mono); font-size: 0.87em;
  background: var(--sm-paper-sunk); padding: 0.12em 0.32em; border-radius: 3px;
}

/* Inline mathematics recovered from QuickLaTeX alt text. */
.sm-math { font-family: var(--sm-serif); font-style: italic; white-space: nowrap; }
"""

_FIGURES = """
figure { margin: 2.5rem 0; }
figure img, figure video { display: block; width: 100%; border-radius: 2px; }
figcaption {
  font-family: var(--sm-sans); font-size: 0.82rem; line-height: 1.45;
  color: var(--sm-ink-faint); margin-top: 0.6rem;
}
figcaption b, figcaption strong { color: var(--sm-ink-soft); font-weight: 600; }

/* A gallery is a GROUP. Markdown cannot say "these four images are one
   thing", which is why the converter keeps galleries as raw HTML. */
.sm-gallery { display: grid; gap: 0.8rem; margin: 2.5rem 0;
              grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.sm-gallery figure { margin: 0; }

/* A gallery that carries its OWN caption describing the whole grid, as
   distinct from captions on the individual images inside it. */
.sm-gallery-fig { margin: 2.5rem 0; }
.sm-gallery-fig .sm-gallery { margin: 0 0 0.6rem; }

/* Figures may breathe past the measure on a wide screen. */
@media (min-width: 60rem) {
  .sm-prose > figure.sm-wide-fig { width: 52rem; margin-left: calc((46rem - 52rem) / 2); }
}

/* The <noscript> fallback that every interactive page is required to carry. */
.sm-fallback { margin: 0; }
.sm-fallback figcaption::before { content: "Static view. "; font-weight: 600; }
"""

_CARDS = """
.sm-list { list-style: none; padding: 0; margin: 0; }
.sm-item { padding: 1.6rem 0; border-bottom: 1px solid var(--sm-rule-soft); }
.sm-item:first-child { padding-top: 0; }
.sm-item h2 { font-size: 1.35rem; line-height: 1.25; font-weight: 600; margin: 0 0 0.3rem; }
.sm-item h2 a { color: var(--sm-ink); text-decoration: none; }
.sm-item h2 a:hover { color: var(--sm-accent); text-decoration: underline; }
.sm-item p { margin: 0.3rem 0 0; color: var(--sm-ink-soft); font-size: 1rem; }
.sm-meta {
  font-family: var(--sm-sans); font-size: 0.76rem; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--sm-ink-faint);
}
.sm-meta a { color: var(--sm-ink-faint); text-decoration: none; }
.sm-meta a:hover { color: var(--sm-accent); }

.sm-section-head {
  font-family: var(--sm-sans); font-size: 0.78rem; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--sm-ink-faint);
  border-bottom: 1px solid var(--sm-rule); padding-bottom: 0.5rem; margin: 3.5rem 0 0;
}

.sm-pills { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1.5rem 0 0; padding: 0; list-style: none; }
.sm-pills a {
  display: inline-block; font-family: var(--sm-sans); font-size: 0.78rem;
  padding: 0.25rem 0.6rem; border: 1px solid var(--sm-rule); border-radius: 999px;
  text-decoration: none; color: var(--sm-ink-soft);
}
.sm-pills a:hover { border-color: var(--sm-accent); color: var(--sm-accent); }

/* The hand-off card for /mana-map/. It is a departure to another repository
   and another visual world, so it is drawn as a card you leave through. */
.sm-depart-card {
  display: block; border: 1px solid var(--sm-rule); border-left: 3px solid var(--sm-depart);
  padding: 1.2rem 1.4rem; margin: 2rem 0; text-decoration: none; color: inherit;
  background: var(--sm-paper-sunk);
}
.sm-depart-card:hover { border-color: var(--sm-depart); }
.sm-depart-card strong { display: block; font-size: 1.15rem; margin-bottom: 0.25rem; color: var(--sm-ink); }
.sm-depart-card span { font-family: var(--sm-sans); font-size: 0.9rem; color: var(--sm-ink-soft); }
"""

_GALLERY = """
/* Panel beside the grid on a wide screen, above it on a narrow one. The panel
   is `position: sticky` so the facets stay reachable while the grid scrolls --
   a filter you have to scroll back up to reach is a filter people stop
   using. */
.sm-gallery-layout { display: grid; grid-template-columns: 210px 1fr; gap: 2rem; }
/* The gallery gets its own width. Everything else on the site is prose and
   wants a narrow measure; a grid of pictures wants the screen. */
main.sm-gallery-wide { max-width: var(--sm-gallery); }
@media (max-width: 52rem) {
  .sm-gallery-layout { grid-template-columns: 1fr; gap: 1.2rem; }
  .sm-panel { position: static !important; max-height: none !important; }
  .sm-facet-pills { flex-direction: row !important; }
}

.sm-panel {
  position: sticky; top: 1.5rem; align-self: start;
  max-height: calc(100vh - 3rem); overflow-y: auto;
  font-family: var(--sm-sans);
}
.sm-panel-head { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.2rem; }
.sm-clear, .sm-play {
  font-family: var(--sm-sans); font-size: 0.74rem; letter-spacing: 0.04em;
  padding: 0.3rem 0.75rem; border-radius: 999px; background: none; cursor: pointer;
  border: 1px solid var(--sm-rule); color: var(--sm-ink-soft);
}
.sm-clear:hover { border-color: var(--sm-accent); color: var(--sm-accent); }
.sm-play { border-color: var(--sm-depart); color: var(--sm-depart); }

.sm-facet { margin: 0 0 1.4rem; }
.sm-facet h2 {
  font-size: 0.7rem; letter-spacing: 0.11em; text-transform: uppercase;
  color: var(--sm-ink-faint); margin: 0 0 0.5rem; font-weight: 600;
}
/* A lexicon facet is a GUESS from prompt text, unlike a field or a measured
   dimension. The dotted rule is the quietest honest way to say so. */
.sm-facet[data-kind="lexicon"] h2 { border-bottom: 1px dotted var(--sm-rule); padding-bottom: 0.3rem; }

.sm-facet-pills { display: flex; flex-direction: column; gap: 0.3rem;
                  flex-wrap: wrap; margin: 0; padding: 0; list-style: none; }
.sm-pill {
  display: inline-flex; align-items: baseline; gap: 0.4rem;
  font-size: 0.8rem; padding: 0.22rem 0.62rem; border-radius: 999px;
  border: 1px solid var(--sm-rule); text-decoration: none;
  color: var(--sm-ink-soft); background: none; cursor: pointer;
  transition: border-color 0.1s ease-in, color 0.1s ease-in;
}
.sm-pill span { font-size: 0.72rem; color: var(--sm-ink-faint);
                font-variant-numeric: tabular-nums; }
.sm-pill:hover { border-color: var(--sm-accent); color: var(--sm-accent); }
.sm-pill.is-on { background: var(--sm-ink); color: var(--sm-paper);
                 border-color: var(--sm-ink); }
.sm-pill.is-on span { color: var(--sm-paper-sunk); }
/* Dimmed, not removed: a facet that vanishes when you pick something else
   makes the collection feel smaller than it is. */
.sm-pill.is-off { opacity: 0.35; }

/* ROW ORDER, which means a grid and not CSS columns.
   `columns` fills each column top-to-bottom before starting the next, so the
   second picture sits BELOW the first rather than beside it -- the reading
   order runs down the page while the eye expects it to run across. A grid
   places items across each row in document order, which for a gallery sorted
   newest-first is the only order that makes sense.
   `align-items: start` keeps every image at its own aspect ratio: these run
   1:1 and 3:4 and a few 16:9, and stretching a row to a common height would
   crop or letterbox most of them. Row bottoms are ragged as a result, which
   is the honest trade. */
.sm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 0.7rem;
  align-items: start;
}
.sm-tile { display: block; margin: 0; line-height: 0; }
.sm-tile img { width: 100%; height: auto; border-radius: 2px;
               transition: opacity 0.12s ease-in; }
.sm-tile:hover img { opacity: 0.86; }
/* Preview only: a staged image is dimmed and corner-marked so curating is
   not guesswork about which of two thousand tiles is already live. */
.sm-tile[data-staged] img { opacity: 0.55; }
.sm-tile[data-staged]:hover img { opacity: 0.95; }
.sm-tile[data-staged]::after {
  content: ""; position: absolute; top: 5px; right: 5px; width: 7px; height: 7px;
  border-radius: 50%; background: var(--sm-accent);
}
.sm-tile { position: relative; }

/* The archive control exists ONLY while the local curation server is running
   -- gallery.js adds the class after probing /curate/health, which the
   deployed site does not have. A visitor never sees it. */
.sm-archive {
  position: absolute; top: 5px; left: 5px; width: 26px; height: 26px;
  border: 0; border-radius: 50%; cursor: pointer; line-height: 1;
  font-size: 1.05rem; background: rgba(20, 18, 15, 0.72); color: #fff;
  opacity: 0; transition: opacity 0.1s ease-in;
}
.sm-tile:hover .sm-archive, .sm-archive:focus { opacity: 1; }
.sm-archive:hover { background: var(--sm-accent); }
.sm-archive[disabled] { opacity: 1; background: var(--sm-ink-faint); cursor: wait; }

.sm-series { border-color: var(--sm-depart); color: var(--sm-depart); }
.sm-series.is-on { background: var(--sm-depart); color: var(--sm-paper); }
/* How many takes this tile stands for, while collapsed. */
.sm-takes {
  position: absolute; bottom: 6px; right: 6px; font-family: var(--sm-sans);
  font-size: 0.68rem; letter-spacing: 0.04em; padding: 0.14rem 0.45rem;
  border-radius: 999px; background: rgba(20, 18, 15, 0.78); color: #fff;
  pointer-events: none;
}

.sm-more-values { margin: 0.35rem 0 0; }
.sm-more-values > summary {
  cursor: pointer; font-family: var(--sm-sans); font-size: 0.72rem;
  color: var(--sm-ink-faint); padding: 0.2rem 0.1rem; list-style: none;
}
.sm-more-values > summary::before { content: "+ "; }
.sm-more-values[open] > summary::before { content: "\2212 "; }
.sm-more-values > summary:hover { color: var(--sm-accent); }
.sm-more-values > ul { margin-top: 0.3rem; }

.sm-more-facets { margin: 0.4rem 0 1.4rem; }
.sm-more-facets > summary {
  cursor: pointer; font-family: var(--sm-sans); font-size: 0.7rem;
  letter-spacing: 0.11em; text-transform: uppercase; color: var(--sm-ink-faint);
  padding: 0.35rem 0; border-top: 1px solid var(--sm-rule-soft);
}
.sm-more-facets > summary:hover { color: var(--sm-accent); }
.sm-more-facets > summary span { font-size: 0.78em; opacity: 0.8; }
.sm-more-facets[open] > summary { margin-bottom: 0.8rem; }

.sm-param-list { list-style: none; padding: 0; margin: 0.6rem 0 0;
                 display: flex; flex-direction: column; gap: 0.35rem; }
.sm-param-list code { font-family: var(--sm-mono); font-size: 0.8rem;
                      background: var(--sm-paper-sunk); padding: 0.2em 0.5em;
                      border-radius: 3px; }
/* While collapsed the badge is a LINK to the whole run, so the obvious click
   goes to the interesting thing rather than to one frame of it. */
a.sm-takes { pointer-events: auto; text-decoration: none; }
a.sm-takes:hover { background: var(--sm-accent); }

.sm-more-wrap { text-align: center; margin: 1.6rem 0 0; }
.sm-more {
  font-family: var(--sm-sans); font-size: 0.82rem; padding: 0.5rem 1.4rem;
  border: 1px solid var(--sm-rule); border-radius: 999px; background: none;
  color: var(--sm-ink-soft); cursor: pointer;
}
.sm-more:hover { border-color: var(--sm-accent); color: var(--sm-accent); }

.sm-lightbox {
  position: fixed; inset: 0; z-index: 50; background: rgba(12, 11, 9, 0.94);
  display: flex; align-items: center; justify-content: center; gap: 0.5rem;
  padding: 2rem 1rem;
}
.sm-lb-fig { margin: 0; max-width: 92vw; max-height: 88vh; display: flex;
             flex-direction: column; gap: 0.7rem; }
.sm-lb-fig img { max-width: 100%; max-height: 76vh; object-fit: contain;
                 border-radius: 2px; cursor: zoom-in; }

/* MAGNIFIED. The figure becomes a fixed window and the image sits inside it
   at its NATURAL size, panned by transform as the cursor moves -- so what you
   see is the actual pixels the model produced rather than an upscale of
   them. max-width/max-height have to be unset or the image would keep being
   squeezed to fit the very frame we are trying to look past. */
.sm-lightbox.is-zoomed .sm-lb-fig {
  overflow: hidden; width: 92vw; height: 82vh; max-width: none; max-height: none;
  cursor: zoom-out; align-items: flex-start;
}
.sm-lightbox.is-zoomed .sm-lb-fig img {
  max-width: none; max-height: none; width: auto; height: auto;
  cursor: zoom-out; transition: none; border-radius: 0;
}
/* The caption would push the image out of the window while magnified. */
.sm-lightbox.is-zoomed .sm-lb-fig figcaption { display: none; }
.sm-lightbox.is-zoomed .sm-lb-prev,
.sm-lightbox.is-zoomed .sm-lb-next { opacity: 0.25; }
.sm-lb-fig figcaption { font-family: var(--sm-sans); font-size: 0.8rem;
                        line-height: 1.5; color: #b9b2a3; max-width: 46rem;
                        margin: 0 auto; text-align: center;
                        max-height: 8em; overflow-y: auto; }
.sm-lightbox button {
  background: none; border: 0; color: #b9b2a3; font-size: 2.4rem; line-height: 1;
  cursor: pointer; padding: 0.4rem 0.8rem; flex: 0 0 auto;
}
.sm-lightbox button:hover { color: #fff; }
.sm-lb-close { position: absolute; top: 0.6rem; right: 1rem; font-size: 2rem; }

.sm-image-full { margin: 0 0 1.5rem; }
.sm-image-full img { width: 100%; height: auto; border-radius: 2px; }
.sm-prompt {
  font-family: var(--sm-mono); font-size: 0.86rem; line-height: 1.6;
  background: var(--sm-paper-sunk); border-left: 2px solid var(--sm-rule);
  padding: 0.9rem 1.1rem; color: var(--sm-ink-soft); white-space: pre-wrap;
}

@media print {
  .sm-panel, .sm-lightbox { display: none; }
  .sm-gallery-layout { display: block; }
  .sm-grid { grid-template-columns: repeat(2, 1fr); }
}
"""

_CODE = """
pre {
  font-family: var(--sm-mono); font-size: 0.84rem; line-height: 1.5;
  background: var(--sm-paper-sunk); border: 1px solid var(--sm-rule-soft);
  border-radius: 3px; padding: 0.9rem 1rem; overflow-x: auto;
}
pre code { font-family: inherit; font-size: inherit; background: none; padding: 0; }
"""

_PRINT = """
/* REAL print rules, not @media print cosmetics. The register is editorial and
   some of this is writing people will want on paper. Print is always
   ink-on-white regardless of the reader's colour scheme -- a dark page that
   prints as heavy grey is worse at the one job it has. */
@page { size: A4; margin: 20mm 18mm 22mm; }

@media print {
  :root {
    --sm-paper: #fff; --sm-paper-sunk: #f6f6f6; --sm-ink: #000;
    --sm-ink-soft: #333; --sm-ink-faint: #555;
    --sm-rule: #bbb; --sm-rule-soft: #ddd; --sm-accent: #000; --sm-depart: #000;
  }
  body { font-size: 11pt; }
  .sm-head, .sm-foot, .sm-nav, .sm-anchor { display: none; }
  .sm-trim, .sm-wide { max-width: none; padding: 0; }
  a { color: inherit; text-decoration: none; }
  /* A printed page cannot be clicked, so an external link must say where it
     went. Internal ones resolve against the site and are left alone. */
  .sm-prose a[href^="http"]::after {
    content: " (" attr(href) ")"; font-size: 0.85em; color: #555; word-break: break-all;
  }
  h2, h3, h4 { break-after: avoid; }
  figure, pre, table, blockquote { break-inside: avoid; }
  p, li { orphans: 3; widows: 3; }
}
"""


def _pygments_css():
    """Generated at build time from the PINNED pygments version.

    This is why the committed docs/site.css doubles as a lockfile check: a
    pygments bump changes these bytes, the byte-diff gate goes red, and someone
    looks at it. That is the gate working, not the gate failing.
    """
    from pygments.formatters import HtmlFormatter
    light = HtmlFormatter(style="tango").get_style_defs(".hl")
    dark = HtmlFormatter(style="nord").get_style_defs(".hl")
    dark = "\n".join("  " + ln for ln in dark.split("\n") if ln.strip())
    return (light
            + "\n@media (prefers-color-scheme: dark) {\n" + dark + "\n}\n"
            + "@media print {\n"
            + "\n".join("  " + ln for ln in light.split("\n") if ln.strip())
            + "\n}\n")


def stylesheet():
    parts = [_TOKENS.replace("MEASURE", spec.MEASURE), _BASE, _CHROME,
             _PROSE, _FIGURES, _CARDS, _GALLERY, _CODE, _pygments_css(), _PRINT]
    return "\n".join(p.strip("\n") for p in parts) + "\n"


def stylesheet_version():
    """Content hash -> the cache-buster. No integer for anyone to forget."""
    return hashlib.sha256(stylesheet().encode("utf-8")).hexdigest()[:8]
