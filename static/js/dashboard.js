// Dashboard state
let currentHealth = 'unknown';
let isPolling = true;
let logOffset = 0;
let logBuildNumber = null;
let logPollingInterval = null;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    fetchPipelineStatus();
    fetchSystemsStatus();
    fetchDeploymentVersion();

    // Start polling
    setInterval(fetchPipelineStatus, 3000);
    setInterval(fetchSystemsStatus, 10000);
    setInterval(fetchDeploymentVersion, 30000);
});

// Fetch pipeline status
async function fetchPipelineStatus() {
    try {
        const response = await fetch('/api/pipeline/status');
        const data = await response.json();

        if (data.error) {
            updateGauge('unknown');
            return;
        }

        updateGauge(data.health);
        updateStages(data.stages);

        // Handle log polling based on build status
        if (data.health === 'building' && data.last_build?.number) {
            startLogPolling(data.last_build.number);
        } else if (currentHealth === 'building' && data.health !== 'building') {
            // Build just finished - stop polling but keep logs visible
            stopLogPolling();
        }
    } catch (error) {
        console.error('Failed to fetch pipeline status:', error);
        updateGauge('unknown');
    }
}

// Update the gauge visualization
function updateGauge(health) {
    const gaugeFill = document.getElementById('gauge-fill');
    const healthLabel = document.getElementById('health-label');

    // Remove old classes
    gaugeFill.classList.remove('healthy', 'building', 'failed', 'unknown');
    healthLabel.classList.remove('healthy', 'building', 'failed', 'unknown');

    // Add new class
    const healthClass = health === 'unstable' ? 'failed' : health;
    gaugeFill.classList.add(healthClass);
    healthLabel.classList.add(healthClass);

    // Update label text
    const labels = {
        healthy: 'HEALTHY',
        building: 'BUILDING',
        failed: 'FAILED',
        unstable: 'UNSTABLE',
        unknown: 'UNKNOWN'
    };
    healthLabel.textContent = labels[health] || 'UNKNOWN';

    currentHealth = health;
}

// Update pipeline stages display
function updateStages(stages) {
    const container = document.getElementById('stages-container');

    if (!stages || stages.length === 0) {
        container.innerHTML = '<div class="stage-placeholder">No stage data available</div>';
        return;
    }

    const stageIcons = {
        success: '✓',
        running: '⟳',
        failed: '✗',
        pending: '○',
        aborted: '⊘',
        unknown: '?'
    };

    let html = '';
    stages.forEach((stage, index) => {
        const icon = stageIcons[stage.status] || stageIcons.unknown;
        const duration = formatDuration(stage.duration_ms);

        html += `
            <div class="stage">
                <div class="stage-box ${stage.status}">
                    <div class="stage-name">${escapeHtml(stage.name)}</div>
                    <div class="stage-icon">${icon}</div>
                    <div class="stage-duration">${duration}</div>
                </div>
            </div>
        `;

        // Add arrow between stages
        if (index < stages.length - 1) {
            html += '<span class="stage-arrow">→</span>';
        }
    });

    container.innerHTML = html;
}

// Fetch systems status
async function fetchSystemsStatus() {
    try {
        const response = await fetch('/api/systems/status');
        const data = await response.json();

        if (data.error) {
            updateSignal('jenkins', 'unhealthy', 'ERROR');
            updateSignal('argocd', 'unhealthy', 'ERROR');
            updateSignal('redis', 'unhealthy', 'ERROR');
            return;
        }

        // Update Jenkins signal
        const jenkinsHealthy = data.jenkins?.status === 'healthy';
        updateSignal('jenkins', jenkinsHealthy ? 'healthy' : 'unhealthy',
            jenkinsHealthy ? 'LIVE' : 'DOWN');

        // Update ArgoCD signal
        const argoHealthy = data.argocd?.status === 'healthy';
        updateSignal('argocd', argoHealthy ? 'healthy' : 'unhealthy',
            argoHealthy ? 'LIVE' : 'DOWN');


        // Update ArgoCD sync signal
        const syncStatus = data.argocd_sync?.sync_status;
        const syncHealthy = syncStatus === 'Synced';
        const syncLabel = syncStatus === 'Synced' ? 'SYNCED' :
                         syncStatus === 'OutOfSync' ? 'OUT OF SYNC' :
                         syncStatus === 'Unknown' ? 'UNKNOWN' : 'SYNCING';
        updateSignal('argocd-sync', syncHealthy ? 'healthy' : 'unhealthy', syncLabel);

    } catch (error) {
        console.error('Failed to fetch systems status:', error);
        updateSignal('jenkins', 'unhealthy', 'ERROR');
        updateSignal('argocd', 'unhealthy', 'ERROR');
        updateSignal('argocd-sync', 'unhealthy', 'ERROR');
    }
}

