import requests
from config import Config


class ArgoCDClient:
    def __init__(self):
        self.base_url = Config.ARGOCD_URL.rstrip('/')
        self.token = Config.ARGOCD_TOKEN

    def _request(self, endpoint, method='GET', **kwargs):
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = kwargs.pop('headers', {})
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=10,
                verify=False,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise Exception(f"ArgoCD API error: {str(e)}")

    def get_health(self):
        """Check if ArgoCD is reachable."""
        try:
            # Try to get applications list as health check
            self._request('/applications')
            return {'status': 'healthy', 'reachable': True}
        except Exception as e:
            return {'status': 'unhealthy', 'reachable': False, 'error': str(e)}

    def get_application_status(self, app_name='web-app'):
        """Get the status of a specific application."""
        try:
            response = self._request(f'/applications/{app_name}')
            data = response.json()

            status = data.get('status', {})
            health = status.get('health', {})
            sync = status.get('sync', {})

            return {
                'name': app_name,
                'health_status': health.get('status', 'Unknown'),
                'sync_status': sync.get('status', 'Unknown'),
                'revision': sync.get('revision', 'Unknown')[:7] if sync.get('revision') else 'Unknown',
                'operation_state': status.get('operationState', {}).get('phase')
            }
        except Exception as e:
            return {'error': str(e)}

    def get_applications(self):
        """Get all applications."""
        try:
            response = self._request('/applications')
            data = response.json()

            apps = []
            for item in data.get('items', []):
                status = item.get('status', {})
                health = status.get('health', {})
                sync = status.get('sync', {})

                apps.append({
                    'name': item.get('metadata', {}).get('name'),
                    'health_status': health.get('status', 'Unknown'),
                    'sync_status': sync.get('status', 'Unknown')
                })

            return {'applications': apps}
        except Exception as e:
            return {'applications': [], 'error': str(e)}
