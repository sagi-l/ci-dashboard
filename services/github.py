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
