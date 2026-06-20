// State management
let activeView = 'beds-view';
let bedsData = [];
let selectedBedId = null;
let autoSimIntervalId = null;

document.addEventListener('DOMContentLoaded', () => {
    // Start system clock
    startClock();
    
    // Initial fetch of beds
    fetchBeds();
    
    // Set up form submission handlers
    setupFormHandlers();
    
    // Set up Drag & Drop for Excel Upload
    setupDragAndDrop();
});

// Real-time system clock
function startClock() {
    const timeEl = document.getElementById('system-time');
    setInterval(() => {
        const now = new Date();
        timeEl.textContent = now.toLocaleTimeString();
    }, 1000);
}

// Switch dashboard views
function switchView(viewId) {
    // Hide all views
    document.querySelectorAll('.dashboard-view').forEach(view => {
        view.classList.remove('active');
    });
    
    // Deactivate all sidebar nav items
    document.querySelectorAll('.sidebar-nav li').forEach(item => {
        item.classList.remove('active');
    });
    
    // Show selected view
    const targetView = document.getElementById(viewId);
    if (targetView) {
        targetView.classList.add('active');
        activeView = viewId;
    }
    
    // Update active nav state in sidebar
    if (viewId === 'beds-view') {
        document.getElementById('nav-beds').classList.add('active');
        document.getElementById('view-title').textContent = "NICU Bedside Monitor";
        document.getElementById('view-subtitle').textContent = "Real-time physiological telemetry & sepsis risk calculation";
    } else if (viewId === 'upload-view') {
        document.getElementById('nav-upload').classList.add('active');
        document.getElementById('view-title').textContent = "Batch Sepsis Predictor";
        document.getElementById('view-subtitle').textContent = "Upload neonatal vital logs in bulk format";
    } else if (viewId === 'add-baby-view') {
        document.getElementById('nav-add-baby').classList.add('active');
        document.getElementById('view-title').textContent = "Admit Newborn Patient";
        document.getElementById('view-subtitle').textContent = "Initialize monitoring telemetry for a new infant";
    }
}

// Fetch all patient beds from backend
async function fetchBeds() {
    try {
        const response = await fetch('/api/beds');
        if (!response.ok) throw new Error("Failed to fetch beds data");
        
        bedsData = await response.json();
        
        // Update sidebar counters
        updateSidebarStats();
        
        // If we are on beds grid view, render it
        if (activeView === 'beds-view') {
            renderBedsGrid();
        }
        
        // If we are currently viewing a patient detail, refresh their details
        if (selectedBedId) {
            refreshSelectedBedDetails();
        }
        
    } catch (err) {
        console.error("Error fetching beds:", err);
    }
}

// Update sidebar counters based on current risk levels
function updateSidebarStats() {
    document.getElementById('stat-active-beds').textContent = bedsData.length;
    
    let criticalCount = 0;
    let warningCount = 0;
    
    bedsData.forEach(bed => {
        if (bed.risk_category === 'Critical Risk' || bed.risk_category === 'Very High Risk') {
            criticalCount++;
        } else if (bed.risk_category === 'High Risk' || bed.risk_category === 'Moderate Risk') {
            warningCount++;
        }
    });
    
    document.getElementById('stat-critical-count').textContent = criticalCount;
    document.getElementById('stat-warning-count').textContent = warningCount;
}

