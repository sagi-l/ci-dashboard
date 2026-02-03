import requests
from requests.auth import HTTPBasicAuth
from config import Config


class JenkinsClient:
    def __init__(self):
        self.base_url = Config.JENKINS_URL.rstrip('/')
        self.job_name = Config.JENKINS_JOB_NAME
        self.auth = None
        if Config.JENKINS_USER and Config.JENKINS_TOKEN:
            self.auth = HTTPBasicAuth(Config.JENKINS_USER, Config.JENKINS_TOKEN)

    def _request(self, endpoint, method='GET', **kwargs):
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(
                method,
                url,
                auth=self.auth,
                timeout=10,
                verify=False,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise Exception(f"Jenkins API error: {str(e)}")

    def get_health(self):
        """Check if Jenkins is reachable."""
        try:
            self._request('/api/json')
            return {'status': 'healthy', 'reachable': True}
        except Exception as e:
            return {'status': 'unhealthy', 'reachable': False, 'error': str(e)}

    def get_last_build(self):
        """Get the last build information."""
        try:
            response = self._request(
                f'/job/{self.job_name}/lastBuild/api/json'
            )
            data = response.json()
            return {
                'number': data.get('number'),
                'result': data.get('result'),
                'building': data.get('building', False),
                'duration': data.get('duration', 0),
                'timestamp': data.get('timestamp'),
                'url': data.get('url')
            }
        except Exception as e:
            return {'error': str(e)}

    def get_build_stages(self, build_number=None):
        """Get pipeline stages for a build using the Pipeline Stage View API."""
        try:
            if build_number is None:
                # Get last build number first
                last_build = self.get_last_build()
                if 'error' in last_build:
                    return {'stages': [], 'error': last_build['error']}
                build_number = last_build.get('number')

            # Use wfapi for pipeline stages
            response = self._request(
                f'/job/{self.job_name}/{build_number}/wfapi/describe'
            )
            data = response.json()

            stages = []
            for stage in data.get('stages', []):
                stages.append({
                    'name': stage.get('name'),
                    'status': self._map_stage_status(stage.get('status')),
                    'duration_ms': stage.get('durationMillis', 0),
                    'start_time': stage.get('startTimeMillis')
                })

            return {
                'stages': stages,
                'build_number': build_number,
                'status': data.get('status')
            }
        except Exception as e:
            return {'stages': [], 'error': str(e)}

    def _map_stage_status(self, status):
        """Map Jenkins stage status to our status format."""
        status_map = {
            'SUCCESS': 'success',
            'FAILED': 'failed',
            'IN_PROGRESS': 'running',
            'NOT_EXECUTED': 'pending',
            'ABORTED': 'aborted',
            'UNSTABLE': 'unstable'
        }
        return status_map.get(status, 'unknown')

    def trigger_build(self, parameters=None):
        """Trigger a new build."""
        try:
            if parameters:
                self._request(
                    f'/job/{self.job_name}/buildWithParameters',
                    method='POST',
                    params=parameters
                )
            else:
                self._request(
                    f'/job/{self.job_name}/build',
                    method='POST'
                )
            return {'success': True, 'message': 'Build triggered successfully'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _get_last_meaningful_health(self):
        """Get health from the last non-aborted build.

        When the most recent build was aborted (e.g., due to [skip ci]),
        we look at the last successful, failed, or unstable build to
        determine the actual pipeline health.
        """
        builds = []

        for endpoint, health in [
            ('lastSuccessfulBuild', 'healthy'),
            ('lastFailedBuild', 'failed'),
            ('lastUnstableBuild', 'unstable')
        ]:
            try:
                response = self._request(f'/job/{self.job_name}/{endpoint}/api/json')
                data = response.json()
                build_number = data.get('number', 0)
                if build_number:
                    builds.append((health, build_number))
            except Exception:
                pass

        if not builds:
            return 'unknown'

        # Return health of the build with highest number (most recent)
        builds.sort(key=lambda x: x[1], reverse=True)
        return builds[0][0]

    def get_pipeline_status(self):
        """Get overall pipeline status including health and current build."""
        last_build = self.get_last_build()
        stages = self.get_build_stages()

        # Determine overall health
        if 'error' in last_build:
            health = 'unknown'
        elif last_build.get('building'):
            health = 'building'
        elif last_build.get('result') == 'ABORTED':
            # Skip aborted builds (e.g., from CI loop prevention)
            health = self._get_last_meaningful_health()
        elif last_build.get('result') == 'SUCCESS':
            health = 'healthy'
        elif last_build.get('result') == 'FAILURE':
            health = 'failed'
        elif last_build.get('result') == 'UNSTABLE':
            health = 'unstable'
        else:
            health = 'unknown'

        return {
            'health': health,
            'last_build': last_build,
            'stages': stages.get('stages', []),
            'build_number': stages.get('build_number')
        }
