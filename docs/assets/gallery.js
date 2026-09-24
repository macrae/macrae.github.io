/**
 * The gallery: filters, lightbox, slideshow.
 *
 * Everything it needs is already in the page -- the tiles are rendered
 * server-side and the metadata is a JSON data island -- so this enhances a
 * working page rather than building one. With the script blocked you still get
 * every image, every link, and every per-image page with its prompt. That is
 * why the controls start hidden: a reader without JavaScript should never see
 * a button that does nothing.
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
    return; // leave the server-rendered grid exactly as it is
  }

  var bySlug = {};
  items.forEach(function (it) { bySlug[it.s] = it; });

  var tiles = Array.prototype.slice.call(grid.querySelectorAll(".sm-tile"));
  var controls = document.querySelector(".sm-controls");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".sm-chip"));
  var visible = tiles.slice();

  if (controls) controls.hidden = false;

  // ---------------------------------------------------------------- filter

  function apply(filter) {
    visible = [];
    tiles.forEach(function (tile) {
      var it = bySlug[tile.dataset.slug];
      var show = filter === "all" ||
        (filter.indexOf("c:") === 0 && it && it.c === filter.slice(2)) ||
        (filter.indexOf("g:") === 0 && it && it.g.indexOf(filter.slice(2)) !== -1);
      // `hidden` rather than style.display, so the page keeps working if the
      // stylesheet fails to load.
      tile.hidden = !show;
      if (show) visible.push(tile);
    });
    chips.forEach(function (c) {
      c.classList.toggle("is-on", c.dataset.filter === filter);
    });
    if (location.hash.slice(1) !== filter && filter !== "all") {
      history.replaceState(null, "", "#" + filter);
    } else if (filter === "all" && location.hash) {
      history.replaceState(null, "", location.pathname);
    }
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () { apply(chip.dataset.filter); });
  });

  // A per-image page links back as /gallery/#c:gameboy, so the filter it came
  // from is still applied when the reader returns.
  var initial = decodeURIComponent(location.hash.slice(1));
  apply(initial && (initial.indexOf("c:") === 0 || initial.indexOf("g:") === 0)
        ? initial : "all");

  // -------------------------------------------------------------- lightbox

  var box = document.getElementById("sm-lightbox");
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
    cap.textContent = it.a || it.p;
    box.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function close() {
    box.hidden = true;
    document.body.style.overflow = "";
    stop();
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    var play = document.querySelector(".sm-play");
    if (play) play.textContent = "Slideshow";
  }

  tiles.forEach(function (tile) {
    tile.addEventListener("click", function (ev) {
      // Plain click opens the lightbox; modified clicks and middle-click keep
      // their normal meaning, because the tile is a real link to a real page.
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;
      ev.preventDefault();
      show(visible.indexOf(tile));
    });
  });

  box.querySelector(".sm-lb-close").addEventListener("click", close);
  box.querySelector(".sm-lb-next").addEventListener("click", function () { show(at + 1); });
  box.querySelector(".sm-lb-prev").addEventListener("click", function () { show(at - 1); });
  box.addEventListener("click", function (ev) { if (ev.target === box) close(); });

  document.addEventListener("keydown", function (ev) {
    if (box.hidden) return;
    if (ev.key === "Escape") close();
    else if (ev.key === "ArrowRight") { stop(); show(at + 1); }
    else if (ev.key === "ArrowLeft") { stop(); show(at - 1); }
  });

  // ------------------------------------------------------------- slideshow

  var play = document.querySelector(".sm-play");
  if (play) {
    play.addEventListener("click", function () {
      if (timer) { stop(); return; }
      if (box.hidden) show(0);
      play.textContent = "Stop";
      timer = setInterval(function () { show(at + 1); }, 3500);
    });
  }
})();
