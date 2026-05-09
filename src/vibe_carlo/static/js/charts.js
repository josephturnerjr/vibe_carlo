/**
 * Plotly chart helpers shared by the authenticated and public simulation pages.
 *
 * renderSimulationCharts(result):
 *   result = {
 *     yearLabels: [int],
 *     percentiles: { p10, p25, p50, p75, p90 },
 *     finalDist: [float],
 *   }
 *
 * Renders into elements with ids "fan-chart" and "histogram", which must already
 * exist in the DOM.
 */

function _formatDollar(val) {
    if (val >= 1e6) return '$' + (val / 1e6).toFixed(1) + 'M';
    if (val >= 1e3) return '$' + (val / 1e3).toFixed(0) + 'K';
    return '$' + val.toFixed(0);
}

function renderSimulationCharts(data) {
    var yearLabels = data.yearLabels;
    var percentiles = data.percentiles;
    var finalDist = data.finalDist;

    var fanTraces = [
        {
            x: yearLabels, y: percentiles.p10, type: 'scatter', mode: 'lines',
            line: { width: 0 }, showlegend: false, hoverinfo: 'skip',
        },
        {
            x: yearLabels, y: percentiles.p90, type: 'scatter', mode: 'lines',
            fill: 'tonexty', fillcolor: 'rgba(59, 130, 246, 0.1)',
            line: { width: 0 }, name: '10th–90th', hoverinfo: 'skip',
        },
        {
            x: yearLabels, y: percentiles.p25, type: 'scatter', mode: 'lines',
            line: { width: 0 }, showlegend: false, hoverinfo: 'skip',
        },
        {
            x: yearLabels, y: percentiles.p75, type: 'scatter', mode: 'lines',
            fill: 'tonexty', fillcolor: 'rgba(59, 130, 246, 0.25)',
            line: { width: 0 }, name: '25th–75th', hoverinfo: 'skip',
        },
        {
            x: yearLabels, y: percentiles.p50, type: 'scatter', mode: 'lines',
            line: { color: 'rgb(37, 99, 235)', width: 2.5 }, name: 'Median',
            hovertemplate: 'Year %{x}<br>%{text}<extra></extra>',
            text: percentiles.p50.map(_formatDollar),
        },
    ];

    var fanLayout = {
        xaxis: { title: 'Year', dtick: 5 },
        yaxis: { title: 'Portfolio Value', tickprefix: '$', separatethousands: true },
        legend: { orientation: 'h', y: -0.2 },
        margin: { t: 20, r: 20 },
        hovermode: 'x unified',
        dragmode: 'ontouchstart' in window ? false : 'zoom',
    };

    var histTrace = {
        x: finalDist, type: 'histogram', nbinsx: 60,
        marker: { color: 'rgba(59, 130, 246, 0.7)', line: { color: 'rgba(59, 130, 246, 1)', width: 1 } },
        hovertemplate: '%{x:$,.0f}<br>Count: %{y}<extra></extra>',
    };

    var histLayout = {
        xaxis: { title: 'Final Portfolio Value', tickprefix: '$', separatethousands: true },
        yaxis: { title: 'Frequency' },
        margin: { t: 20, r: 20 },
        bargap: 0.05,
        dragmode: 'ontouchstart' in window ? false : 'zoom',
    };

    Plotly.newPlot('fan-chart', fanTraces, fanLayout, { responsive: true });
    Plotly.newPlot('histogram', [histTrace], histLayout, { responsive: true });
}

function purgeSimulationCharts() {
    var fanChart = document.getElementById('fan-chart');
    var histogram = document.getElementById('histogram');
    if (fanChart) Plotly.purge(fanChart);
    if (histogram) Plotly.purge(histogram);
}
