import requests
import base64
from config import Config


class GitHubClient:
    def __init__(self):
        self.token = Config.GITHUB_TOKEN
        self.owner = Config.GITHUB_REPO_OWNER
        self.repo = Config.GITHUB_REPO_NAME
        self.api_base = 'https://api.github.com'

    def _request(self, endpoint, method='GET', **kwargs):
        url = f"{self.api_base}{endpoint}"
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'token {self.token}'
        headers['Accept'] = 'application/vnd.github.v3+json'

        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs
        )
        response.raise_for_status()
        return response

    def get_file_content(self, path, branch='main'):
        """Get file content and SHA from the repo."""
        response = self._request(
            f'/repos/{self.owner}/{self.repo}/contents/{path}',
            params={'ref': branch}
        )
        data = response.json()
        content = base64.b64decode(data['content']).decode('utf-8')
        return {
            'content': content.strip(),
            'sha': data['sha']
        }

    def update_file(self, path, new_content, sha, message, branch='main'):
        """Update a file in the repo."""
        encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

        self._request(
            f'/repos/{self.owner}/{self.repo}/contents/{path}',
            method='PUT',
            json={
                'message': message,
                'content': encoded_content,
                'sha': sha,
                'branch': branch
            }
        )

    def bump_version(self, branch='main'):
        """Bump the patch version in VERSION file and push."""
        # Get current version
        file_data = self.get_file_content('VERSION', branch)
        current_version = file_data['content']

        # Parse and bump version (simple semver bump)
        parts = current_version.split('.')
        if len(parts) == 3:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            new_version = f"{major}.{minor}.{patch + 1}"
        else:
            new_version = "0.0.1"

        # Update file
        self.update_file(
            'VERSION',
            new_version + '\n',
            file_data['sha'],
            f'Bump version to {new_version}',
            branch
        )

        return {
            'previous_version': current_version,
            'new_version': new_version
        }

    def get_webhooks(self):
        """Get all webhooks for the repo."""
        response = self._request(f'/repos/{self.owner}/{self.repo}/hooks')
        return response.json()

    def get_webhook_deliveries(self, hook_id, per_page=5):
        """Get recent deliveries for a webhook."""
        response = self._request(
            f'/repos/{self.owner}/{self.repo}/hooks/{hook_id}/deliveries',
            params={'per_page': per_page}
        )
        return response.json()

    def get_webhook_health(self):
        """Check if webhooks are healthy based on recent delivery status."""
        try:
            webhooks = self.get_webhooks()

            if not webhooks:
                return {
                    'status': 'warning',
                    'reachable': True,
                    'message': 'No webhooks configured',
                    'webhooks': []
                }

            webhook_statuses = []
            any_failing = False

            for hook in webhooks:
                hook_id = hook['id']
                hook_url = hook.get('config', {}).get('url', 'unknown')

                try:
                    deliveries = self.get_webhook_deliveries(hook_id, per_page=3)

                    if not deliveries:
                        webhook_statuses.append({
                            'id': hook_id,
                            'url': hook_url,
                            'status': 'unknown',
                            'message': 'No recent deliveries'
                        })
                        continue

                    # Check the most recent delivery
                    latest = deliveries[0]
                    status_code = latest.get('status_code', 0)
                    is_success = 200 <= status_code < 300

                    if not is_success:
                        any_failing = True

                    webhook_statuses.append({
                        'id': hook_id,
                        'url': hook_url,
                        'status': 'healthy' if is_success else 'failing',
                        'last_delivery': {
                            'status_code': status_code,
                            'delivered_at': latest.get('delivered_at'),
                            'event': latest.get('event')
                        }
                    })

                except Exception as e:
                    webhook_statuses.append({
                        'id': hook_id,
                        'url': hook_url,
                        'status': 'error',
                        'message': str(e)
                    })

            return {
                'status': 'failing' if any_failing else 'healthy',
                'reachable': True,
                'webhooks': webhook_statuses
            }

        except Exception as e:
            return {
                'status': 'error',
                'reachable': False,
                'message': str(e)
            }
