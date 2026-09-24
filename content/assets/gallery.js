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

  function apply() {
    visible = [];
    tiles.forEach(function (tile) {
      var it = bySlug[tile.dataset.slug];
      var show = !it || matches(it);
      tile.hidden = !show;
      if (show) visible.push(tile);
    });

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
      countEl.textContent = visible.length === total
        ? total + " images"
        : visible.length + " of " + total + " images";
    }
    if (clearBtn) clearBtn.hidden = active === 0;

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