// Render the grid of NICU Beds
function renderBedsGrid() {
    const container = document.getElementById('beds-grid-container');
    if (!container) return;
    
    if (bedsData.length === 0) {
        container.innerHTML = `
            <div class="loading-state">
                <i class="fa-solid fa-circle-info" style="font-size: 2rem; color: var(--text-muted);"></i>
                <p>No newborn beds admitted to the NICU.</p>
            </div>`;
        return;
    }
    
    let html = '';
    bedsData.forEach(bed => {
        const vitals = bed.latest_vitals;
        
        // Establish alert visual classes
        let riskClass = 'risk-low';
        let badgeClass = 'low';
        if (bed.risk_category === 'Critical Risk') { riskClass = 'risk-critical'; badgeClass = 'critical'; }
        else if (bed.risk_category === 'Very High Risk') { riskClass = 'risk-high'; badgeClass = 'high'; }
        else if (bed.risk_category === 'High Risk') { riskClass = 'risk-high'; badgeClass = 'high'; }
        else if (bed.risk_category === 'Moderate Risk') { riskClass = 'risk-mod'; badgeClass = 'mod'; }
        
        // Check for specific vital warning highlights based on backend vital statuses
        const hasSpO2Warning = bed.vital_statuses.spo2 === 'LOW' || bed.vital_statuses.spo2 === 'CRITICAL_LOW';
        const hasTempWarning = bed.vital_statuses.temp !== 'NORMAL';
        const hasRRWarning = bed.vital_statuses.rr !== 'NORMAL';
        const hasWBCWarning = bed.vital_statuses.wbc !== 'TYPICAL';
        
        // Radial progress math: circumference of r=30 is ~188.5
        const circum = 188.5;
        const offset = circum * (1 - bed.nss / 100);
        
        // Stroke color for the small radial progress
        let strokeColor = 'var(--color-emerald)';
        if (bed.risk_category === 'Critical Risk' || bed.risk_category === 'Very High Risk' || bed.risk_category === 'High Risk') strokeColor = 'var(--color-red)';
        else if (bed.risk_category === 'Moderate Risk') strokeColor = 'var(--color-orange)';
        
        // Construct visual alert banner if critical warnings exist
        let alertBannerHtml = '';
        if (bed.alerts && bed.alerts.length > 0) {
            alertBannerHtml = `
                <div class="bed-card-alert-banner">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <span>${bed.alerts[0].message}</span>
                </div>
            `;
        }

        html += `
            <div class="glass-card bed-card ${riskClass}" onclick="selectBed('${bed.id}')">
                <div class="bed-card-header">
                    <div class="bed-number">${bed.id.toUpperCase().replace('_', ' ')}</div>
                    <div class="baby-name">${bed.name} (${bed.gender})</div>
                </div>
                <div class="bed-card-body">
                    <!-- Vitals Summary -->
                    <div class="bed-vitals-mini">
                        <div class="vital-mini-row">
                            <span>SpO₂</span>
                            <strong class="${hasSpO2Warning ? 'vital-danger' : 'vital-ok'} font-mono">${vitals.spo2_percent}%</strong>
                        </div>
                        <div class="vital-mini-row">
                            <span>Temp</span>
                            <strong class="${hasTempWarning ? 'vital-warning' : 'vital-ok'} font-mono">${vitals.temperature_c}°C</strong>
                        </div>
                        <div class="vital-mini-row">
                            <span>RR</span>
                            <strong class="${hasRRWarning ? 'vital-danger' : 'vital-ok'} font-mono">${vitals.resp_rate_min}/m</strong>
                        </div>
                        <div class="vital-mini-row">
                            <span>WBC</span>
                            <strong class="${hasWBCWarning ? 'vital-warning' : 'vital-ok'} font-mono">${vitals.wbcჩl}</strong>
                        </div>
                    </div>
                    
                    <!-- Circular Sepsis Score -->
                    <div class="radial-progress">
                        <svg width="80" height="80" viewBox="0 0 80 80">
                            <circle cx="40" cy="40" r="30" class="gauge-bg" />
                            <circle cx="40" cy="40" r="30" class="gauge-fill" 
                                    stroke="${strokeColor}"
                                    stroke-dasharray="${circum}" 
                                    stroke-dashoffset="${offset}" />
                        </svg>
                        <div class="bed-card-score-lbl">
                            <span class="score-num font-mono">${Math.round(bed.nss)}</span>
                            <span class="score-title">NSS</span>
                        </div>
                    </div>
                    
                    ${alertBannerHtml}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Select a patient bed and open detailed view
async function selectBed(bedId) {
    selectedBedId = bedId;
    switchView('patient-detail-view');
    
    // Fetch fresh detailed data for this bed
    try {
        const response = await fetch(`/api/beds/${bedId}`);
        if (!response.ok) throw new Error("Failed to load patient detail");
        
        const bed = await response.json();
        
        // Render details
        renderPatientDetail(bed);
        
    } catch (err) {
        console.error("Error loading patient details:", err);
    }
}

// Refresh detailed views (used during simulation ticks)
async function refreshSelectedBedDetails() {
    if (!selectedBedId) return;
    try {
        const response = await fetch(`/api/beds/${selectedBedId}`);
        if (response.ok) {
            const bed = await response.json();
            renderPatientDetail(bed);
        }
    } catch (e) {
        console.error("Error refreshing active bed details:", e);
    }
}

// Render patient details onto screen elements
function renderPatientDetail(bed) {
    // Header
    document.getElementById('view-title').textContent = `${bed.id.toUpperCase().replace('_', ' ')} Monitor - ${bed.name}`;
    document.getElementById('view-subtitle').textContent = `Clinical status, predictive trends, and detailed diagnostics.`;
    
    // Demographics
    document.getElementById('detail-bed-id').textContent = bed.id.toUpperCase().replace('_', ' ');
    document.getElementById('detail-patient-name').textContent = bed.name;
    document.getElementById('detail-gender').textContent = bed.gender;
    document.getElementById('detail-admission').textContent = bed.date_of_admission;
    document.getElementById('detail-ga').textContent = `${bed.gestational_age_weeks} Weeks - ${bed.ga_category} (${bed.ga_multiplier})`;
    document.getElementById('detail-bw').textContent = `${bed.birth_weight_g} g - ${bed.bw_category}`;
    
    // NSS Gauge Circle Circumference = 2 * PI * 70 = 439.82
    const score = bed.nss;
    const circum = 439.82;
    const offset = circum * (1 - score / 100);
    const circle = document.getElementById('detail-nss-circle');
    circle.style.strokeDasharray = circum;
    circle.style.strokeDashoffset = offset;
    
    // Color gauge fill based on risk
    let color = 'var(--color-emerald)';
    if (bed.risk_category === 'Critical Risk' || bed.risk_category === 'Very High Risk') color = 'var(--color-red)';
    else if (bed.risk_category === 'High Risk') color = 'var(--color-red)';
    else if (bed.risk_category === 'Moderate Risk') color = 'var(--color-orange)';
    circle.style.stroke = color;
    
    document.getElementById('detail-nss-score').textContent = Math.round(score);
    const catEl = document.getElementById('detail-nss-category');
    catEl.textContent = bed.risk_category;
    catEl.className = `score-cat`;
    if (bed.risk_category === 'Critical Risk' || bed.risk_category === 'Very High Risk' || bed.risk_category === 'High Risk') catEl.classList.add('text-danger');
    else if (bed.risk_category === 'Moderate Risk') catEl.classList.add('text-warning');
    else catEl.classList.add('text-emerald');
    
    // NSS Sub-values
    document.getElementById('detail-nss-val').textContent = score.toFixed(1);
    document.getElementById('detail-ml-val').textContent = `${bed.ml_risk_score.toFixed(1)}%`;
    
    // Clinical Indices Bars
    updateIndexBar('tvi', bed.tvi);
    updateIndexBar('hsi', bed.hsi);
    updateIndexBar('ois', bed.ois);
    updateIndexBar('prs', bed.prs);
    
    // Vitals Cards
    const latest = bed.history[bed.history.length - 1];
    
    // SpO2
    document.getElementById('val-spo2').textContent = latest.spo2_percent;
    const trendSpo2 = document.getElementById('trend-spo2');
    const sStatus = bed.vital_statuses.spo2;
    if (sStatus === "CRITICAL_LOW") {
        trendSpo2.className = "vital-trend text-danger";
        trendSpo2.innerHTML = '<i class="fa-solid fa-angles-down"></i> Crit Low';
    } else if (sStatus === "LOW") {
        trendSpo2.className = "vital-trend text-danger";
        trendSpo2.innerHTML = '<i class="fa-solid fa-arrow-down"></i> Low';
    } else if (sStatus === "TARGET") {
        trendSpo2.className = "vital-trend text-emerald";
        trendSpo2.innerHTML = '<i class="fa-solid fa-circle-check"></i> Target';
    } else {
        trendSpo2.className = "vital-trend text-warning";
        trendSpo2.innerHTML = '<i class="fa-solid fa-arrow-up"></i> High';
    }
    
    // Temp
    document.getElementById('val-temp').textContent = latest.temperature_c.toFixed(2);
    const trendTemp = document.getElementById('trend-temp');
    const tStatus = bed.vital_statuses.temp;
    if (tStatus === "HYPOTHERMIA") {
        trendTemp.className = "vital-trend text-danger";
        trendTemp.innerHTML = '<i class="fa-solid fa-snowflake"></i> Hypothermia';
    } else if (tStatus === "MILD_HYPO") {
        trendTemp.className = "vital-trend text-warning";
        trendTemp.innerHTML = '<i class="fa-solid fa-arrow-down"></i> Mild Hypo';
    } else if (tStatus === "NORMAL") {
        trendTemp.className = "vital-trend text-emerald";
        trendTemp.innerHTML = '<i class="fa-solid fa-circle-check"></i> Normal';
    } else if (tStatus === "ELEVATED") {
        trendTemp.className = "vital-trend text-warning";
        trendTemp.innerHTML = '<i class="fa-solid fa-arrow-up"></i> Elevated';
    } else {
        trendTemp.className = "vital-trend text-danger";
        trendTemp.innerHTML = '<i class="fa-solid fa-fire"></i> Fever';
    }
    
    // RR
    document.getElementById('val-rr').textContent = Math.round(latest.resp_rate_min);
    const trendRR = document.getElementById('trend-rr');
    const rStatus = bed.vital_statuses.rr;
    if (rStatus === "DISTRESS") {
        trendRR.className = "vital-trend text-danger";
        trendRR.innerHTML = '<i class="fa-solid fa-angles-up"></i> Distress';
    } else if (rStatus === "TACHYPNEA") {
        trendRR.className = "vital-trend text-warning";
        trendRR.innerHTML = '<i class="fa-solid fa-arrow-up"></i> Tachypnea';
    } else if (rStatus === "APNEA") {
        trendRR.className = "vital-trend text-danger";
        trendRR.innerHTML = '<i class="fa-solid fa-arrow-down"></i> Apnea';
    } else {
        trendRR.className = "vital-trend text-emerald";
        trendRR.innerHTML = '<i class="fa-solid fa-circle-check"></i> Normal';
    }
    
    // CRP
    document.getElementById('val-crp').textContent = latest.crp_mg_l.toFixed(1);
    const trendCrp = document.getElementById('trend-crp');
    const cStatus = bed.vital_statuses.crp;
    
    let crpDelta = 0;
    if (bed.history.length >= 2) {
        crpDelta = latest.crp_mg_l - bed.history[bed.history.length - 2].crp_mg_l;
    }
    
    if (cStatus === "SEPSIS_SUSPICION") {
        trendCrp.className = "vital-trend text-danger";
        trendCrp.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Sepsis Ind';
    } else if (crpDelta > 5 || cStatus === "SIG_INFLAM") {
        trendCrp.className = "vital-trend text-danger";
        trendCrp.innerHTML = '<i class="fa-solid fa-trending-up"></i> Rising';
    } else if (cStatus === "MILD_INFLAM" || cStatus === "BORDERLINE") {
        trendCrp.className = "vital-trend text-warning";
        trendCrp.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Inflamed';
    } else {
        trendCrp.className = "vital-trend text-emerald";
        trendCrp.innerHTML = '<i class="fa-solid fa-circle-check"></i> Normal';
    }
    
    // WBC
    document.getElementById('val-wbc').textContent = latest.wbcჩl.toFixed(1);
    const trendWbc = document.getElementById('trend-wbc');
    const wStatus = bed.vital_statuses.wbc;
    if (wStatus === "LEUKOPENIA") {
        trendWbc.className = "vital-trend text-danger";
        trendWbc.innerHTML = '<i class="fa-solid fa-angles-down"></i> Leukopenia';
    } else if (wStatus === "LEUKOCYTOSIS") {
        trendWbc.className = "vital-trend text-danger";
        trendWbc.innerHTML = '<i class="fa-solid fa-angles-up"></i> Leukocytosis';
    } else if (wStatus === "LOW") {
        trendWbc.className = "vital-trend text-warning";
        trendWbc.innerHTML = '<i class="fa-solid fa-arrow-down"></i> Low';
    } else if (wStatus === "ELEVATED") {
        trendWbc.className = "vital-trend text-warning";
        trendWbc.innerHTML = '<i class="fa-solid fa-arrow-up"></i> High';
    } else {
        trendWbc.className = "vital-trend text-emerald";
        trendWbc.innerHTML = '<i class="fa-solid fa-circle-check"></i> Normal';
    }
    
    // HR
    document.getElementById('val-hr').textContent = Math.round(latest.heart_rate_bpm);
    document.getElementById('val-hrv-label').textContent = `HRV: ${Math.round(latest.hrv)}ms`;
    
    // Active Alerts List
    const alertsContainer = document.getElementById('detail-alerts-container');
    const alertsBox = document.getElementById('detail-alerts-box');
    
    if (bed.alerts && bed.alerts.length > 0) {
        alertsBox.style.display = 'block';
        alertsContainer.innerHTML = bed.alerts.map(alert => `
            <div class="alert-item ${alert.type}">
                <i class="fa-solid ${alert.type === 'danger' ? 'fa-circle-radiation' : alert.type === 'warning' ? 'fa-triangle-exclamation' : 'fa-circle-info'}"></i>
                <span>${alert.message}</span>
            </div>
        `).join('');
    } else {
        alertsBox.style.display = 'none';
    }
    
    // Render History Plotly Chart
    drawVitalsChart(bed.history);
}

// Update the layout bar for clinical indices
function updateIndexBar(id, value) {
    document.getElementById(`lbl-${id}`).textContent = value.toFixed(1);
    document.getElementById(`bar-${id}`).style.width = `${value}%`;
    
    // Set colors based on risk thresholds
    const fill = document.getElementById(`bar-${id}`);
    if (value > 75) {
        fill.style.backgroundColor = 'var(--color-red)';
    } else if (value > 40) {
        fill.style.backgroundColor = 'var(--color-orange)';
    } else {
        fill.style.backgroundColor = 'var(--color-cyan)';
    }
}

// Draw high-fidelity medical telemetry line chart using Plotly
function drawVitalsChart(history) {
    const timestamps = history.map(h => {
        const d = new Date(h.timestamp);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });
    
    const spo2 = history.map(h => h.spo2_percent);
    const temp = history.map(h => h.temperature_c);
    const hrv = history.map(h => h.hrv);
    const crp = history.map(h => h.crp_mg_l);
    
    // Set up trace 1: SpO2
    const traceSpo2 = {
        x: timestamps,
        y: spo2,
        name: 'SpO₂ Saturation (%)',
        type: 'scatter',
        mode: 'lines+markers',
        line: { color: '#06b6d4', width: 3, shape: 'spline' },
        marker: { size: 6 },
        yaxis: 'y'
    };
    
    // Set up trace 2: Temperature
    const traceTemp = {
        x: timestamps,
        y: temp,
        name: 'Temperature (°C)',
        type: 'scatter',
        mode: 'lines+markers',
        line: { color: '#f59e0b', width: 3, shape: 'spline' },
        marker: { size: 6 },
        yaxis: 'y2'
    };

    // Set up trace 3: HRV
    const traceHRV = {
        x: timestamps,
        y: hrv,
        name: 'HRV (ms)',
        type: 'scatter',
        mode: 'lines+markers',
        line: { color: '#ef4444', width: 2, dash: 'dot', shape: 'spline' },
        marker: { size: 4 },
        yaxis: 'y3'
    };
    
    const data = [traceSpo2, traceTemp, traceHRV];
    
    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(255,255,255,0.01)',
        margin: { t: 30, r: 50, b: 40, l: 50 },
        hovermode: 'closest',
        showlegend: true,
        legend: {
            orientation: 'h',
            y: 1.15,
            x: 0.1,
            font: { color: '#9ca3af', size: 10 }
        },
        xaxis: {
            gridcolor: 'rgba(255,255,255,0.05)',
            tickfont: { color: '#9ca3af', family: 'JetBrains Mono', size: 9 },
            linecolor: 'rgba(255,255,255,0.1)'
        },
        yaxis: {
            title: 'SpO₂ / HRV',
            titlefont: { color: '#06b6d4', size: 10 },
            gridcolor: 'rgba(255,255,255,0.05)',
            tickfont: { color: '#06b6d4', family: 'JetBrains Mono', size: 9 },
            linecolor: 'rgba(255,255,255,0.1)',
            range: [65, 105]
        },
        yaxis2: {
            title: 'Temperature (°C)',
            titlefont: { color: '#f59e0b', size: 10 },
            tickfont: { color: '#f59e0b', family: 'JetBrains Mono', size: 9 },
            overlaying: 'y',
            side: 'right',
            gridcolor: 'rgba(255,255,255,0.02)',
            linecolor: 'rgba(255,255,255,0.1)',
            range: [34.5, 40.0]
        },
        // Setup hidden 3rd axis mapping for HRV limits if needed, overlaying on left
        yaxis3: {
            visible: false,
            overlaying: 'y',
            range: [0, 100]
        }
    };
    
    const config = {
        responsive: true,
        displayModeBar: false
    };
    
    Plotly.newPlot('vitals-trend-chart', data, layout, config);
}

// Form Handlers Setup
function setupFormHandlers() {
    // Record Manual Vitals Form
    const recordForm = document.getElementById('recordVitalsForm');
    if (recordForm) {
        recordForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!selectedBedId) return;
            
            const submitBtn = document.getElementById('btn-submit-record');
            submitBtn.disabled = true;
            
            const formData = new FormData(recordForm);
            const data = {
                heart_rate_bpm: parseFloat(formData.get('heart_rate_bpm')),
                spo2_percent: parseFloat(formData.get('spo2_percent')),
                temperature_c: parseFloat(formData.get('temperature_c')),
                resp_rate_min: parseFloat(formData.get('resp_rate_min')),
                crp_mg_l: parseFloat(formData.get('crp_mg_l')),
                wbc_l: parseFloat(formData.get('wbc_l')),
                hrv: parseFloat(formData.get('hrv'))
            };
            
            try {
                const response = await fetch(`/api/beds/${selectedBedId}/record`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (!response.ok) {
                    const res = await response.json();
                    throw new Error(res.error || "Failed to update record");
                }
                
                // Refresh data
                const updatedBed = await response.json();
                renderPatientDetail(updatedBed);
                recordForm.reset();
                
                // Triggers parent fetch to sync bedside list in background
                fetchBeds();
                
            } catch (err) {
                alert("Error recording vitals: " + err.message);
            } finally {
                submitBtn.disabled = false;
            }
        });
    }
    
    // Admit Newborn Form
    const addBabyForm = document.getElementById('addBabyForm');
    if (addBabyForm) {
        addBabyForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = document.getElementById('btn-submit-admission');
            submitBtn.disabled = true;
            
            const formData = new FormData(addBabyForm);
            const data = {
                name: formData.get('name'),
                gender: formData.get('gender'),
                gestational_age_weeks: parseFloat(formData.get('gestational_age_weeks')),
                birth_weight_g: parseFloat(formData.get('birth_weight_g')),
                heart_rate_bpm: parseFloat(formData.get('heart_rate_bpm')),
                spo2_percent: parseFloat(formData.get('spo2_percent')),
                temperature_c: parseFloat(formData.get('temperature_c')),
                resp_rate_min: parseFloat(formData.get('resp_rate_min')),
                crp_mg_l: parseFloat(formData.get('crp_mg_l')),
                wbc_l: parseFloat(formData.get('wbc_l')),
                hrv: parseFloat(formData.get('hrv'))
            };
            
            try {
                const response = await fetch('/api/beds/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (!response.ok) {
                    const res = await response.json();
                    throw new Error(res.error || "Failed to admit newborn");
                }
                
                addBabyForm.reset();
                await fetchBeds();
                switchView('beds-view');
                
            } catch (err) {
                alert("Error admitting newborn: " + err.message);
            } finally {
                submitBtn.disabled = false;
            }
        });
    }
}

// Drag and drop setup for Excel files
function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('excelFile');
    const uploadForm = document.getElementById('excelUploadForm');
    
    if (!dropZone || !fileInput) return;
    
    // Triggers file browse on drop-zone click
    dropZone.addEventListener('click', () => fileInput.click());
    
    // Highlight drop zone on dragover
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        }, false);
    });
    
    // Remove highlights
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        }, false);
    });
    
    // Handle dropped file
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            fileInput.files = files;
            updateDropZoneLabel(files[0].name);
        }
    });
    
    // File selected manually
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            updateDropZoneLabel(fileInput.files[0].name);
        }
    });
    
    function updateDropZoneLabel(name) {
        dropZone.querySelector('p').innerHTML = `Selected File: <strong style="color:var(--color-cyan)">${name}</strong>`;
    }
    
    // Form upload submission
    if (uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (fileInput.files.length === 0) {
                alert("Please select or drop an Excel file first.");
                return;
            }
            
            const submitBtn = document.getElementById('btn-upload-excel');
            const loader = document.getElementById('upload-loader');
            const errorBox = document.getElementById('upload-error');
            const resultsSection = document.getElementById('batchResultsSection');
            const tbody = document.getElementById('batch-results-tbody');
            
            submitBtn.disabled = true;
            loader.style.display = 'flex';
            errorBox.style.display = 'none';
            resultsSection.style.display = 'none';
            
            const formPayload = new FormData();
            formPayload.append('file', fileInput.files[0]);
            
            try {
                const response = await fetch('/predict', {
                    method: 'POST',
                    body: formPayload
                });
                
                const result = await response.json();
                
                if (!response.ok) {
                    throw new Error(result.error || "Batch prediction failed");
                }
                
                // Render batch results table
                tbody.innerHTML = result.results.map(row => {
                    const v = row.vitals;
                    
                    let badgeClass = 'low';
                    if (row.risk_category === 'Critical Risk') badgeClass = 'critical';
                    else if (row.risk_category === 'Very High Risk' || row.risk_category === 'High Risk') badgeClass = 'high';
                    else if (row.risk_category === 'Moderate Risk') badgeClass = 'mod';
                    
                    return `
                        <tr>
                            <td><strong style="color:var(--color-cyan)">${row.patient_id}</strong></td>
                            <td class="font-mono">${v.gestational_age_weeks} weeks</td>
                            <td class="font-mono">${v.birth_weight_g} g</td>
                            <td>
                                <div style="display:flex; gap:10px;">
                                    <span>SpO2: <strong class="font-mono">${v.spo2_percent}%</strong></span>
                                    <span>HR: <strong class="font-mono">${v.heart_rate_bpm}</strong></span>
                                    <span>T: <strong class="font-mono">${v.temperature_c}°C</strong></span>
                                    <span>RR: <strong class="font-mono">${v.resp_rate_min}</strong></span>
                                </div>
                            </td>
                            <td>
                                <div style="display:flex; gap:10px;">
                                    <span>CRP: <strong class="font-mono">${v.crp_mg_l}</strong></span>
                                    <span>WBC: <strong class="font-mono">${v.wbc_l}</strong></span>
                                </div>
                            </td>
                            <td class="font-mono" style="font-weight:600">${row.ml_risk_score.toFixed(1)}%</td>
                            <td class="font-mono" style="font-weight:600">${row.nss.toFixed(1)}</td>
                            <td><span class="badge-tag ${badgeClass}">${row.risk_category}</span></td>
                        </tr>
                    `;
                }).join('');
                
                resultsSection.style.display = 'block';
                
            } catch (err) {
                errorBox.textContent = err.message;
                errorBox.style.display = 'block';
            } finally {
                loader.style.display = 'none';
                submitBtn.disabled = false;
            }
        });
    }
}

// Telemetry Simulation Actions
async function triggerSimulationStep() {
    const btn = document.getElementById('btn-sim-step');
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/simulate', { method: 'POST' });
        if (response.ok) {
            await fetchBeds();
        }
    } catch (e) {
        console.error(e);
    } finally {
        btn.disabled = false;
    }
}

function toggleAutoSimulation(checkbox) {
    if (checkbox.checked) {
        // Trigger immediately
        triggerSimulationStep();
        // Set loop (every 5 seconds)
        autoSimIntervalId = setInterval(() => {
            triggerSimulationStep();
        }, 5000);
    } else {
        if (autoSimIntervalId) {
            clearInterval(autoSimIntervalId);
            autoSimIntervalId = null;
        }
    }
}

async function resetSimulation() {
    const btn = document.getElementById('btn-sim-reset');
    btn.disabled = true;
    
    if (confirm("Are you sure you want to reset all patient telemetry back to original clinical histories?")) {
        try {
            const response = await fetch('/api/reset', { method: 'POST' });
            if (response.ok) {
                await fetchBeds();
                // Return to bed grid if we reset
                switchView('beds-view');
                selectedBedId = null;
            }
        } catch (e) {
            console.error(e);
        }
    }
    
    btn.disabled = false;
}
