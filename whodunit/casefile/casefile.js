// The case file's two controls: the paper colour, and the replay of the investigation.
// Everything on the page reads without this script. It only adds the toggle and the playback.
(function () {
  var root = document.documentElement;
  var toggle = document.querySelector('[data-theme-toggle]');
  function paint(dark) {
    if (dark) { root.setAttribute('data-theme', 'dark'); } else { root.removeAttribute('data-theme'); }
    if (toggle) { toggle.textContent = dark ? 'Light' : 'Dark'; toggle.setAttribute('aria-pressed', dark ? 'true' : 'false'); }
  }
  var chosen = null;
  try { chosen = window.localStorage.getItem('whodunit-paper'); } catch (e) { /* no storage, no memory */ }
  paint(chosen === 'dark');  // light unless someone chose dark, whatever the system prefers
  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener('click', function () {
      var dark = root.getAttribute('data-theme') !== 'dark';
      paint(dark);
      try { window.localStorage.setItem('whodunit-paper', dark ? 'dark' : 'light'); } catch (e) { /* fine */ }
    });
  }

  var svg = document.querySelector('svg.lineup');
  // On a narrow screen the lineup scrolls sideways. Start it where the culprit is.
  var ringed = svg && svg.querySelector('.col.culprit .hit');
  var frame = document.querySelector('.scroll');
  if (ringed && frame && frame.scrollWidth > frame.clientWidth) {
    frame.scrollLeft = Math.max(0, parseFloat(ringed.getAttribute('x')) - frame.clientWidth / 2);
  }
  var data = document.getElementById('lineup-data');
  var button = document.querySelector('[data-play]');
  var caption = document.querySelector('.caption');
  if (!svg || !data || !button) { return; }
  var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) { return; }  // the page stays as it was drawn
  var play = JSON.parse(data.textContent);
  var NS = 'http://www.w3.org/2000/svg';
  var cols = Array.prototype.slice.call(svg.querySelectorAll('.col'));
  var finalMarks = cols.map(function (col) { return col.querySelector('.marks').innerHTML; });
  var finalPct = cols.map(function (col) { var t = col.querySelector('.pct'); return t ? t.textContent : ''; });
  var finalClass = cols.map(function (col) { return col.getAttribute('class'); });
  var finalCaption = caption ? caption.textContent : '';
  var timer = null, at = 0, sub = 0, state = null;
  button.hidden = false;

  // The same rule the page was drawn with: one typed mark a line, or glyph and count when there are too many.
  function lines(ordinary, replays) {
    var all = ordinary.map(function (m) { return [m, 'ord ' + (m === 'x' ? 'fail' : 'pass')]; })
      .concat(replays.map(function (m) { return [m, m === 'x' ? 'fail' : m === 'o' ? 'pass' : 'skip']; }));
    if (all.length <= play.cap) { return all; }
    var out = [];
    [['x', 'ord fail', ordinary], ['o', 'ord pass', ordinary], ['x', 'fail', replays], ['o', 'pass', replays], ['-', 'skip', replays]].forEach(function (group) {
      var count = group[2].filter(function (m) { return m === group[0]; }).length;
      if (count) { out.push([group[0], group[1]]); out.push([String(count), group[1] + ' count']); }
    });
    return out;
  }
  function drawMarks(i) {
    var holder = cols[i].querySelector('.marks');
    while (holder.firstChild) { holder.removeChild(holder.firstChild); }
    lines(state.ordinary[i], state.replays[i]).forEach(function (line, n) {
      var text = document.createElementNS(NS, 'text');
      text.setAttribute('class', 'mark ' + line[1]);
      text.setAttribute('x', play.x[i]);
      text.setAttribute('y', play.marksTop + n * play.lineHeight);
      text.textContent = line[0];
      holder.appendChild(text);
    });
  }
  function drawOdds(odds) {
    cols.forEach(function (col, i) {
      if (i === 0) { return; }
      var p = odds ? (odds[i - 1] || 0) : null;
      var label = col.querySelector('.pct');
      if (label) { label.textContent = p !== null && p >= 0.05 ? Math.round(p * 100) + '%' : ''; }
      var base = finalClass[i].replace(/\s*\b(cleared|culprit)\b/g, '');
      col.setAttribute('class', base + (p !== null && p < 0.01 ? ' cleared' : ''));
    });
  }
  function reset() {
    state = { ordinary: play.ordinary.map(function (list) { return list.slice(); }), replays: cols.map(function () { return []; }) };
    at = 0; sub = 0;
    svg.classList.remove('reveal'); svg.classList.add('playing');
    cols.forEach(function (col, i) { drawMarks(i); });
    drawOdds(null);
    if (caption) { caption.textContent = play.before; }
  }
  function finish() {
    clearInterval(timer); timer = null;
    cols.forEach(function (col, i) { col.querySelector('.marks').innerHTML = finalMarks[i]; col.setAttribute('class', finalClass[i]); var t = col.querySelector('.pct'); if (t) { t.textContent = finalPct[i]; } });
    svg.classList.remove('playing'); svg.classList.add('reveal');
    if (caption) { caption.textContent = finalCaption; }
    button.textContent = 'Replay again'; button.setAttribute('aria-pressed', 'false');
    state = null;
  }
  function tick() {
    if (at >= play.rounds.length) { finish(); return; }
    var round = play.rounds[at];
    if (sub < round.c.length) {
      state.replays[round.c[sub]].push(round.v[sub]);
      drawMarks(round.c[sub]);
      sub += 1;
      if (caption) { caption.textContent = 'Round ' + (at + 1) + ' of ' + play.rounds.length + '. ' + round.say + ' ' + round.v.slice(0, sub).join(' '); }
      return;
    }
    drawOdds(round.p);
    if (caption) { caption.textContent = 'Round ' + (at + 1) + ' of ' + play.rounds.length + '. ' + round.say + ' ' + round.v.join(' ') + '. ' + round.lead; }
    at += 1; sub = 0;
  }
  button.addEventListener('click', function () {
    if (timer) { clearInterval(timer); timer = null; button.textContent = 'Carry on'; button.setAttribute('aria-pressed', 'false'); return; }
    if (!state) { reset(); }
    button.textContent = 'Pause'; button.setAttribute('aria-pressed', 'true');
    timer = setInterval(tick, play.pace);
  });
})();
