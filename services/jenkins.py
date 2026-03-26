import requests
from requests.auth import HTTPBasicAuth
from config import Config


class JenkinsClient:
    def __init__(self):
        self.base_url = Config.JENKINS_URL.rstrip('/')
        self.job_name = Config.JENKINS_JOB_NAME
        self.branch = Config.JENKINS_BRANCH
        self._job_path = f'{self.job_name}/job/{self.branch}' if self.branch else self.job_name
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
                f'/job/{self._job_path}/lastBuild/api/json'
            )
            data = response.json()

            # Extract branch name and commit SHA from actions (Git plugin)
            branch = None
            commit_sha = None
            for action in data.get('actions', []):
                if action.get('_class', '').endswith('BuildData'):
                    last_rev = action.get('lastBuiltRevision', {})
                    commit_sha = last_rev.get('SHA1')
                    branches = last_rev.get('branch', [])
                    if branches:
                        branch = branches[0].get('name', '').replace('origin/', '')
                        break

            return {
                'number': data.get('number'),
                'result': data.get('result'),
                'building': data.get('building', False),
                'duration': data.get('duration', 0),
                'timestamp': data.get('timestamp'),
                'url': data.get('url'),
                'branch': branch,
                'commit_sha': commit_sha
            }
        except Exception as e:
            return {'error': str(e)}

    def get_build_stages(self, build_number=None):
        """Get pipeline stages for a build using the Blue Ocean REST API."""
        try:
            if build_number is None:
                # Get last build number first
                last_build = self.get_last_build()
                if 'error' in last_build:
                    return {'stages': [], 'error': last_build['error']}
                build_number = last_build.get('number')

            # Use Blue Ocean API for pipeline stages
            if self.branch:
                blueocean_path = f'/blue/rest/organizations/jenkins/pipelines/{self.job_name}/branches/{self.branch}/runs/{build_number}/nodes/'
            else:
                blueocean_path = f'/blue/rest/organizations/jenkins/pipelines/{self.job_name}/runs/{build_number}/nodes/'
            response = self._request(blueocean_path)
            data = response.json()

            # Index all nodes by their ID for parent lookups
            # BlueOcean uses type=STAGE for regular/nested stages and type=PARALLEL for parallel branches

            # Only type=PARALLEL nodes are true parallel branches — group them under their parent
            # type=STAGE nodes with a firstParent are nested sequential stages (e.g. inside
            # "Initiate Build and Push") and should be treated as top-level for display purposes
            top_level = []
            children_by_parent = {}

            for node in data:
                if node.get('type') not in ('STAGE', 'PARALLEL'):
                    continue
                if node.get('type') == 'PARALLEL':
                    # Parallel branch — always group under its parent
                    first_parent_id = node.get('firstParent')
                    children_by_parent.setdefault(first_parent_id, []).append(node)
                else:
                    # Regular or nested STAGE — show at top level
                    top_level.append(node)

            # Build the final stage list, expanding parallel groups inline
            stages = []
            for node in top_level:
                node_id = node.get('id')
                children = children_by_parent.get(node_id)

                if children:
                    # This is a parallel group — derive its aggregate status from children
                    child_statuses = [
                        self._map_blueocean_status(c.get('result'), c.get('state'))
                        for c in children
                    ]
                    if 'running' in child_statuses:
                        group_status = 'running'
                    elif 'failed' in child_statuses:
                        group_status = 'failed'
                    elif all(s == 'success' for s in child_statuses):
                        group_status = 'success'
                    else:
                        group_status = 'pending'

                    # Total duration = longest child (they ran in parallel)
                    max_duration = max(
                        (c.get('durationInMillis', 0) or 0 for c in children),
                        default=0
                    )

                    stages.append({
                        'name': node.get('displayName'),
                        'status': group_status,
                        'duration_ms': max_duration,
                        'start_time': node.get('startTime'),
                        'parallel': [
                            {
                                'name': c.get('displayName'),
                                'status': self._map_blueocean_status(c.get('result'), c.get('state')),
                                'duration_ms': c.get('durationInMillis', 0),
                            }
                            for c in sorted(children, key=lambda c: c.get('displayName', ''))
                        ]
                    })
                else:
                    stages.append({
                        'name': node.get('displayName'),
                        'status': self._map_blueocean_status(node.get('result'), node.get('state')),
                        'duration_ms': node.get('durationInMillis', 0),
                        'start_time': node.get('startTime')
                    })

            # Sort top-level stages by start time, pending stages go last
            stages.sort(key=lambda s: (0, s['start_time']) if s.get('start_time') else (1, ''))

            # Determine overall status
            overall_status = 'SUCCESS'
            for stage in stages:
                if stage['status'] == 'running':
                    overall_status = 'IN_PROGRESS'
                    break
                elif stage['status'] == 'failed':
                    overall_status = 'FAILED'
                    break

            return {
                'stages': stages,
                'build_number': build_number,
                'status': overall_status
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

    def _map_blueocean_status(self, result, state):
        """Map Blue Ocean result/state to our status format.

        Blue Ocean uses:
        - state: RUNNING, FINISHED, QUEUED, PAUSED, SKIPPED, NOT_BUILT
        - result: SUCCESS, FAILURE, UNSTABLE, ABORTED, NOT_BUILT, UNKNOWN
        """
        if state == 'RUNNING':
            return 'running'
        elif state == 'QUEUED':
            return 'pending'
        elif state == 'SKIPPED' or state == 'NOT_BUILT':
            return 'pending'
        elif state == 'FINISHED':
            result_map = {
                'SUCCESS': 'success',
                'FAILURE': 'failed',
                'UNSTABLE': 'unstable',
                'ABORTED': 'aborted',
                'NOT_BUILT': 'pending'
            }
            return result_map.get(result, 'unknown')
        return 'unknown'

    def trigger_build(self, parameters=None):
        """Trigger a new build."""
        try:
            if parameters:
                self._request(
                    f'/job/{self._job_path}/buildWithParameters',
                    method='POST',
                    params=parameters
                )
            else:
                self._request(
                    f'/job/{self._job_path}/build',
                    method='POST'
                )
            return {'success': True, 'message': 'Build triggered successfully'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _get_last_meaningful_build(self):
        """Get the last non-aborted build info.

        When the most recent build was aborted (e.g., due to [skip ci]),
        we look at the last successful, failed, or unstable build to
        determine the actual pipeline health and show its stages.

        Returns (health, build_number) tuple.
        """
        builds = []

        for endpoint, health in [
            ('lastSuccessfulBuild', 'healthy'),
            ('lastFailedBuild', 'failed'),
            ('lastUnstableBuild', 'unstable')
        ]:
            try:
                response = self._request(f'/job/{self._job_path}/{endpoint}/api/json')
                data = response.json()
                build_number = data.get('number', 0)
                if build_number:
                    builds.append((health, build_number))
            except Exception:
                pass

        if not builds:
            return ('unknown', None)

        # Return health and build number of the most recent meaningful build
        builds.sort(key=lambda x: x[1], reverse=True)
        return builds[0]

    def get_pipeline_status(self):
        """Get overall pipeline status including health and current build."""
        last_build = self.get_last_build()

        # Determine overall health and which build to show stages for
        if 'error' in last_build:
            health = 'unknown'
            stages = self.get_build_stages()
        elif last_build.get('building'):
            health = 'building'
            stages = self.get_build_stages()
        elif last_build.get('result') == 'ABORTED':
            # Skip aborted builds (e.g., from CI loop prevention)
            # Show health and stages from last meaningful build
            health, meaningful_build_number = self._get_last_meaningful_build()
            stages = self.get_build_stages(meaningful_build_number)
        elif last_build.get('result') == 'SUCCESS':
            health = 'healthy'
            stages = self.get_build_stages()
        elif last_build.get('result') == 'FAILURE':
            health = 'failed'
            stages = self.get_build_stages()
        elif last_build.get('result') == 'UNSTABLE':
            health = 'unstable'
            stages = self.get_build_stages()
        else:
            health = 'unknown'
            stages = self.get_build_stages()

        return {
            'health': health,
            'last_build': last_build,
            'stages': stages.get('stages', []),
            'build_number': stages.get('build_number'),
            'branch': last_build.get('branch', 'main')
        }

    def get_build_history(self, limit=5):
        """Get recent build history.

        Args:
            limit: Number of recent builds to return

        Returns:
            List of build info dicts with number, result, duration, timestamp
        """
        try:
            response = self._request(
                f'/job/{self._job_path}/api/json?tree=builds[number,result,duration,timestamp,building]{{0,{limit}}}'
            )
            data = response.json()

            builds = []
            for build in data.get('builds', []):
                # Skip currently building
                if build.get('building'):
                    continue
                # Skip aborted builds
                if build.get('result') == 'ABORTED':
                    continue

                builds.append({
                    'number': build.get('number'),
                    'result': build.get('result'),
                    'duration_ms': build.get('duration', 0),
                    'timestamp': build.get('timestamp')
                })

            return builds[:limit]
        except Exception:
            return []

    def get_build_logs(self, build_number=None, start=0):
        """Get progressive console output for a build.

        Args:
            build_number: Build number to fetch logs for (default: last build)
            start: Byte offset to start reading from (for progressive loading)

        Returns:
            dict with 'text' (log content), 'next_start' (offset for next request),
            and 'has_more' (whether build is still producing output)
        """
        try:
            if build_number is None:
                last_build = self.get_last_build()
                if 'error' in last_build:
                    return {'text': '', 'next_start': 0, 'has_more': False, 'error': last_build['error']}
                build_number = last_build.get('number')

            response = self._request(
                f'/job/{self._job_path}/{build_number}/logText/progressiveText',
                params={'start': start}
            )

            text = response.text
            # X-Text-Size header contains the offset for the next request
            next_start = int(response.headers.get('X-Text-Size', start))
            # X-More-Data header indicates if more data is expected
            has_more = response.headers.get('X-More-Data', 'false').lower() == 'true'

            return {
                'text': text,
                'next_start': next_start,
                'has_more': has_more,
                'build_number': build_number
            }
        except Exception as e:
            return {'text': '', 'next_start': start, 'has_more': False, 'error': str(e)}
