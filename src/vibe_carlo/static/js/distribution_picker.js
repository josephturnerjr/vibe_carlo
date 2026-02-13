/**
 * Distribution picker: show/hide fields and render preview charts.
 * Works with any prefix for reusable distribution pickers.
 */

function updateDistFields(prefix) {
    var distType = document.getElementById(prefix + '_dist_type').value;
    var groups = ['flat', 'uniform', 'truncated_normal'];

    groups.forEach(function(g) {
        var el = document.getElementById(prefix + '_' + g + '_fields');
        if (!el) return;
        var isActive = (g === distType);
        el.classList.toggle('hidden', !isActive);
        // Disable hidden inputs so they don't submit
        var inputs = el.querySelectorAll('input');
        inputs.forEach(function(inp) { inp.disabled = !isActive; });
    });

    updateDistPreview(prefix);
}

function updateDistPreview(prefix) {
    var distType = document.getElementById(prefix + '_dist_type').value;
    var previewEl = prefix + '_preview';
    var traces;

    if (distType === 'flat') {
        var val = parseFloat(document.getElementById(prefix + '_dist_value').value) || 0;
        traces = _flatTrace(val);
    } else if (distType === 'uniform') {
        var low = parseFloat(document.getElementById(prefix + '_u_low').value) || 0;
        var high = parseFloat(document.getElementById(prefix + '_u_high').value) || 0;
        traces = _uniformTrace(low, high);
    } else if (distType === 'truncated_normal') {
        var low = parseFloat(document.getElementById(prefix + '_tn_low').value) || 0;
        var high = parseFloat(document.getElementById(prefix + '_tn_high').value) || 0;
        var mean = parseFloat(document.getElementById(prefix + '_tn_mean').value) || 0;
        var stddev = parseFloat(document.getElementById(prefix + '_tn_stddev').value) || 1;
        traces = _truncatedNormalTrace(low, high, mean, stddev);
    } else {
        return;
    }

    var layout = {
        margin: { t: 4, b: 20, l: 40, r: 10 },
        height: 96,
        xaxis: { tickprefix: '$', separatethousands: true, tickfont: { size: 10 } },
        yaxis: { showticklabels: false, showgrid: false, zeroline: false },
        showlegend: false,
    };

    Plotly.react(previewEl, traces, layout, { responsive: true, displayModeBar: false });
}

function _flatTrace(val) {
    if (val <= 0) {
        return [{ x: [0], y: [0], type: 'bar', marker: { color: 'rgba(59,130,246,0.7)' } }];
    }
    return [{
        x: [val],
        y: [1],
        type: 'bar',
        width: [Math.max(val * 0.02, 100)],
        marker: { color: 'rgba(59,130,246,0.7)' },
    }];
}

function _uniformTrace(low, high) {
    if (high <= low) {
        return _flatTrace(low);
    }
    var h = 1.0 / (high - low);
    return [{
        x: [low, low, high, high],
        y: [0, h, h, 0],
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        fillcolor: 'rgba(59,130,246,0.2)',
        line: { color: 'rgb(59,130,246)', width: 2 },
    }];
}

function _truncatedNormalTrace(low, high, mean, stddev) {
    if (high <= low || stddev <= 0) {
        return _flatTrace(mean);
    }
    var n = 200;
    var xs = [];
    var ys = [];
    var step = (high - low) / n;
    for (var i = 0; i <= n; i++) {
        var x = low + i * step;
        var z = (x - mean) / stddev;
        var y = Math.exp(-0.5 * z * z);
        xs.push(x);
        ys.push(y);
    }
    return [{
        x: xs,
        y: ys,
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        fillcolor: 'rgba(59,130,246,0.2)',
        line: { color: 'rgb(59,130,246)', width: 2 },
    }];
}

// Initialize all distribution pickers on page load
document.addEventListener('DOMContentLoaded', function() {
    var selectors = document.querySelectorAll('[id$="_dist_type"]');
    selectors.forEach(function(sel) {
        var prefix = sel.id.replace('_dist_type', '');
        updateDistFields(prefix);
    });
});
