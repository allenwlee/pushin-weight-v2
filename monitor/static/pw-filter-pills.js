// Pushin' Weight (走个量) filter-pill behavior.
//
// Behavior:
//   - Drag-to-scroll on .filter-bar-scroller (horizontal, 6px threshold).
//   - Single open-state authority per pill (`is-open` class, set on pointerup
//     so a drag does not toggle a pill open).
//   - Dropdown geometry aligned to filter-bar box (not viewport).
//   - Segmented lens (Brands Open/Closed, Nationalism US/CN) with per-tier
//     counts + scoped all/clear buttons (data-dd-scope="visible").
//   - Keyboard: Enter/Space toggle pill; Escape closes.
//   - Status-dot reflection on each pill ("is-default" vs "is-changed").
//
// References / invariants pinned by tests/regression_net.py and
// tests/test_home_v22_filter_pills.py:
//   - `.filter-bar-scroller` exists + drag handler attached
//   - `.filter-pill.is-open` is the single open-state authority
//   - `.filter-dropdown` placement uses filter-bar box not viewport
//   - Branded pill has `data-tier-grid="open"` + `data-tier-grid="closed"`
//   - Nationalism pill has `data-tier-grid="us"` + `data-tier-grid="cn"`
//   - `dd-toolbar` with `data-dd-scope="visible"` exists on lens pills

