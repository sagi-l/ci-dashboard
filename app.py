import os
import time
import random
from flask import Flask, render_template, jsonify, request
from config import Config

# pipeline test 1

app = Flask(__name__)

# Mock data for development
MOCK_STAGES = [
    {'name': 'Check Trigger', 'status': 'success', 'duration_ms': 2000},
    {'name': 'Verify BuildKit', 'status': 'success', 'duration_ms': 5000},
    {'name': 'Build & Push', 'status': 'success', 'duration_ms': 45000},
    {'name': 'Update K8s', 'status': 'success', 'duration_ms': 8000}
]


def get_mock_pipeline_status():
    """Generate mock pipeline data for development."""
    statuses = ['healthy', 'building', 'failed']
    weights = [0.7, 0.2, 0.1]

    # Simulate occasional builds
    is_building = random.random() < 0.2

    if is_building:
        health = 'building'
        # Show some stages complete, some in progress
        stages = []
        completed = random.randint(0, 3)
        for i, stage in enumerate(MOCK_STAGES):
            s = dict(stage)
            if i < completed:
                s['status'] = 'success'
            elif i == completed:
                s['status'] = 'running'
                s['duration_ms'] = 0
            else:
                s['status'] = 'pending'
                s['duration_ms'] = 0
            stages.append(s)
    else:
        health = random.choices(statuses, weights)[0]
        if health == 'failed':
            stages = [dict(s) for s in MOCK_STAGES]
            fail_idx = random.randint(0, 3)
            stages[fail_idx]['status'] = 'failed'
            for i in range(fail_idx + 1, len(stages)):
                stages[i]['status'] = 'pending'
                stages[i]['duration_ms'] = 0
        else:
            stages = [dict(s) for s in MOCK_STAGES]

    return {
        'health': health,
        'last_build': {
            'number': 42,
            'result': 'SUCCESS' if health == 'healthy' else ('FAILURE' if health == 'failed' else None),
            'building': is_building,
            'duration': sum(s['duration_ms'] for s in stages),
            'timestamp': int(time.time() * 1000) - 300000,
            'branch': 'main'
        },
        'stages': stages,
        'build_number': 42,
        'branch': 'main'
    }


def get_mock_systems_status():
    """Generate mock systems status for development."""
    return {
        'jenkins': {'status': 'healthy', 'reachable': True},
        'argocd': {'status': 'healthy', 'reachable': True},
        'argocd_sync': {'sync_status': 'Synced', 'health_status': 'Healthy'},
        'github_webhook': {'status': 'healthy', 'reachable': True, 'webhooks': []}
    }


def get_mock_deployment_version():
    """Generate mock deployment version."""
    return {
        'version': 'v1.2.3',
        'image': 'myregistry/web-app:v1.2.3',
        'deployment': 'web-app',
        'replicas': 2,
        'desired_replicas': 2
    }


def get_mock_build_history():
    """Generate mock build history."""
    now = int(time.time() * 1000)
    return [
        {'number': 42, 'result': 'SUCCESS', 'duration_ms': 60000, 'timestamp': now - 300000},
        {'number': 41, 'result': 'SUCCESS', 'duration_ms': 58000, 'timestamp': now - 3600000},
        {'number': 40, 'result': 'FAILURE', 'duration_ms': 45000, 'timestamp': now - 7200000},
        {'number': 39, 'result': 'SUCCESS', 'duration_ms': 62000, 'timestamp': now - 10800000},
        {'number': 38, 'result': 'SUCCESS', 'duration_ms': 59000, 'timestamp': now - 14400000},
    ]


# Initialize clients only if not in mock mode
jenkins_client = None
argocd_client = None
k8s_client = None
github_client = None

if not Config.MOCK_MODE:
    from services.jenkins import JenkinsClient
    from services.argocd import ArgoCDClient
    from services.kubernetes import KubernetesClient
    from services.github import GitHubClient

    jenkins_client = JenkinsClient()
    argocd_client = ArgoCDClient()
    k8s_client = KubernetesClient()
    github_client = GitHubClient()


