/**
 * The gallery: faceted filtering, lightbox, slideshow.
 *
 * The page works before this runs. Tiles are rendered server-side and every
 * facet pill is a real <a> to a fragment URL, so with JavaScript blocked you
 * still get the whole collection and a readable index of what is in it. This
 * upgrades those links into toggles and filters in place.
 *
 * FILTER SEMANTICS: OR inside a group, AND across groups. Picking `gold` and
 * `crystal` under Material shows both; adding `weathered` under Condition
 * narrows to images that are (gold OR crystal) AND weathered. That is what
 * people expect from faceted search, and the alternative -- AND everywhere --
 * makes a second click inside one group always return nothing.
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
    return; // leave the server-rendered page exactly as it is
  }

  var bySlug = {};
  items.forEach(function (it) { bySlug[it.s] = it; });

  var tiles = [].slice.call(grid.querySelectorAll(".sm-tile"));
  var pills = [].slice.call(document.querySelectorAll(".sm-pill"));
  var clearBtn = document.querySelector(".sm-clear");
  var playBtn = document.querySelector(".sm-play");
  var countEl = document.getElementById("sm-count");
  var box = document.getElementById("sm-lightbox");

  var selected = {};            // group -> [values]
  var visible = tiles.slice();
  var total = tiles.length;

  // SHOW A PAGE AT A TIME. Two and a half thousand tiles at once is
  // unreadable before it is slow, and scanning is the whole job here.
  var CHUNK = 120;
  var shown = CHUNK;
  var moreBtn = document.querySelector(".sm-more");

  // ONE PER PROMPT. This archive was made by re-running prompts to explore
  // what the model does differently each time, so a "take" is not a
  // duplicate -- but 2,342 takes of 398 ideas is unreadable. Collapsed, the
  // newest take of each prompt stands for the series and carries its count.
  var seriesMode = false;
  var seriesBtn = document.querySelector(".sm-series");
  var counts = {};
  items.forEach(function (it) { counts[it.r] = (counts[it.r] || 0) + 1; });

  [clearBtn, playBtn].forEach(function (b) { if (b) b.hidden = false; });

  function matches(it) {
    for (var group in selected) {
      var want = selected[group];
      if (!want.length) continue;
      var has = (it.x && it.x[group]) || [];
      var ok = false;
      for (var i = 0; i < want.length; i++) {
        if (has.indexOf(want[i]) !== -1) { ok = true; break; }
      }
      if (!ok) return false;     // AND across groups
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

  function paint() {
    visible.forEach(function (tile, i) { tile.hidden = i >= shown; });
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
      var left = visible.length - shown;
      moreBtn.hidden = left <= 0;
      moreBtn.textContent = left > 0
        ? "Show " + Math.min(CHUNK, left) + " more (" + left + " left)"
        : "";
    }
  }

  function apply(keepShown) {
    visible = [];
    var seenSeries = {};
    tiles.forEach(function (tile) {
      var it = bySlug[tile.dataset.slug];
      var show = !it || matches(it);
      if (show && seriesMode && it) {
        // Tiles are already newest-first, so the first one kept for a series
        // is its most recent take.
        if (seenSeries[it.r]) show = false;
        else seenSeries[it.r] = true;
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
      // Dim a pill that would return nothing, rather than letting someone
      // click into an empty grid and wonder what broke.
      var n = availability(g, v);
      pill.classList.toggle("is-off", n === 0 && !on);
      var badge = pill.querySelector("span");
      if (badge) badge.textContent = n;
    });

    if (countEl) {
      var noun = seriesMode ? " prompts" : " images";
      var head = (!seriesMode && visible.length === total)
        ? total + noun
        : visible.length + (seriesMode ? noun + " of " + total + " takes"
                                       : " of " + total + noun);
      countEl.textContent = visible.length > shown
        ? head + " \u2014 showing " + shown
        : head;
    }
    if (clearBtn) clearBtn.hidden = active === 0;

    // A badge saying how many takes this tile stands for, shown only while
    // collapsed -- on the full grid every take is already on screen.
    tiles.forEach(function (tile) {
      var badge = tile.querySelector(".sm-takes");
      var it = bySlug[tile.dataset.slug];
      var n = it ? counts[it.r] : 1;
      if (seriesMode && n > 1) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "sm-takes";
          tile.appendChild(badge);
        }
        badge.textContent = n + " takes";
        badge.hidden = false;
      } else if (badge) {
        badge.hidden = true;
      }
    });

    var parts = [];
    for (var g in selected) {
      if (selected[g].length) parts.push(g + "=" + selected[g].join(","));
    }
    history.replaceState(null, "", parts.length
      ? "#" + parts.join("&") : location.pathname);
  }

  function toggle(group, value) {
    var list = selected[group] || (selected[group] = []);
    var at = list.indexOf(value);
    if (at === -1) list.push(value); else list.splice(at, 1);
    apply();
  }

  pills.forEach(function (pill) {
    pill.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return;  // let it open a link
      ev.preventDefault();
      toggle(pill.dataset.group, pill.dataset.value);
    });
  });

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

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      selected = {};
      apply();
    });
  }

  // A per-image page links back as #material=gold, so the filter survives the
  // round trip.
  (function fromHash() {
    var hash = decodeURIComponent(location.hash.slice(1));
    if (!hash) return;
    hash.split("&").forEach(function (part) {
      var bits = part.split("=");
      if (bits.length === 2 && bits[1]) selected[bits[0]] = bits[1].split(",");
    });
  })();
  apply();

  // -------------------------------------------------------- local curation
  //
  // Probed once, and ABSENT rather than broken when it is not there. The
  // deployed site has no /curate endpoint, so these buttons never exist for a
  // visitor -- the same way the sibling mana-map repo gates its local API.

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
      btn.textContent = "\u00d7";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        btn.disabled = true;
        fetch("/curate/status", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ ids: [tile.dataset.id], status: "archived" }),
        }).then(function (r) { return r.json(); }).then(function (res) {
          if (!res.ok) { btn.disabled = false; return; }
          // Drop it from the working set so counts and the slideshow agree
          // with what is on screen.
          var at = tiles.indexOf(tile);
          if (at !== -1) tiles.splice(at, 1);
          total = tiles.length;
          tile.remove();
          apply(true);
        }).catch(function () { btn.disabled = false; });
      });
      tile.appendChild(btn);
    });
  }).catch(function () { /* no curation server: nothing to do */ });

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