// Update a system signal indicator
function updateSignal(system, status, label) {
    const signal = document.getElementById(`signal-${system}`);
    if (!signal) return;

    signal.classList.remove('healthy', 'unhealthy');
    signal.classList.add(status);

    const statusEl = signal.querySelector('.signal-status');
    if (statusEl) {
        statusEl.textContent = label;
    }
}

// Fetch deployment version
async function fetchDeploymentVersion() {
    try {
        const response = await fetch('/api/deployment/version');
        const data = await response.json();

        const versionDisplay = document.getElementById('version-display');
        const versionDetails = document.getElementById('version-details');

        if (data.error) {
            versionDisplay.textContent = '---';
            versionDetails.textContent = 'Unable to fetch version';
            return;
        }

        versionDisplay.textContent = data.version || '---';

        if (data.replicas !== undefined) {
            versionDetails.textContent = `${data.replicas}/${data.desired_replicas} replicas`;
        } else {
            versionDetails.textContent = '';
        }

    } catch (error) {
        console.error('Failed to fetch deployment version:', error);
        document.getElementById('version-display').textContent = '---';
        document.getElementById('version-details').textContent = 'Connection error';
    }
}

// Trigger a new build
async function triggerBuild() {
    const btn = document.getElementById('trigger-btn');
    const status = document.getElementById('trigger-status');

    btn.disabled = true;
    btn.textContent = 'TRIGGERING...';
    status.textContent = '';
    status.classList.remove('success', 'error');

    try {
        const response = await fetch('/api/pipeline/trigger', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            status.textContent = 'Build triggered successfully!';
            status.classList.add('success');

            // Immediately poll for new status
            setTimeout(fetchPipelineStatus, 1000);
        } else {
            status.textContent = data.error || 'Failed to trigger build';
            status.classList.add('error');
        }

    } catch (error) {
        console.error('Failed to trigger build:', error);
        status.textContent = 'Connection error';
        status.classList.add('error');
    }

    btn.disabled = false;
    btn.textContent = 'TRIGGER NEW BUILD';

    // Clear status after 5 seconds
    setTimeout(() => {
        status.textContent = '';
        status.classList.remove('success', 'error');
    }, 5000);
}

// Utility: Format duration in milliseconds to human readable
function formatDuration(ms) {
    if (!ms || ms === 0) return '-';

    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
}

// Utility: Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Toggle info/how-it-works section
function toggleInfo() {
    const content = document.getElementById('info-content');
    const arrow = document.getElementById('info-arrow');
    const isExpanding = !content.classList.contains('expanded');

    content.classList.toggle('expanded');
    arrow.classList.toggle('expanded');

    // Scroll to show content after expansion animation
    if (isExpanding) {
        setTimeout(() => {
            content.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 100);
    }
}

// Toggle logs panel
function toggleLogs() {
    const content = document.getElementById('logs-content');
    const arrow = document.getElementById('logs-arrow');

    content.classList.toggle('expanded');
    arrow.classList.toggle('expanded');
}

// Start polling for build logs
function startLogPolling(buildNumber) {
    // Don't restart if already polling same build
    if (logPollingInterval && logBuildNumber === buildNumber) {
        return;
    }

    stopLogPolling();
    logBuildNumber = buildNumber;
    logOffset = 0;

    // Clear previous logs
    const output = document.getElementById('logs-output');
    output.textContent = '';

    // Show logs card
    document.getElementById('logs-card').style.display = 'block';

    // Fetch immediately, then poll
    fetchLogs();
    logPollingInterval = setInterval(fetchLogs, 2000);
}

// Stop polling for logs
function stopLogPolling() {
    if (logPollingInterval) {
        clearInterval(logPollingInterval);
        logPollingInterval = null;
    }
}

// Fetch build logs
async function fetchLogs() {
    if (!logBuildNumber) return;

    try {
        const response = await fetch(`/api/pipeline/logs?build=${logBuildNumber}&start=${logOffset}`);
        const data = await response.json();

        if (data.error) {
            console.error('Log fetch error:', data.error);
            return;
        }

        // Append new text
        if (data.text) {
            const output = document.getElementById('logs-output');
            output.textContent += data.text;
            // Auto-scroll to bottom
            output.scrollTop = output.scrollHeight;
        }

        // Update offset for next request
        logOffset = data.next_start;

        // Stop polling if build is done
        if (!data.has_more) {
            stopLogPolling();
        }
    } catch (error) {
        console.error('Failed to fetch logs:', error);
    }
}

// Hide logs panel
function hideLogs() {
    stopLogPolling();
    document.getElementById('logs-card').style.display = 'none';
    logBuildNumber = null;
    logOffset = 0;
}
