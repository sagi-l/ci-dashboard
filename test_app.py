import pytest
from app import app


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_healthz_returns_ok(client):
    """Health endpoint should return 200 with status ok."""
    response = client.get('/healthz')

    assert response.status_code == 200
    assert response.json['status'] == 'ok'


def test_readyz_in_mock_mode(client):
    """Readiness endpoint should work in mock mode."""
    response = client.get('/readyz')

    assert response.status_code == 200
    assert 'status' in response.json


def test_pipeline_status_returns_expected_fields(client):
    """Pipeline status should return health, stages, and build info."""
    response = client.get('/api/pipeline/status')

    assert response.status_code == 200
    data = response.json

    # Check required fields exist
    assert 'health' in data
    assert 'stages' in data
    assert 'last_build' in data

    # Health should be one of the valid states
    assert data['health'] in ['healthy', 'building', 'failed']

    # Stages should be a list
    assert isinstance(data['stages'], list)


def test_systems_status_returns_jenkins_and_argocd(client):
    """Systems status should return info for both Jenkins and ArgoCD."""
    response = client.get('/api/systems/status')

    assert response.status_code == 200
    data = response.json

    assert 'jenkins' in data
    assert 'argocd' in data


def test_systems_status_includes_github_webhook(client):
    """Systems status should include GitHub webhook health."""
    response = client.get('/api/systems/status')

    assert response.status_code == 200
    data = response.json

    assert 'github_webhook' in data
    assert 'status' in data['github_webhook']


def test_pipeline_trigger_mock_mode(client):
    """Trigger endpoint should return success in mock mode."""
    response = client.post('/api/pipeline/trigger')

    assert response.status_code == 200
    data = response.json

    assert data['success'] is True
    assert 'new_version' in data


def test_pending_deployments_returns_expected_structure(client):
    """Pending deployments should return prs list and count."""
    response = client.get('/api/deployments/pending')

    assert response.status_code == 200
    data = response.json

    assert 'prs' in data
    assert 'count' in data
    assert isinstance(data['prs'], list)


def test_approve_deployment_mock_mode(client):
    """Approve deployment should return success in mock mode."""
    response = client.post('/api/deployments/approve/123')

    assert response.status_code == 200
    data = response.json

    assert data['success'] is True


def test_reject_deployment_mock_mode(client):
    """Reject deployment should return success in mock mode."""
    response = client.post('/api/deployments/reject/123')

    assert response.status_code == 200
    data = response.json

    assert data['success'] is True
