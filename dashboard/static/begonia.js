/**
 * Begonia Dashboard — widget layer for the overview page.
 *
 * Live metrics (zram, pressure, platform, vivi) arrive through the existing
 * SSE stream via the window.BegoniaLive hook that live.js calls from
 * handleMessage(). The slower REST endpoints (/api/system/health and
 * /api/system/vivi) are polled on a 15s timer: health has to observe several
 * subsystems at once and does not benefit from a 1s cadence.
 *
 * Nothing here is required for the page to work: if the fetch fails the
 * panels stay in their placeholder state.
 */
(function () {
    'use strict';

    var HIDDEN_METRICS = {
        zram: true,
        pressure: true,
        platform: true,
        vivi: true
    };

    var POLL_MS = 15000;
    var pollTimer = null;

    /* ---------- formatting helpers ---------- */

    function el(id) {
        return document.getElementById(id);
    }

    function setText(id, text) {
        var node = el(id);
        if (node) node.textContent = text;
    }

    function fmtBytes(bytes) {
        if (bytes === null || bytes === undefined) return '—';
        var n = Number(bytes);
        if (!isFinite(n) || n < 0) return '—';
        var units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
        var i = 0;
        while (n >= 1024 && i < units.length - 1) {
            n /= 1024;
            i += 1;
        }
        return (i === 0 ? n.toFixed(0) : n.toFixed(n < 10 ? 2 : 1)) + ' ' + units[i];
    }

    function fmtPct(value, digits) {
        if (value === null || value === undefined) return '—';
        var n = Number(value);
        if (!isFinite(n)) return '—';
        return n.toFixed(digits === undefined ? 1 : digits) + '%';
    }

    function fmtRatio(value) {
        if (value === null || value === undefined) return '—';
        var n = Number(value);
        if (!isFinite(n)) return '—';
        return n.toFixed(2) + '\u00d7';
    }

    function fmtAvg(avg) {
        if (!avg) return '—';
        return fmtPct(avg.avg10, 2) + ' / ' + fmtPct(avg.avg60, 2) + ' / ' + fmtPct(avg.avg300, 2);
    }

    function bar(elId, percent, level) {
        var node = el(elId);
        if (!node) return;
        var p = Math.max(0, Math.min(100, Number(percent) || 0));
        var fill = node.querySelector('span') || node.firstElementChild;
        if (fill) fill.style.width = p + '%';
        node.classList.remove('is-warn', 'is-bad');
        if (level === 'bad') node.classList.add('is-bad');
        else if (level === 'warn') node.classList.add('is-warn');
    }

    function setLevel(id, level) {
        var node = el(id);
        if (!node) return;
        node.classList.remove('is-good', 'is-warn', 'is-bad');
        if (level) node.classList.add('is-' + level);
    }

    /* ---------- health ---------- */

    function renderHealth(data) {
        if (!data) return;
        var status = data.status || 'green';
        var verdict = el('begonia-health');
        if (verdict) {
            verdict.classList.remove('is-green', 'is-yellow', 'is-red');
            verdict.classList.add('is-' + status);
        }
        var labels = { green: 'HEALTHY', yellow: 'DEGRADED', red: 'CRITICAL' };
        setText('begonia-health-label', labels[status] || String(status).toUpperCase());

        var host = el('begonia-health-checks');
        if (!host) return;
        var checks = data.checks || [];
        host.innerHTML = '';
        checks.forEach(function (check) {
            var span = document.createElement('span');
            span.className = 'health-check level-' + (check.level || 'ok');
            span.title = check.detail || '';
            var dot = document.createElement('span');
            dot.className = 'dot';
            var label = document.createElement('span');
            label.textContent = check.label + (check.detail ? ': ' + check.detail : '');
            span.appendChild(dot);
            span.appendChild(label);
            host.appendChild(span);
        });
    }

    /* ---------- zram ---------- */

    function renderZram(data) {
        if (!data) return;
        if (!data.available) {
            setText('begonia-zram-devices', 'zram not in use');
            return;
        }
        setText('begonia-zram-devices', data.device_count + ' device' + (data.device_count === 1 ? '' : 's'));
        setText('begonia-zram-ratio', fmtRatio(data.ratio));
        setText('begonia-zram-original', fmtBytes(data.orig_bytes));
        setText('begonia-zram-compressed', fmtBytes(data.compr_bytes));
        setText('begonia-zram-memused', fmtBytes(data.mem_used_bytes));

        var swap = data.swap || {};
        if (swap.total_bytes) {
            var usedPct = swap.used_bytes / swap.total_bytes * 100;
            setText('begonia-zram-swap', fmtBytes(swap.used_bytes) + ' / ' + fmtBytes(swap.total_bytes));
            var swapLevel = usedPct >= 90 ? 'bad' : (usedPct >= 75 ? 'warn' : null);
            bar('begonia-zram-bar', usedPct, swapLevel);
            setLevel('begonia-zram-swap', swapLevel);
        } else {
            setText('begonia-zram-swap', 'no swap');
        }
    }

    /* ---------- pressure (PSI) ---------- */

    function pressureLevel(fullAvg60) {
        if (fullAvg60 === null || fullAvg60 === undefined) return null;
        if (fullAvg60 >= 20) return 'bad';
        if (fullAvg60 >= 10) return 'warn';
        return null;
    }

    function renderPressure(data) {
        if (!data) return;
        if (!data.available) {
            setText('begonia-psi-memory-full', 'PSI unavailable');
            return;
        }
        var mem = data.memory || {};
        var io = data.io || {};
        var cpu = data.cpu || {};

        setText('begonia-psi-memory-some', fmtAvg(mem.some));
        setText('begonia-psi-memory-full', fmtAvg(mem.full));
        setText('begonia-psi-io-some', fmtAvg(io.some));
        setText('begonia-psi-io-full', fmtAvg(io.full));
        setText('begonia-psi-cpu-some', fmtAvg(cpu.some));

        var summary = data.summary || {};
        var memFull = summary.memory_full_avg60;
        var ioFull = summary.io_full_avg60;
        var worst = Math.max(memFull || 0, ioFull || 0);

        var level = pressureLevel(worst);
        setLevel('begonia-psi-memory-full', pressureLevel(memFull));
        setLevel('begonia-psi-io-full', pressureLevel(ioFull));
        bar('begonia-psi-bar', Math.min(100, worst * 5), level);
    }

    /* ---------- CPU clusters ---------- */

    function renderClusters(data) {
        var host = el('begonia-clusters');
        if (!host || !data) return;
        var clusters = data.cpu_clusters || [];
        setText('begonia-clusters-count', clusters.length ? clusters.length + ' clusters' : '—');
        host.innerHTML = '';

        if (!clusters.length) {
            var empty = document.createElement('div');
            empty.className = 'begonia-hint';
            empty.textContent = 'No cpufreq policies exposed by this kernel.';
            host.appendChild(empty);
            return;
        }

        clusters.forEach(function (cluster) {
            var row = document.createElement('div');
            row.className = 'cluster-row role-' + (cluster.role || 'generic');

            var badge = document.createElement('span');
            badge.className = 'cluster-badge';
            badge.textContent = (cluster.role === 'performance' ? 'big' : cluster.role === 'efficiency' ? 'LITTLE' : 'cpu');

            var cpus = document.createElement('span');
            cpus.className = 'cluster-cpus';
            cpus.title = cluster.label || '';
            cpus.textContent = 'CPU ' + (cluster.cpus || '—');

            var freq = document.createElement('span');
            freq.className = 'cluster-freq';
            freq.textContent = cluster.cur_khz ? (cluster.cur_khz / 1000).toFixed(0) + ' MHz' : '—';
            freq.title = 'Governor: ' + (cluster.governor || 'unknown');

            row.appendChild(badge);
            row.appendChild(cpus);
            row.appendChild(freq);
            host.appendChild(row);
        });
    }

    /* ---------- Vivi-AI ---------- */

    function renderVivi(data) {
        if (!data) return;
        var requiredActive = data.required_active_count == null ? data.active_count : data.required_active_count;
        var requiredTotal = data.required_count == null ? data.installed_count : data.required_count;
        var optionalIdle = data.optional_idle_count || 0;

        setText('begonia-vivi-active', requiredActive + '/' + requiredTotal + ' active');
        setText('begonia-vivi-installed',
            data.installed_count + ' installed' + (optionalIdle ? ' · ' + optionalIdle + ' optional idle' : ''));
        setText('begonia-vivi-failed', data.failed_count + ' failed');

        var activeNode = el('begonia-vivi-active');
        if (activeNode) activeNode.classList.toggle('is-good', data.failed_count === 0 && requiredActive > 0);
        var failedNode = el('begonia-vivi-failed');
        if (failedNode) failedNode.classList.toggle('is-bad', data.failed_count > 0);

        var host = el('begonia-vivi-list');
        if (!host) return;
        host.innerHTML = '';

        (data.services || []).forEach(function (svc) {
            var row = document.createElement('div');
            row.className = 'vivi-row sev-' + (svc.severity || 'off');

            var dot = document.createElement('span');
            dot.className = 'vivi-dot';

            var name = document.createElement('span');
            name.className = 'vivi-name';
            name.textContent = svc.label || svc.unit;
            name.title = svc.unit + ' (' + svc.scope + ')' + (svc.optional ? ', optional' : '');

            var state = document.createElement('span');
            state.className = 'vivi-state';
            if (!svc.installed) {
                state.textContent = 'not installed';
            } else if (svc.optional && svc.state !== 'active' && svc.state !== 'failed') {
                state.textContent = (svc.state || 'unknown') + ' (optional)';
            } else {
                state.textContent = svc.state || 'unknown';
            }

            var mem = document.createElement('span');
            mem.className = 'vivi-mem';
            mem.textContent = svc.memory_bytes ? fmtBytes(svc.memory_bytes) : '';

            row.appendChild(dot);
            row.appendChild(name);
            row.appendChild(state);
            row.appendChild(mem);
            host.appendChild(row);
        });
    }

    /* ---------- REST polling ---------- */

    function fetchJson(url) {
        return fetch(url, { credentials: 'same-origin' }).then(function (res) {
            if (!res.ok) throw new Error(url + ' -> HTTP ' + res.status);
            return res.json();
        });
    }

    function pollSlow() {
        fetchJson('/api/system/health').then(renderHealth).catch(function () { /* keep last value */ });
        fetchJson('/api/system/vivi').then(renderVivi).catch(function () { /* keep last value */ });
    }

    function startPolling() {
        pollSlow();
        if (pollTimer === null) pollTimer = setInterval(pollSlow, POLL_MS);
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            if (pollTimer !== null) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        } else {
            startPolling();
        }
    });

    /* ---------- SSE hook used by live.js ---------- */

    window.BegoniaLive = {
        handle: function (metric, data) {
            if (!HIDDEN_METRICS[metric]) return false;
            if (metric === 'zram') renderZram(data);
            else if (metric === 'pressure') renderPressure(data);
            else if (metric === 'platform') renderClusters(data);
            else if (metric === 'vivi') renderVivi(data);
            return true;
        },
        fmtBytes: fmtBytes
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            fetchJson('/api/system/platform').then(renderClusters).catch(function () { /* ignore */ });
            startPolling();
        });
    } else {
        fetchJson('/api/system/platform').then(renderClusters).catch(function () { /* ignore */ });
        startPolling();
    }
})();
