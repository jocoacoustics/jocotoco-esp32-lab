let state = null;
const $ = (id) => document.getElementById(id);
const safe = (v) =>
  String(v ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const bytes = (n) =>
  n == null
    ? '—'
    : n < 1024
      ? n + ' B'
      : n < 1048576
        ? (n / 1024).toFixed(1) + ' KB'
        : n < 1073741824
          ? (n / 1048576).toFixed(1) + ' MB'
          : (n / 1073741824).toFixed(2) + ' GB';
function plot(id, samples, keys, min, max, height) {
  let grid = '';
  for (let i = 0; i < 4; i++) {
    let y = 8 + (i * (height - 16)) / 3;
    grid += `<line x1="0" x2="600" y1="${y}" y2="${y}" stroke="#2a3a37" stroke-dasharray="3 6"/>`;
  }
  let paths = keys
    .map((key, k) => {
      let points = samples.map((s, i) =>
        s[key] == null
          ? null
          : [
              (i * 600) / Math.max(samples.length - 1, 1),
              height -
                8 -
                ((Math.max(min, Math.min(max, s[key])) - min) / (max - min)) * (height - 16),
            ],
      );
      let d = '',
        active = false;
      for (let p of points) {
        if (!p) {
          active = false;
          continue;
        }
        d += (active ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1);
        active = true;
      }
      return `<path d="${d}" fill="none" stroke="${k ? '#64d2be' : '#c7ef7a'}" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
    })
    .join('');
  $(id).innerHTML = grid + paths;
}
function render(s) {
  state = s;
  let stale = !s.updated || Date.now() / 1000 - s.updated > 20;
  let live = s.connected && !stale && !s.paused;
  $('connection').textContent = s.paused
    ? 'Lecture en pause'.replace('Lecture en pause', 'Lectura pausada')
    : live
      ? 'USB conectado · datos reales'
      : 'Sin lectura reciente';
  $('led').style.background = live ? '#c7ef7a' : '#d9a26d';
  $('port').textContent = (s.port || 'USB') + ' · ' + (s.connected ? 'conectado' : 'sin conexión');
  $('pause').textContent = s.paused ? 'Reanudar lectura' : 'Pausar lectura';
  $('notice').style.display = live ? 'none' : 'block';
  $('notice').textContent = s.paused
    ? 'Lectura pausada. Los valores visibles corresponden a la última muestra.'
    : s.message;
  $('rssi').textContent = s.rssi ?? '—';
  $('quality').textContent =
    s.rssi == null
      ? 'Sin señal medida'
      : s.rssi >= -60
        ? 'Señal fuerte · referencia orientativa'
        : s.rssi >= -75
          ? 'Señal intermedia · referencia orientativa'
          : 'Señal débil · referencia orientativa';
  $('down').textContent = s.down_mbps == null ? '—' : s.down_mbps.toFixed(2);
  $('totals').textContent = bytes(s.received) + ' / ' + bytes(s.sent);
  $('count').textContent = s.client_count ?? '—';
  $('route').textContent = s.uplink_ip
    ? 'Router enlazado · IP recibida. Internet no se verifica desde este panel.'
    : 'Sin IP del router · revisa el enlace doméstico.';
  $('security').textContent =
    s.web_disabled && s.remote_disabled ? 'Desactivadas' : 'Revisar estado';
  $('uptime').textContent = s.uptime?.split(' (since')[0] || '—';
  $('last').textContent = s.updated
    ? 'Última muestra · ' +
      new Date(s.updated * 1000).toLocaleTimeString('es-EC') +
      ' · sesión en memoria'
    : 'Esperando primera muestra';
  let a = s.samples || [];
  let max = Math.max(0.1, ...a.flatMap((x) => [x.down || 0, x.up || 0]));
  plot('traffic', a, ['down', 'up'], 0, max, 180);
  plot('signal', a, ['rssi'], -100, -30, 130);
  $('trafficEmpty').style.display = a.some((x) => x.down != null) ? 'none' : 'grid';
  $('signalEmpty').style.display = a.some((x) => x.rssi != null) ? 'none' : 'grid';
  $('trafficMax').textContent = 'Máximo visible: ' + max.toFixed(2) + ' Mbps';
  $('scan').disabled = s.scanning || s.paused || !s.connected;
  $('scan').textContent = s.scanning ? 'Explorando…' : '↻ Explorar';
  if (s.scan_time) {
    $('scanTime').textContent =
      'Último escaneo · ' + new Date(s.scan_time * 1000).toLocaleTimeString('es-EC');
    $('networks').innerHTML = s.networks.length
      ? s.networks
          .map(
            (n) =>
              `<tr><td>${safe(n.ssid)}</td><td>${n.channel}</td><td>${safe(n.security)}</td><td><span class="signalbar"><b style="width:${Math.max(3, Math.min(100, ((n.rssi + 100) / 70) * 100))}%"></b></span>${n.rssi} dBm</td></tr>`,
          )
          .join('')
      : '<tr><td colspan="4" class="emptyrow">Sin redes en el último escaneo.</td></tr>';
  }
  $('clientRows').innerHTML = s.clients?.length
    ? s.clients
        .map(
          (c) =>
            `<tr><td>${safe(c.name)}<br><span class="foot">${safe(c.id)}</span></td><td>${safe(c.ip)}</td></tr>`,
        )
        .join('')
    : `<tr><td colspan="2" class="emptyrow">${s.connected ? 'Sin clientes en la última lectura.' : 'Esperando conexión USB.'}</td></tr>`;
}
async function update() {
  try {
    let r = await fetch('/api/state');
    if (!r.ok) throw Error();
    render(await r.json());
  } catch (e) {
    $('connection').textContent = 'Servidor local desconectado';
    $('led').style.background = '#d9a26d';
    $('notice').style.display = 'block';
    $('notice').textContent = 'El servidor no responde. Los valores conservados son históricos.';
  }
  setTimeout(update, 2000);
}
$('scan').onclick = () => fetch('/api/scan', { method: 'POST' });
$('pause').onclick = () => fetch('/api/pause', { method: 'POST' }).then(() => {});
$('export').onclick = () => {
  if (!state) return;
  let data = { ...state, exported_at: new Date().toISOString() };
  let url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
  );
  let a = document.createElement('a');
  a.href = url;
  a.download = 'jocotoco-lab-sesion.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
document.querySelectorAll('nav a').forEach(
  (a) =>
    (a.onclick = () => {
      document.querySelectorAll('nav a').forEach((n) => n.classList.remove('active'));
      a.classList.add('active');
    }),
);
update();