@app.route('/')
def index():
    """Serve the dashboard HTML."""
    return render_template(
        'index.html',
        github_app_repo=Config.GITHUB_APP_REPO,
        github_infra_repo=Config.GITHUB_INFRA_REPO
    )


@app.route('/healthz')
def healthz():
    """Liveness probe - is the app running?"""
    return jsonify({'status': 'ok'}), 200


@app.route('/readyz')
def readyz():
    """Readiness probe - is the app ready to serve traffic?"""
    # For now, just check if we can reach the services (in non-mock mode)
    if Config.MOCK_MODE:
        return jsonify({'status': 'ok', 'mode': 'mock'}), 200

    checks = {}
    all_ok = True

    try:
        jenkins_health = jenkins_client.get_health()
        checks['jenkins'] = jenkins_health.get('reachable', False)
        if not checks['jenkins']:
            all_ok = False
    except Exception:
        checks['jenkins'] = False
        all_ok = False

    status_code = 200 if all_ok else 503
    return jsonify({'status': 'ok' if all_ok else 'degraded', 'checks': checks}), status_code


@app.route('/api/pipeline/status')
def pipeline_status():
    """Get pipeline health, stages, and current build info."""
    if Config.MOCK_MODE:
        return jsonify(get_mock_pipeline_status())

    try:
        status = jenkins_client.get_pipeline_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pipeline/trigger', methods=['POST'])
def trigger_pipeline():
    """Trigger a new build by bumping VERSION and pushing to GitHub."""
    if Config.MOCK_MODE:
        return jsonify({
            'success': True,
            'message': 'Build triggered (mock mode)',
            'previous_version': '0.0.1',
            'new_version': '0.0.2'
        })

    try:
        # Check webhook health before triggering
        webhook_health = github_client.get_webhook_health()
        if webhook_health.get('status') == 'failing':
            failing_hooks = [
                w for w in webhook_health.get('webhooks', [])
                if w.get('status') == 'failing'
            ]
            return jsonify({
                'success': False,
                'error': 'GitHub webhook is failing - build would not start. Check your tunnel/ingress.',
                'webhook_status': failing_hooks
            }), 503

        result = github_client.bump_version()
        return jsonify({
            'success': True,
            'message': f'Version bumped to {result["new_version"]}, build will start via webhook',
            'previous_version': result['previous_version'],
            'new_version': result['new_version']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pipeline/logs')
def pipeline_logs():
    """Get progressive build logs."""
    if Config.MOCK_MODE:
        return jsonify({
            'text': '[Mock] Building step 1...\n[Mock] Building step 2...\n',
            'next_start': 100,
            'has_more': False,
            'build_number': 42
        })

    try:
        build_number = request.args.get('build', type=int)
        start = request.args.get('start', 0, type=int)
        logs = jenkins_client.get_build_logs(build_number, start)
        return jsonify(logs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/systems/status')
def systems_status():
    """Get health status of Jenkins and ArgoCD."""
    if Config.MOCK_MODE:
        return jsonify(get_mock_systems_status())

    try:
        status = {
            'jenkins': jenkins_client.get_health(),
            'argocd': argocd_client.get_health(),
            'argocd_sync': argocd_client.get_application_status(Config.ARGOCD_APP_NAME),
            'github_webhook': github_client.get_webhook_health()
        }
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/deployment/version')
def deployment_version():
    """Get current deployed version."""
    if Config.MOCK_MODE:
        return jsonify(get_mock_deployment_version())

    try:
        version = k8s_client.get_deployment_version()
        return jsonify(version)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pipeline/history')
def pipeline_history():
    """Get recent build history."""
    if Config.MOCK_MODE:
        return jsonify(get_mock_build_history())

    try:
        history = jenkins_client.get_build_history(limit=5)
        return jsonify(history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