(function () {
  "use strict";

  var bar = document.querySelector(".filter-bar");
  if (!bar) return;
  var scroller = bar.querySelector(".filter-bar-scroller");
  var pills = Array.prototype.slice.call(bar.querySelectorAll(".filter-pill"));

  // --- Panel aligns to filter-bar (same width as topbar / pulse / chart cards) ---
  function placeDropdown(pill) {
    var dd = pill.querySelector(".filter-dropdown");
    if (!dd) return;
    var barR = bar.getBoundingClientRect();
    dd.style.top = Math.round(barR.bottom + 2) + "px";
    dd.style.left = Math.round(barR.left) + "px";
    dd.style.width = Math.round(barR.width) + "px";
    dd.style.right = "auto";
  }

  function setExpanded(pill, open) {
    pill.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAll() {
    pills.forEach(function (p) {
      p.classList.remove("is-open");
      setExpanded(p, false);
    });
  }

  function openPill(pill) {
    closeAll();
    pill.classList.add("is-open");
    setExpanded(pill, true);
    requestAnimationFrame(function () {
      placeDropdown(pill);
      requestAnimationFrame(function () { placeDropdown(pill); });
    });
  }

  function refreshDots() {
    pills.forEach(function (p) {
      var boxes = p.querySelectorAll(".filter-dropdown input[type=checkbox]");
      var changed = false;
      boxes.forEach(function (b) {
        if (b.checked !== b.defaultChecked) changed = true;
      });
      var dot = p.querySelector(".status-dot");
      if (dot) {
        dot.classList.toggle("is-changed", changed);
        dot.classList.toggle("is-default", !changed);
      }
    });
  }

  function commitToolbarGroup(boxes) {
    if (!boxes.length || !window.pwFilter || !window.pwFilter.syncFromControls) return;
    var group = boxes[0].getAttribute('data-pw-filter-group');
    if (group) window.pwFilter.syncFromControls(group);
  }

  // --- Drag-to-scroll the pill row (click+drag / touch) ---
  // Open/close is deferred to pointerup so a drag does not toggle a pill.
  var drag = {
    active: false, moved: false, startX: 0, scrollLeft: 0,
    pointerId: null, pressPill: null,
  };
  var DRAG_THRESHOLD = 6; // px

  if (scroller) {
    scroller.addEventListener("pointerdown", function (e) {
      // Don't start a bar-drag from inside a dropdown panel
      if (e.target.closest && e.target.closest(".filter-dropdown")) return;
      if (e.button != null && e.button !== 0) return;
      drag.active = true;
      drag.moved = false;
      drag.startX = e.clientX;
      drag.scrollLeft = scroller.scrollLeft;
      drag.pointerId = e.pointerId;
      var el = document.elementFromPoint(e.clientX, e.clientY);
      drag.pressPill = (el && el.closest) ? el.closest(".filter-pill") : null;
      if (!drag.pressPill && e.target.closest) {
        drag.pressPill = e.target.closest(".filter-pill");
      }
    });

    scroller.addEventListener("pointermove", function (e) {
      if (!drag.active) return;
      var dx = e.clientX - drag.startX;
      if (!drag.moved && Math.abs(dx) >= DRAG_THRESHOLD) {
        drag.moved = true;
        scroller.classList.add("is-dragging");
        closeAll();
        try { scroller.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      }
      if (drag.moved) {
        scroller.scrollLeft = drag.scrollLeft - dx;
        e.preventDefault();
      }
    });

    function endDrag() {
      if (!drag.active) return;
      var wasMoved = drag.moved;
      drag.active = false;
      scroller.classList.remove("is-dragging");
      try {
        if (drag.pointerId != null) scroller.releasePointerCapture(drag.pointerId);
      } catch (err) { /* ignore */ }
      drag._justFinishedDrag = wasMoved;
    }

    scroller.addEventListener("pointerup", endDrag);
    scroller.addEventListener("pointercancel", endDrag);
  }

  // --- Open / close: pointerup so drag can cancel the open ---
  document.addEventListener("pointerup", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    if (drag.moved || drag._justFinishedDrag) {
      drag.moved = false;
      drag._justFinishedDrag = false;
      drag.pressPill = null;
      return;
    }
    var dd = t.closest(".filter-dropdown");
    if (dd) {
      var owner = dd.closest(".filter-pill");
      if (owner && owner.classList.contains("is-open")) return;
    }
    var pill = drag.pressPill;
    if (!pill) {
      pill = t.closest(".filter-pill");
    }
    drag.pressPill = null;

    if (pill && bar.contains(pill) && !(t.closest && t.closest(".filter-dropdown"))) {
      if (pill.classList.contains("is-open")) closeAll();
      else openPill(pill);
      return;
    }
    if (!t.closest(".filter-bar") && !t.closest(".filter-dropdown")) {
      closeAll();
    }
  }, true);

  // Keyboard: Enter/Space toggle; Escape closes
  bar.addEventListener("keydown", function (e) {
    var pill = e.target && e.target.closest ? e.target.closest(".filter-pill") : null;
    if (!pill || !bar.contains(pill)) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (pill.classList.contains("is-open")) closeAll();
      else openPill(pill);
    } else if (e.key === "Escape") {
      closeAll();
      pill.focus();
    }
  });

  // Flat-group toolbar (Lang, etc.): all / clear on all boxes in that dropdown
  bar.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest("[data-dd-action]") : null;
    if (!btn) return;
    if (btn.hasAttribute("data-dd-scope")) return; // handled by lens scoped handlers
    var dd = btn.closest(".filter-dropdown");
    if (!dd) return;
    if (dd.getAttribute("data-idea") === "a" || dd.getAttribute("data-idea") === "b") return;
    var boxes = dd.querySelectorAll(".dd-grid input[type=checkbox]");
    var action = btn.getAttribute("data-dd-action");
    var on = action === "all";
    boxes.forEach(function (b) { b.checked = on; });
    refreshDots();
    commitToolbarGroup(boxes);
    e.preventDefault();
  });

  pills.forEach(function (p) {
    p.querySelectorAll(".filter-dropdown input[type=checkbox]").forEach(function (cb) {
      cb.addEventListener("change", refreshDots);
    });
  });

  function repositionOpen() {
    var open = bar.querySelector(".filter-pill.is-open");
    if (open) placeDropdown(open);
  }
  window.addEventListener("resize", repositionOpen);
  window.addEventListener("scroll", repositionOpen, true);

  // --- Segmented lens (Brands Open/Closed, Nationalism US/CN) + clear ---
  function updateLensCounts(dd) {
    if (!dd) return;
    dd.querySelectorAll("[data-lens-count]").forEach(function (el) {
      var tier = el.getAttribute("data-lens-count");
      var boxes = dd.querySelectorAll('[data-tier-grid="' + tier + '"] input[type=checkbox]');
      var on = 0;
      boxes.forEach(function (b) { if (b.checked) on++; });
      el.textContent = "· " + on;
      var tab = dd.querySelector('[data-lens="' + tier + '"]');
      if (tab) tab.title = tier + " " + on + "/" + boxes.length + " selected";
    });
  }

  bar.addEventListener("click", function (e) {
    var tab = e.target.closest ? e.target.closest("[data-lens]") : null;
    if (!tab || tab.closest(".dd-segment") == null) return;
    var dd = tab.closest(".filter-dropdown");
    if (!dd || dd.getAttribute("data-idea") !== "b") return;
    var lens = tab.getAttribute("data-lens");
    dd.querySelectorAll(".dd-segment [data-lens]").forEach(function (b) {
      var on = b === tab;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    var body = dd.querySelector(".dd-lens-body");
    if (body) body.setAttribute("data-active-lens", lens);
    e.preventDefault();
    e.stopPropagation();
  });

  // Scoped all/clear: only currently visible lens tier
  bar.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest("[data-dd-action][data-dd-scope=visible]") : null;
    if (!btn) return;
    var dd = btn.closest(".filter-dropdown");
    if (!dd || dd.getAttribute("data-idea") !== "b") return;
    var body = dd.querySelector(".dd-lens-body");
    var lens = body ? body.getAttribute("data-active-lens") : null;
    if (!lens) return;
    var boxes = dd.querySelectorAll('[data-tier-grid="' + lens + '"] input[type=checkbox]');
    var action = btn.getAttribute("data-dd-action");
    var on = action === "all";
    boxes.forEach(function (b) { b.checked = on; });
    refreshDots();
    updateLensCounts(dd);
    commitToolbarGroup(boxes);
    e.preventDefault();
    e.stopPropagation();
  }, true);

  var _refreshDotsLens = refreshDots;
  refreshDots = function () {
    _refreshDotsLens();
    bar.querySelectorAll(".filter-dropdown[data-idea=b]").forEach(updateLensCounts);
  };

  document.addEventListener('pw:filter-change', refreshDots);
  refreshDots();
})();
