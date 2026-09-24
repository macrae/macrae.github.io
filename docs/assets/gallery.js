/**
 * The gallery: faceted filtering, series collapse, lightbox, slideshow.
 *
 * The page works before this runs. Tiles are rendered server-side and every
 * facet pill is a real <a> to a fragment URL, so with JavaScript blocked you
 * still get the whole collection and a readable index of what is in it. This
 * upgrades those links into toggles and filters in place.
 *
 * FILTER SEMANTICS: OR inside a group, AND across groups. Picking `gold` and
 * `crystal` under Material shows both; adding `weathered` under Condition
 * narrows to images that are (gold OR crystal) AND weathered. ANDing
 * everywhere would make a second click inside one group always return nothing.
 *
 * SERIES: this archive was made by re-running prompts, so a "take" is not a
 * duplicate. Collapsed, one tile stands for each prompt and carries a link to
 * the whole run.
 *
 * Rewritten rather than patched again: four rounds of string edits left a
 * listener attached inside paint(), so every repaint added another one and a
 * single click toggled the mode twice -- back to where it started, silently.
 */
(function () {
  "use strict";

  var grid = document.getElementById("sm-grid");
  var dataEl = document.getElementById("sm-gallery-data");
  if (!grid || !dataEl) return;

  var items;
  try {
    items = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;                       // leave the server-rendered page alone
  }

  var bySlug = {};
  var takes = {};
  items.forEach(function (it) {
    bySlug[it.s] = it;
    takes[it.r] = (takes[it.r] || 0) + 1;
  });

  var tiles = [].slice.call(grid.querySelectorAll(".sm-tile"));
  var pills = [].slice.call(document.querySelectorAll(".sm-pill"));
  var clearBtn = document.querySelector(".sm-clear");
  var playBtn = document.querySelector(".sm-play");
  var seriesBtn = document.querySelector(".sm-series");
  var moreBtn = document.querySelector(".sm-more");
  var countEl = document.getElementById("sm-count");
  var box = document.getElementById("sm-lightbox");

  var CHUNK = 120;
  var selected = {};              // group -> [values]
  var seriesMode = false;
  var shown = CHUNK;
  var visible = [];
  var total = tiles.length;

  // ------------------------------------------------------------ filtering

  function matches(it) {
    for (var group in selected) {
      var want = selected[group];
      if (!want.length) continue;
      var has = (it.x && it.x[group]) || [];
      var ok = false;
      for (var i = 0; i < want.length; i++) {
        if (has.indexOf(want[i]) !== -1) { ok = true; break; }
      }
      if (!ok) return false;      // AND across groups
    }
    return true;
  }

  /** How many images a pill would yield, given every OTHER group's choice. */
  function availability(group, value) {
    var n = 0;
    for (var i = 0; i < items.length; i++) {
      var it = items[i], ok = true;
      for (var g in selected) {
        if (g === group || !selected[g].length) continue;
        var has = (it.x && it.x[g]) || [];
        var any = false;
        for (var j = 0; j < selected[g].length; j++) {
          if (has.indexOf(selected[g][j]) !== -1) { any = true; break; }
        }
        if (!any) { ok = false; break; }
      }
      if (ok && ((it.x && it.x[group]) || []).indexOf(value) !== -1) n++;
    }
    return n;
  }

  // ------------------------------------------------------------- painting

  function badgeFor(tile) {
    var badge = tile.querySelector(".sm-takes");
    if (badge) return badge;
    badge = document.createElement("a");
    badge.className = "sm-takes";
    tile.appendChild(badge);
    return badge;
  }

  function paint() {
    visible.forEach(function (tile, i) { tile.hidden = i >= shown; });

    if (moreBtn) {
      var left = visible.length - shown;
      moreBtn.hidden = left <= 0;
      moreBtn.textContent = "Show " + Math.min(CHUNK, left) + " more of " + left;
    }

    if (countEl) {
      var head;
      if (seriesMode) {
        head = visible.length + " prompts of " + total + " takes";
      } else {
        head = visible.length === total
          ? total + " images"
          : visible.length + " of " + total + " images";
      }
      countEl.textContent = visible.length > shown
        ? head + " — showing " + shown
        : head;
    }
  }

  function apply(keepShown) {
    var seen = {};
    visible = [];
    tiles.forEach(function (tile) {
      var it = bySlug[tile.dataset.slug];
      var show = !it || matches(it);
      if (show && seriesMode && it) {
        // Tiles are newest-first, so the survivor of a run is its latest take.
        if (seen[it.r]) show = false;
        else seen[it.r] = true;
      }
      tile.hidden = true;
      if (show) visible.push(tile);
    });
    if (!keepShown) shown = CHUNK;
    paint();

    var active = 0;
    pills.forEach(function (pill) {
      var g = pill.dataset.group, v = pill.dataset.value;
      var on = (selected[g] || []).indexOf(v) !== -1;
      pill.classList.toggle("is-on", on);
      if (on) active++;
      var n = availability(g, v);
      // Dim rather than remove: a facet that vanishes makes the collection
      // feel smaller than it is.
      pill.classList.toggle("is-off", n === 0 && !on);
      var badge = pill.querySelector("span");
      if (badge) badge.textContent = n;
    });
    if (clearBtn) clearBtn.hidden = active === 0;

    tiles.forEach(function (tile) {
      var it = bySlug[tile.dataset.slug];
      var n = it ? takes[it.r] : 1;
      if (seriesMode && n > 1 && it) {
        var badge = badgeFor(tile);
        badge.href = "/gallery/series/" + it.rs + "/";
        badge.title = "See all " + n + " takes of this prompt";
        badge.textContent = n + " takes";
        badge.hidden = false;
      } else {
        var existing = tile.querySelector(".sm-takes");
        if (existing) existing.hidden = true;
      }
    });

    var parts = [];
    for (var g2 in selected) {
      if (selected[g2].length) parts.push(g2 + "=" + selected[g2].join(","));
    }
    if (seriesMode) parts.push("series=1");
    history.replaceState(null, "", parts.length
      ? "#" + parts.join("&") : location.pathname);
  }

  // -------------------------------------------------------------- controls

  pills.forEach(function (pill) {
    pill.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
      ev.preventDefault();
      var g = pill.dataset.group, v = pill.dataset.value;
      var list = selected[g] || (selected[g] = []);
      var at = list.indexOf(v);
      if (at === -1) list.push(v); else list.splice(at, 1);
      apply();
    });
  });

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      selected = {};
      apply();
    });
  }

  if (seriesBtn) {
    seriesBtn.hidden = false;
    seriesBtn.addEventListener("click", function () {
      seriesMode = !seriesMode;
      seriesBtn.classList.toggle("is-on", seriesMode);
      seriesBtn.textContent = seriesMode ? "Every take" : "One per prompt";
      apply();
    });
  }

  if (moreBtn) {
    moreBtn.addEventListener("click", function () {
      shown += CHUNK;
      apply(true);
    });
  }

  if (playBtn) playBtn.hidden = false;

  (function fromHash() {
    var hash = decodeURIComponent(location.hash.slice(1));
    if (!hash) return;
    hash.split("&").forEach(function (part) {
      var bits = part.split("=");
      if (bits.length !== 2 || !bits[1]) return;
      if (bits[0] === "series") {
        seriesMode = bits[1] === "1";
        if (seriesBtn) {
          seriesBtn.classList.toggle("is-on", seriesMode);
          seriesBtn.textContent = seriesMode ? "Every take" : "One per prompt";
        }
      } else {
        selected[bits[0]] = bits[1].split(",");
      }
    });
  })();
  apply();

  // -------------------------------------------------------- local curation
  //
  // Probed once, and ABSENT rather than broken when missing. The deployed
  // site has no /curate, so these buttons never exist for a visitor.

  fetch("/curate/health").then(function (r) {
    return r.ok ? r.json() : null;
  }).then(function (health) {
    if (!health || !health.ok) return;
    document.body.classList.add("sm-curating");
    tiles.forEach(function (tile) {
      var btn = document.createElement("button");
      btn.className = "sm-archive";
      btn.type = "button";
      btn.title = "Archive — hide from the site (kept in git)";
      btn.textContent = "×";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        btn.disabled = true;
        fetch("/curate/status", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ ids: [tile.dataset.id], status: "archived" })
        }).then(function (r) { return r.json(); }).then(function (res) {
          if (!res.ok) { btn.disabled = false; return; }
          var at = tiles.indexOf(tile);
          if (at !== -1) tiles.splice(at, 1);
          total = tiles.length;
          tile.remove();
          apply(true);
        }).catch(function () { btn.disabled = false; });
      });
      tile.appendChild(btn);
    });
  }).catch(function () { /* no curation server */ });

  // -------------------------------------------------------------- lightbox

  if (!box) return;
  var img = box.querySelector("img");
  var cap = box.querySelector("figcaption");
  var at = -1;
  var timer = null;

  function show(i) {
    if (!visible.length) return;
    at = (i + visible.length) % visible.length;
    var it = bySlug[visible[at].dataset.slug];
    if (!it) return;
    img.src = "/gallery/images/" + it.f;
    img.alt = it.a || it.p.slice(0, 120);
    cap.textContent = it.a ? it.a + " — " + it.p : it.p;
    box.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    if (playBtn) playBtn.textContent = "Slideshow";
  }

  function close() {
    box.hidden = true;
    document.body.style.overflow = "";
    stop();
  }

  tiles.forEach(function (tile) {
    tile.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;
      if (ev.target.closest(".sm-takes, .sm-archive")) return;
      ev.preventDefault();
      show(visible.indexOf(tile));
    });
  });

  box.querySelector(".sm-lb-close").addEventListener("click", close);
  box.querySelector(".sm-lb-next").addEventListener("click", function () { stop(); show(at + 1); });
  box.querySelector(".sm-lb-prev").addEventListener("click", function () { stop(); show(at - 1); });
  box.addEventListener("click", function (ev) { if (ev.target === box) close(); });

  document.addEventListener("keydown", function (ev) {
    if (box.hidden) return;
    if (ev.key === "Escape") close();
    else if (ev.key === "ArrowRight") { stop(); show(at + 1); }
    else if (ev.key === "ArrowLeft") { stop(); show(at - 1); }
  });

  if (playBtn) {
    playBtn.addEventListener("click", function () {
      if (timer) { stop(); return; }
      if (box.hidden) show(0);
      playBtn.textContent = "Stop";
      timer = setInterval(function () { show(at + 1); }, 3500);
    });
  }
})();
