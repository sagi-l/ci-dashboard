import pytest
from unittest.mock import patch, MagicMock
from services.jenkins import JenkinsClient
from services.github import GitHubClient


# ============== Jenkins Tests ==============

@pytest.fixture
def jenkins():
    """Create a JenkinsClient for testing."""
    return JenkinsClient()


@patch('services.jenkins.requests.request')
def test_jenkins_get_last_build_parses_branch_and_sha(mock_request, jenkins):
    """get_last_build should extract branch and commit_sha from BuildData action."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'number': 10,
        'result': 'SUCCESS',
        'building': False,
        'duration': 30000,
        'timestamp': 1700000000000,
        'url': 'http://jenkins/job/test/10/',
        'actions': [
            {'_class': 'hudson.plugins.git.util.BuildData',
             'lastBuiltRevision': {
                 'SHA1': 'abc123def456',
                 'branch': [{'name': 'origin/main'}]
             }}
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_request.return_value = mock_response

    result = jenkins.get_last_build()

    assert result['branch'] == 'main'
    assert result['commit_sha'] == 'abc123def456'
    assert result['number'] == 10
    assert result['result'] == 'SUCCESS'


@patch('services.jenkins.requests.request')
def test_jenkins_get_last_build_handles_missing_revision(mock_request, jenkins):
    """get_last_build should return None for branch/sha when no revision data."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'number': 11,
        'result': 'SUCCESS',
        'building': False,
        'duration': 20000,
        'timestamp': 1700000000000,
        'url': 'http://jenkins/job/test/11/',
        'actions': [{'_class': 'some.other.Action'}]
    }
    mock_response.raise_for_status = MagicMock()
    mock_request.return_value = mock_response

    result = jenkins.get_last_build()

    assert result['branch'] is None
    assert result['commit_sha'] is None
    assert result['number'] == 11


@patch('services.jenkins.requests.request')
def test_jenkins_get_last_build_handles_error(mock_request, jenkins):
    """get_last_build should return an error dict on request failure."""
    from requests.exceptions import ConnectionError
    mock_request.side_effect = ConnectionError('Connection refused')

    result = jenkins.get_last_build()

    assert 'error' in result


def test_jenkins_blueocean_status_mapping(jenkins):
    """_map_blueocean_status should map state/result combos correctly."""
    assert jenkins._map_blueocean_status(None, 'RUNNING') == 'running'
    assert jenkins._map_blueocean_status(None, 'QUEUED') == 'pending'
    assert jenkins._map_blueocean_status(None, 'SKIPPED') == 'pending'
    assert jenkins._map_blueocean_status(None, 'NOT_BUILT') == 'pending'
    assert jenkins._map_blueocean_status('SUCCESS', 'FINISHED') == 'success'
    assert jenkins._map_blueocean_status('FAILURE', 'FINISHED') == 'failed'
    assert jenkins._map_blueocean_status('UNSTABLE', 'FINISHED') == 'unstable'
    assert jenkins._map_blueocean_status('ABORTED', 'FINISHED') == 'aborted'
    assert jenkins._map_blueocean_status('NOT_BUILT', 'FINISHED') == 'pending'
    assert jenkins._map_blueocean_status(None, 'WEIRD_STATE') == 'unknown'


# ============== GitHub Tests ==============

@pytest.fixture
def github():
    """Create a GitHubClient for testing."""
    return GitHubClient()


@patch.object(GitHubClient, 'get_file_content')
@patch.object(GitHubClient, 'update_file')
def test_github_bump_version_increments_patch(mock_update, mock_get, github):
    """bump_version should increment the patch version."""
    mock_get.return_value = {'content': '0.1.5', 'sha': 'abc123'}

    result = github.bump_version()

    assert result['previous_version'] == '0.1.5'
    assert result['new_version'] == '0.1.6'
    mock_update.assert_called_once()


@patch.object(GitHubClient, 'get_file_content')
@patch.object(GitHubClient, 'update_file')
def test_github_bump_version_handles_invalid_format(mock_update, mock_get, github):
    """bump_version should fall back to 0.0.1 for non-semver input."""
    mock_get.return_value = {'content': 'not-a-version', 'sha': 'abc123'}

    result = github.bump_version()

    assert result['new_version'] == '0.0.1'


def test_github_extract_version_from_title(github):
    """_extract_version_from_title should parse version from deploy PR title."""
    assert github._extract_version_from_title('[deploy] ci-dashboard:85') == '85'
    assert github._extract_version_from_title('[deploy] ci-dashboard:1.2.3') == '1.2.3'
    assert github._extract_version_from_title('no colon here') == 'unknown'
