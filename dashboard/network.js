// v0.4.0 — PC stays on domestic Wi-Fi; ESP32 uses only charger after verification.
let linkbox = document.createElement('div');
linkbox.className = 'card';
linkbox.style.margin = '16px 0';
linkbox.innerHTML = `<div class="cardhead"><h2>Conexión inalámbrica con la estación</h2><span class="pill" id="transportBadge">Comprobando</span></div><div class="timeline-tools"><label>IP del ESP32 en tu router <input id="espHost" placeholder="192.168.1.50" aria-label="IP doméstica del ESP32" style="width:160px"></label><button id="connectNetwork">Usar Wi-Fi / HTTP</button><a id="adminLink" target="_blank" rel="noopener" style="display:none">Abrir control del ESP32 ↗</a></div><p id="networkHelp" style="font-size:12px;margin-bottom:0">El panel y SQLite siguen en este PC. El ESP32 puede estar en un cargador de 5 V, dentro del alcance del router.</p><p class="history-note">HTTP sin cifrado, solo red local. Los cambios administrativos requieren la contraseña que configuraste. El firmware publica estado básico y escaneos sin login; el recolector no necesita ni guarda tu contraseña.</p></div>`;
$('overview').prepend(linkbox);
const beforeNetworkRender = render;
render = function (s) {
  beforeNetworkRender(s);
  let http = s.transport === 'http';
  $('transportBadge').textContent = http ? 'Wi-Fi → HTTP' : 'USB';
  if (document.activeElement !== $('espHost'))
    $('espHost').value = s.http_host || s.uplink_ip || '';
  if (s.http_host) {
    $('adminLink').href = 'http://' + s.http_host;
    $('adminLink').style.display = 'inline';
  }
  if (http) {
    $('connection').textContent = s.paused
      ? 'Lectura pausada'
      : s.connected
        ? 'Wi-Fi conectado · datos reales'
        : 'Sin respuesta HTTP';
    $('port').textContent = 'HTTP · ' + s.http_host;
    $('security').textContent = 'Web: AP + red doméstica';
    $('networkHelp').textContent = s.connected
      ? 'Lectura por HTTP confirmada. Puedes retirar el USB de datos y alimentar el ESP32 con un cargador micro-USB de 5 V. El PC sigue conectado a tu red doméstica.'
      : 'Esperando respuesta del ESP32. Revisa alimentación, alcance y dirección IP. Si DHCP cambia su IP, actualízala aquí.';
    document.querySelector('.metric:nth-child(2) .foot').textContent =
      'Aproximado · contadores HTTP redondeados';
    document.querySelector('.metric:nth-child(3) .foot').textContent =
      'Aproximado · desde el último reinicio del ESP32';
    if (s.client_count > 0 && !s.clients?.length)
      $('clientRows').innerHTML =
        `<tr><td colspan="2" class="emptyrow">${s.client_count} cliente(s). El estado HTTP básico no expone su detalle; no se inventan IP ni nombres.</td></tr>`;
  }
  document.querySelector('.statusbar span:last-child').textContent =
    'LOCAL · SQLite persistente · ' + (http ? 'HTTP sin USB' : 'USB') + ' · v0.4.0';
  $('last').textContent = s.updated
    ? 'Última muestra · ' + clock(s.updated) + ' · historial SQLite'
    : 'Esperando primera muestra';
  document.querySelector('#spectrum .cardhead p').textContent =
    'Escaneo configurable; puede interrumpir brevemente el tráfico.';
  $('scanTime').textContent = s.scan_time
    ? 'Último escaneo · ' + clock(s.scan_time) + (http ? ' · adquisición asíncrona HTTP' : '')
    : 'Esperando primer escaneo';
};
$('connectNetwork').onclick = async () => {
  let host = $('espHost').value.trim();
  let r = await fetch('/api/network', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host }),
  });
  if (!r.ok)
    $('networkHelp').textContent =
      'Ingresa una dirección IPv4 privada válida del ESP32, sin http:// ni puerto.';
  else $('networkHelp').textContent = 'Comprobando la dirección por HTTP…';
};
if (state) render(state);
