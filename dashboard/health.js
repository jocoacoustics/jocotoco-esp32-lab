// v0.6.0 — readings are unknown until the telemetry firmware is installed.
let hw = document.createElement('section');
hw.className = 'card';
hw.id = 'hardware';
hw.style.marginTop = '16px';
hw.innerHTML = `<div class="cardhead"><h2>Salud del ESP32</h2><span class="pill" id="hardwareFresh">Esperando firmware de telemetría</span></div><div class="metrics" style="margin-top:16px"><div class="card metric"><div class="label">CPU · promedio de dos núcleos</div><div class="value"><span id="cpuUsed">—</span> <small>%</small></div><div class="foot" id="cpuCores">Pendiente de lectura real</div></div><div class="card metric"><div class="label">RAM · heap libre</div><div class="value"><span id="heapFree">—</span> <small>KiB</small></div><div class="foot" id="heapUsed">Heap interno usado: sin medir</div></div><div class="card metric"><div class="label">Flash usada · aplicación activa</div><div class="value"><span id="flashUsed">—</span> <small>MiB</small></div><div class="foot" id="flashSlot">Capacidad física: 4 MiB. Tamaño activo pendiente.</div></div><div class="card metric"><div class="label">Voltaje / temperatura</div><div class="value">—</div><div class="foot">Sin medición física. No se infieren del cargador.</div></div></div><div class="grid"><div><h2>CPU por núcleo · %</h2><div class="chart"><svg id="cpuHistory" viewBox="0 0 600 180"></svg></div><p class="history-note">Verde: núcleo 0; turquesa: núcleo 1. Tiempo no inactivo en ventanas de 2 s, incluido Wi-Fi y sistema.</p></div><div><h2>Heap interno usado · %</h2><div class="chart"><svg id="heapHistory" viewBox="0 0 600 180"></svg></div><p class="history-note">Porcentaje del heap interno disponible para asignaciones, no de toda la SRAM física.</p></div></div><div class="kv"><span>RAM mínima libre desde el arranque</span><b id="heapMinimum">—</b></div><div class="kv"><span>Mayor bloque libre contiguo</span><b id="heapLargest">—</b></div><div class="kv"><span>NVS · entradas usadas / totales</span><b id="nvsUsed">—</b></div><div class="kv"><span>Archivos · espacio usado / total</span><b id="fsUsed">—</b></div><div class="kv"><span>Firmware / tareas / frecuencia</span><b id="deviceBuild">—</b></div><p class="history-note">La flash se desglosa: aplicación activa frente al slot OTA, entradas NVS y uso del volumen de archivos. El segundo slot OTA es espacio reservado; no es RAM ni espacio libre para archivos.</p><div class="kv"><span>Comprobación OTA autenticada</span><b id="otaCheck">Sin comprobar</b></div>`;
$('overview').after(hw);
const kib = (n) => (n / 1024).toFixed(1) + ' KiB',
  mib = (n) => (n / 1048576).toFixed(2) + ' MiB';
function healthCharts() {
  let a = historyData?.device_metrics || [];
  drawAxis(
    'cpuHistory',
    [
      { color: colors[0], points: a.map((p) => ({ t: p.t_ms / 1000, v: p.core0 })) },
      { color: colors[1], points: a.map((p) => ({ t: p.t_ms / 1000, v: p.core1 })) },
    ],
    0,
    100,
    '%',
    180,
  );
  drawAxis(
    'heapHistory',
    [
      {
        color: colors[0],
        points: a.map((p) => ({
          t: p.t_ms / 1000,
          v: p.heap_total ? (100 * p.heap_used) / p.heap_total : null,
        })),
      },
    ],
    0,
    100,
    '%',
    180,
  );
}
async function healthUpdate() {
  try {
    let r = await fetch('/api/hardware');
    let h = await r.json(),
      m = h.metrics,
      p = h.preflight;
    $('otaCheck').textContent = p?.runtime_version_verified
      ? 'Actualización y arranque verificados'
      : p?.state === 'preflight_ok'
        ? (p.device?.Version || 'Versión leída') + ' · ' + clock(p.checked_at)
        : 'Sin comprobación reciente';
    if (m) {
      let c = m.cpu,
        r = m.heap,
        f = m.flash;
      $('hardwareFresh').textContent =
        (Date.now() / 1000 - h.metrics_updated > 15 ? 'Histórico · ' : 'Medido · ') +
        clock(h.metrics_updated);
      $('cpuUsed').textContent = c.valid ? c.used_percent.toFixed(1) : '—';
      $('cpuCores').textContent = c.valid
        ? 'Núcleo 0: ' +
          c.core0_percent.toFixed(1) +
          ' % · Núcleo 1: ' +
          c.core1_percent.toFixed(1) +
          ' %'
        : 'Esperando primera ventana';
      $('heapFree').textContent = (r.free_bytes / 1024).toFixed(1);
      $('heapUsed').textContent =
        'Usado: ' +
        kib(r.used_bytes) +
        ' / ' +
        kib(r.total_bytes) +
        ' · ' +
        r.used_percent.toFixed(1) +
        ' %';
      $('heapMinimum').textContent = kib(r.minimum_free_bytes);
      $('heapLargest').textContent = kib(r.largest_free_block_bytes);
      $('flashUsed').textContent = f.active_image_bytes
        ? (f.active_image_bytes / 1048576).toFixed(2)
        : '—';
      $('flashSlot').textContent = f.active_image_bytes
        ? 'Slot ' +
          f.active_partition +
          ': ' +
          f.active_slot_used_percent.toFixed(1) +
          ' % de ' +
          mib(f.active_slot_bytes)
        : 'Sin tamaño activo';
      $('nvsUsed').textContent = m.nvs
        ? m.nvs.used_entries + ' / ' + m.nvs.total_entries + ' entradas'
        : 'Sin lectura';
      $('fsUsed').textContent = m.filesystem
        ? kib(m.filesystem.used_bytes) + ' / ' + kib(m.filesystem.total_bytes)
        : 'Volumen no disponible';
      $('deviceBuild').textContent =
        m.firmware_version + ' · ' + m.task_count + ' tareas · ' + m.cpu_frequency_mhz + ' MHz';
    }
    healthCharts();
  } catch (e) {
    $('hardwareFresh').textContent = 'Sin respuesta del servidor local';
  }
}
healthUpdate();
setInterval(healthUpdate, 4000);
