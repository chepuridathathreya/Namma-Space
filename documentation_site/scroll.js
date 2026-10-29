if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

if (location.hash) history.replaceState(null, '', location.pathname + location.search);
window.scrollTo(0, 0);
window.addEventListener('pageshow', function (e) { if (e.persisted) window.scrollTo(0, 0); });

var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function easeInOut(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

function glideTo(targetY) {
  var startY = window.scrollY;
  var distance = targetY - startY;
  var duration = Math.min(2200, Math.max(900, Math.abs(distance) * 0.6));
  var startTime = null;
  function step(now) {
    if (startTime === null) startTime = now;
    var t = Math.min(1, (now - startTime) / duration);
    window.scrollTo(0, startY + distance * easeInOut(t));
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

document.addEventListener('click', function (e) {
  var link = e.target.closest('a[href^="#"]');
  if (!link) return;
  var target = document.getElementById(link.getAttribute('href').slice(1));
  if (!target) return;
  e.preventDefault();
  var y = target.getBoundingClientRect().top + window.scrollY - 12;
  if (reduceMotion) window.scrollTo(0, y); else glideTo(y);
});
