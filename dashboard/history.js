// v0.3.0 — SQLite history, synchronized axes, per-network received power.
let historyData = null,
  selected = new Set(),
  selectionInitialized = false,
  rangeMinutes = 60;
const colors = [
  '#c7ef7a',
  '#64d2be',
  '#f7bb75',
  '#ae9aee',
  '#ef92ad',
  '#75b8ef',
  '#eddf89',
  '#b5d0bf',
  '#ef8976',
  '#91b7a4',
  '#e5b9ed',
  '#d2c6a9',
];
const clock = (t) =>
  new Intl.DateTimeFormat('es-EC', {
    timeZone: 'America/Guayaquil',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(t * 1000));
const historyCSS = document.createElement('style');
historyCSS.textContent = `select,input{background:#172824;border:1px solid #3c5147;color:#edf2e7;border-radius:6px;padding:8px;font:inherit}input[type=checkbox]{accent-color:#c7ef7a}.timeline-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0}.history-chart{height:300px;margin:15px 0}.history-chart svg{width:100%;height:100%;overflow:visible}.hist-table{max-height:390px;overflow:auto}.hist-table th{position:sticky;top:0;background:#142020}.network-name{max-width:230px;overflow-wrap:anywhere}.change{color:#c7ef7a}.history-stats{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;color:#98aaa3}.history-note{font-size:11px;color:#98aaa3}.history-legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;margin:10px 0}.history-legend span{border-left:3px solid;padding-left:6px}.chart{height:220px!important}.axis{display:none}#networks input{padding:0}.timeline-head{display:flex;justify-content:space-between;gap:15px;align-items:center;flex-wrap:wrap}.eventlist{font-size:12px;line-height:1.9;color:#98aaa3}@media(max-width:650px){.history-chart{height:260px}.hist-table{overflow-x:auto}.hist-table table{min-width:650px}.cardhead{flex-wrap:wrap}.cardhead h2{line-height:1.5}}`;
document.head.append(historyCSS);
document.querySelector('h1').textContent = 'El entorno cambia. Regístralo.';
document.querySelector('.intro p').textContent =
  'Observación Wi-Fi con historial local, series temporales y reloj compartido.';
document.querySelector('.statusbar span:last-child').textContent =
  'LOCAL · SQLite · Sin contraseñas · v0.3.0';
let section = document.createElement('section');
section.className = 'card';
section.id = 'timeline';
section.style.marginTop = '16px';
section.innerHTML = `<div class="timeline-head"><div><span class="eyebrow accent">Observatorio Wi-Fi</span><h2 style="margin-top:6px">Cada red, su propia curva</h2></div><span class="pill">RSSI · dBm · hora de Ecuador</span></div><div class="timeline-tools"><label>Período <select id="range"><option value="5">5 minutos</option><option value="15">15 minutos</option><option value="60" selected>1 hora</option><option value="360">6 horas</option><option value="1440">24 horas</option></select></label><label>Escanear cada <select id="interval"><option value="0">Solo manual</option><option value="30">30 segundos</option><option value="60" selected>60 segundos</option><option value="120">2 minutos</option><option value="300">5 minutos</option></select></label><button id="allNetworks">Ver todas</button><button id="noNetworks">Ocultar todas</button></div><div class="history-stats" id="historyStats">Abriendo historial SQLite…</div><div class="history-chart"><svg id="networkChart" viewBox="0 0 900 280" role="img" aria-label="Potencia recibida de redes Wi-Fi a lo largo del tiempo"></svg></div><div class="history-legend" id="networkLegend"></div><div class="history-note">Reloj del PC, resolución de milisegundos; etiquetas hasta el segundo. NTP no verificado. Cada escaneo tiene inicio y fin; las redes se observan secuencialmente. No es una captura simultánea del espacio.</div><div class="timeline-tools"><input id="networkFilter" placeholder="Filtrar por nombre de red" aria-label="Filtrar redes"><span class="dim" style="font-size:11px">Selecciona las curvas en la tabla. Δ = cambio frente a la observación anterior, en dB.</span></div><div class="hist-table"><table><thead><tr><th>Ver / red</th><th>Canal</th><th>Última</th><th>Δ dB</th><th>Mín / máx</th><th>Lecturas</th><th>Última vez</th></tr></thead><tbody id="historyRows"></tbody></table></div><p class="history-note">Identidad aproximada: SSID + canal + seguridad. Este firmware no expone BSSID en la consola; nombres repetidos pueden agrupar antenas distintas. Se conservan todas las observaciones originales en SQLite; la curva usa la señal más fuerte del grupo por escaneo. Red ausente = hueco, nunca 0 dBm.</p><div class="cardhead" style="margin-top:20px"><h2>Registro de la sesión</h2><button id="mark">＋ Anotar cambio físico</button></div><div id="events" class="eventlist">Aún sin eventos.</div>`;
document.querySelector('#overview').after(section);
let navlink = document.createElement('a');
navlink.href = '#timeline';
navlink.textContent = '⌁   Línea temporal';
document.querySelector('nav').append(navlink);

function drawAxis(id, series, min, max, unit, h = 180) {
  let svg = $(id),
    w = Math.max(280, Math.round(svg.clientWidth || 600));
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
  const left = 53,
    right = 14,
    top = 12,
    bottom = 31,
    pw = w - left - right,
    ph = h - top - bottom;
  let all = series.flatMap((s) => s.points).filter((p) => p.t != null);
  let start = all.length ? Math.min(...all.map((p) => p.t)) : Date.now() / 1000 - rangeMinutes * 60;
  let end = all.length ? Math.max(...all.map((p) => p.t)) : Date.now() / 1000;
  if (historyData) {
    let times = [
      ...historyData.samples.map((p) => p.t),
      ...historyData.scans.map((p) => p.t_ms / 1000),
    ];
    if (times.length) {
      start = Math.min(...times);
      end = Math.max(...times);
    }
  }
  if (end - start < 1) {
    start -= 1;
    end += 1;
  }
  const x = (t) => left + ((t - start) / (end - start)) * pw;
  const y = (v) => top + ((max - v) / (max - min)) * ph;
  let markup = '';
  for (let i = 0; i < 5; i++) {
    let val = min + ((max - min) * i) / 4,
      yy = y(val);
    markup += `<line x1="${left}" x2="${w - right}" y1="${yy}" y2="${yy}" stroke="#2a3a37" stroke-dasharray="3 5"/><text x="${left - 8}" y="${yy + 3}" text-anchor="end" fill="#a6b7af" font-size="11">${unit === 'dBm' ? val.toFixed(0) : val.toFixed(max < 1 ? 3 : 2)}</text>`;
  }
  for (let i = 0; i < 5; i++) {
    let t = start + ((end - start) * i) / 4;
    markup += `<text x="${x(t)}" y="${h - 9}" text-anchor="${i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}" fill="#a6b7af" font-size="11">${clock(t)}</text>`;
  }
  markup += `<text x="${left}" y="9" fill="#a6b7af" font-size="11">${unit}</text>`;
  for (let s of series) {
    let d = '',
      active = false,
      prev = null;
    for (let p of s.points) {
      if (p.v == null || p.v < min || p.v > max) {
        active = false;
        continue;
      }
      if (
        prev &&
        p.t - prev > Math.max(20, (state?.scan_interval || 60) * 2) &&
        id !== 'networkChart'
      )
        active = false;
      d += (active ? 'L' : 'M') + x(p.t).toFixed(1) + ',' + y(p.v).toFixed(1);
      active = true;
      prev = p.t;
    }
    markup += `<path d="${d}" stroke="${s.color}" fill="none" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
    if (id === 'networkChart')
      for (let p of s.points) {
        if (p.v == null) continue;
        markup += `<circle cx="${x(p.t)}" cy="${y(p.v)}" r="3" fill="${s.color}"><title>${safe(s.name)} · ${clock(p.t)} · ${p.v} dBm</title></circle>`;
      }
  }
  if (!all.some((p) => p.v != null))
    markup += `<text x="${left + pw / 2}" y="${h / 2}" text-anchor="middle" fill="#98aaa3" font-size="12">Esperando observaciones reales</text>`;
  svg.innerHTML = markup;
}
// Replace initial minimal plots with real labeled X/Y axes and persisted history.
plot = function (id, samples, keys, min, max, height) {
  let a = historyData?.samples || samples;
  if (id === 'signal') max = -20;
  drawAxis(
    id,
    keys.map((key, i) => ({ color: colors[i], points: a.map((p) => ({ t: p.t, v: p[key] })) })),
    min,
    max,
    id === 'signal' ? 'dBm' : 'Mbps',
    height,
  );
};
const originalRender = render;
render = function (s) {
  originalRender(s);
  $('interval').value = s.scan_interval ?? 60;
  $('security').textContent = s.remote_disabled
    ? s.web_disabled
      ? 'Desactivadas'
      : s.web_ap_only
        ? 'Web: solo AP · TCP: apagada'
        : 'Revisar interfaz web'
    : 'Revisar estado';
  document.querySelector('.statusbar span:last-child').textContent =
    'LOCAL · SQLite persistente · v0.3.0';
};
function renderHistory() {
  let h = historyData;
  if (!h) return;
  let nets = h.networks;
  if (!selectionInitialized && nets.length) {
    nets.slice(0, 8).forEach((n) => selected.add(n.key));
    selectionInitialized = true;
  }
  let scans = h.scans.map((s) => ({ id: s.id, t: s.t_ms / 1000 }));
  let visible = nets.filter((n) => selected.has(n.key));
  let lines = visible.map((n) => {
    let found = new Map(n.points.map((p) => [p.scan_id, p.rssi]));
    return {
      name: n.ssid,
      color: colors[nets.indexOf(n) % colors.length],
      points: scans.map((s) => ({ t: s.t, v: found.has(s.id) ? found.get(s.id) : null })),
    };
  });
  drawAxis('networkChart', lines, -100, -20, 'dBm', 280);
  $('networkLegend').innerHTML = visible
    .map(
      (n) =>
        `<span style="border-color:${colors[nets.indexOf(n) % colors.length]}">${safe(n.ssid)} · ch ${n.channel}</span>`,
    )
    .join('');
  $('historyStats').textContent =
    `${h.total_samples.toLocaleString()} muestras guardadas · ${h.total_scans.toLocaleString()} escaneos · ${nets.length} grupos en el período · SQLite ${(h.database_bytes / 1024).toFixed(0)} KB${h.truncated ? ' · Vista limitada a los últimos 2000 puntos; exportación completa disponible' : ''}`;
  let filter = $('networkFilter').value.toLowerCase();
  $('historyRows').innerHTML =
    nets
      .filter((n) => n.ssid.toLowerCase().includes(filter))
      .map(
        (n) =>
          `<tr><td class="network-name"><label><input type="checkbox" data-key="${safe(n.key)}" ${selected.has(n.key) ? 'checked' : ''}> <span style="color:${colors[nets.indexOf(n) % colors.length]}">${safe(n.ssid)}</span></label></td><td>${n.channel}</td><td>${n.last} dBm</td><td>${n.delta == null ? '—' : (n.delta > 0 ? '+' : '') + n.delta}</td><td>${n.minimum} / ${n.maximum}</td><td>${n.count}</td><td>${clock(n.points.at(-1).t)}</td></tr>`,
      )
      .join('') ||
    '<tr><td colspan="7" class="emptyrow">Sin observaciones en este período.</td></tr>';
  $('historyRows')
    .querySelectorAll('input')
    .forEach(
      (el) =>
        (el.onchange = () => {
          el.checked ? selected.add(el.dataset.key) : selected.delete(el.dataset.key);
          renderHistory();
        }),
    );
  $('events').innerHTML =
    h.events
      .map((e) => `<div>${clock(e.t_ms / 1000)} · ${safe(e.kind)} · ${safe(e.detail)}</div>`)
      .join('') || 'Aún sin eventos registrados.';
  if (state) render(state);
}
async function refreshHistory() {
  try {
    let r = await fetch('/api/history?minutes=' + rangeMinutes);
    if (r.ok) {
      historyData = await r.json();
      renderHistory();
    }
  } catch (e) {}
}
$('range').onchange = () => {
  rangeMinutes = Number($('range').value);
  refreshHistory();
};
$('interval').onchange = () =>
  fetch('/api/interval', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seconds: Number($('interval').value) }),
  });
$('allNetworks').onclick = () => {
  historyData?.networks.forEach((n) => selected.add(n.key));
  renderHistory();
};
$('noNetworks').onclick = () => {
  selected.clear();
  renderHistory();
};
$('networkFilter').oninput = renderHistory;
$('mark').onclick = async () => {
  let detail = prompt(
    'Describe un cambio observado: por ejemplo, moví el ESP32 o cerré una puerta. No ingreses contraseñas.',
  );
  if (detail?.trim()) {
    await fetch('/api/mark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: detail.slice(0, 200) }),
    });
    refreshHistory();
  }
};
$('export').textContent = '↓ Exportar historial';
$('export').onclick = async () => {
  let r = await fetch('/api/export');
  if (!r.ok) return;
  let url = URL.createObjectURL(await r.blob());
  let a = document.createElement('a');
  a.href = url;
  a.download = 'jocotoco-historial-' + new Date().toISOString().slice(0, 10) + '.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
refreshHistory();
setInterval(refreshHistory, 5000);
