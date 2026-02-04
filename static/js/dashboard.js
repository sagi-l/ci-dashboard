// Dashboard state
let currentHealth = 'unknown';
let isPolling = true;
let logOffset = 0;
let logBuildNumber = null;
let logPollingInterval = null;

// Favicon SVGs for different states
const favicons = {
    healthy: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='%2300ff88'/></svg>",
    building: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='%23ffcc00'/></svg>",
    failed: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='%23ff4444'/></svg>",
    unknown: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='%2388888a'/></svg>"
};

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    fetchPipelineStatus();
    fetchSystemsStatus();
    fetchDeploymentVersion();
    fetchBuildHistory();
    alignSidebars();

    // Start polling
    setInterval(fetchPipelineStatus, 3000);
    setInterval(fetchSystemsStatus, 10000);
    setInterval(fetchDeploymentVersion, 30000);
    setInterval(fetchBuildHistory, 15000);

    // Realign sidebars on resize
    window.addEventListener('resize', alignSidebars);
});

// Align sidebars with main content
function alignSidebars() {
    const infoCard = document.querySelector('.info-card');
    const stagesCard = document.querySelector('.stages-card');
    const logsCard = document.getElementById('logs-card');
    const topRow = document.querySelector('.top-row');

    if (!infoCard || !topRow) return;

    // Get positions
    const topRowRect = topRow.getBoundingClientRect();
    const infoCardRect = infoCard.getBoundingClientRect();

    // Calculate top and bottom positions
    const topPos = topRowRect.top + window.scrollY;
    const bottomPos = window.innerHeight - (infoCardRect.bottom + window.scrollY);

    // Apply to sidebars (only on desktop)
    if (window.innerWidth > 1100) {
        if (stagesCard) {
            stagesCard.style.top = topPos + 'px';
            stagesCard.style.bottom = Math.max(15, window.innerHeight - infoCardRect.bottom) + 'px';
        }
        if (logsCard) {
            logsCard.style.top = topPos + 'px';
            logsCard.style.bottom = Math.max(15, window.innerHeight - infoCardRect.bottom) + 'px';
        }
    } else {
        // Reset for mobile
        if (stagesCard) {
            stagesCard.style.top = '';
            stagesCard.style.bottom = '';
        }
        if (logsCard) {
            logsCard.style.top = '';
            logsCard.style.bottom = '';
        }
    }
}

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
        updateBranch(data.branch);

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

    // Update favicon
    updateFavicon(healthClass);

    currentHealth = health;
}

// Update favicon based on build status
function updateFavicon(status) {
    const favicon = document.getElementById('favicon');
    if (favicon && favicons[status]) {
        favicon.href = favicons[status];
    }
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

// Update branch name display
function updateBranch(branch) {
    const branchName = document.getElementById('branch-name');
    if (branchName && branch) {
        branchName.textContent = branch;
    }
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

// Fetch build history
async function fetchBuildHistory() {
    try {
        const response = await fetch('/api/pipeline/history');
        const data = await response.json();

        const container = document.getElementById('history-container');

        if (data.error || !data.length) {
            container.innerHTML = '<div class="history-placeholder">No build history</div>';
            return;
        }

        let html = '';
        data.forEach(build => {
            const status = build.result === 'SUCCESS' ? 'success' : 'failed';
            const duration = formatDuration(build.duration_ms);
            const timeAgo = formatTimeAgo(build.timestamp);

            html += `
                <div class="history-item">
                    <div class="history-item-left">
                        <span class="history-status ${status}"></span>
                        <span class="history-number">#${build.number}</span>
                    </div>
                    <div class="history-item-right">
                        <span class="history-duration">${duration}</span>
                        <span class="history-time">${timeAgo}</span>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
        // Realign sidebars after content change
        alignSidebars();

    } catch (error) {
        console.error('Failed to fetch build history:', error);
        document.getElementById('history-container').innerHTML =
            '<div class="history-placeholder">Failed to load history</div>';
    }
}

// Utility: Format timestamp to relative time
function formatTimeAgo(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;

    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
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

    // Scroll to show content after expansion animation and realign sidebars
    if (isExpanding) {
        setTimeout(() => {
            content.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            alignSidebars();
        }, 100);
    } else {
        setTimeout(alignSidebars, 400); // Wait for collapse animation
    }
}

// Toggle logs panel
function toggleLogs() {
    const card = document.getElementById('logs-card');
    const arrow = document.getElementById('logs-arrow');

    card.classList.toggle('expanded');
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
