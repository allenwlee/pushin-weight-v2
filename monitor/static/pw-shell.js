// Left navigation rail for the homepage and /dashboard/each: expands on
// desktop and opens as a drawer at phone widths.
(function () {
  'use strict';

  var MOBILE = '(max-width: 700px)';

  function start() {
    var body = document.body;
    var rail = document.getElementById('pw-rail');
    if (!rail) return;
    var railToggle = rail.querySelector('[data-pw-rail-toggle]');
    var mobileToggle = document.querySelector('[data-pw-rail-open]');
    var backdrop = document.querySelector('[data-pw-rail-close]');

    function isMobile() { return window.matchMedia(MOBILE).matches; }
    function state() { return body.getAttribute('data-pw-nav') || ''; }

    function setNav(next) {
      var wasDrawer = state() === 'mobile-open';
      if (next) body.setAttribute('data-pw-nav', next);
      else body.removeAttribute('data-pw-nav');
      var open = next === 'expanded' || next === 'mobile-open';
      if (railToggle) railToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (mobileToggle) mobileToggle.setAttribute('aria-expanded', next === 'mobile-open' ? 'true' : 'false');
      if (backdrop) backdrop.hidden = next !== 'mobile-open';
      if (next === 'mobile-open') {
        var first = rail.querySelector('nav a');
        if (first) first.focus();
      } else if (wasDrawer && mobileToggle) {
        mobileToggle.focus();
      }
    }

    if (railToggle) {
      railToggle.addEventListener('click', function () {
        if (isMobile()) setNav(state() === 'mobile-open' ? '' : 'mobile-open');
        else setNav(state() === 'expanded' ? '' : 'expanded');
      });
    }
    if (mobileToggle) mobileToggle.addEventListener('click', function () { setNav('mobile-open'); });
    if (backdrop) backdrop.addEventListener('click', function () { setNav(''); });
    rail.addEventListener('click', function (event) {
      if (event.target.closest('nav a') && state() === 'mobile-open') setNav('');
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && state()) setNav('');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
