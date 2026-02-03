from kubernetes import client, config as k8s_config
from config import Config


class KubernetesClient:
    def __init__(self):
        self.namespace = Config.K8S_NAMESPACE
        self._initialized = False
        self._init_error = None

    def _init_client(self):
        """Initialize Kubernetes client lazily."""
        if self._initialized:
            return self._init_error is None

        try:
            # Try in-cluster config first (when running inside K8s)
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                # Fall back to kubeconfig
                k8s_config.load_kube_config()

            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            self._initialized = True
            return False

    def get_redis_status(self):
        """Get Redis pod status in the web-app namespace."""
        if not self._init_client():
            return {'status': 'unknown', 'error': self._init_error}

        try:
            pods = self.v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector='app=redis'
            )

            if not pods.items:
                return {'status': 'not_found', 'message': 'No Redis pods found'}

            pod = pods.items[0]
            phase = pod.status.phase

            # Check container statuses
            ready = False
            if pod.status.container_statuses:
                ready = all(c.ready for c in pod.status.container_statuses)

            status = 'healthy' if phase == 'Running' and ready else 'unhealthy'

            return {
                'status': status,
                'phase': phase,
                'ready': ready,
                'pod_name': pod.metadata.name
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    def get_deployment_version(self, deployment_name='ci-dashboard'):
        """Get the current deployed image version."""
        if not self._init_client():
            return {'version': 'unknown', 'error': self._init_error}

        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace
            )

            # Get the image tag from the first container
            containers = deployment.spec.template.spec.containers
            if containers:
                image = containers[0].image
                # Extract tag from image (e.g., "myimage:v1.2.3" -> "v1.2.3")
                if ':' in image:
                    version = image.split(':')[-1]
                else:
                    version = 'latest'

                return {
                    'version': version,
                    'image': image,
                    'deployment': deployment_name,
                    'replicas': deployment.status.ready_replicas or 0,
                    'desired_replicas': deployment.spec.replicas or 1
                }

            return {'version': 'unknown', 'error': 'No containers found'}
        except Exception as e:
            return {'version': 'unknown', 'error': str(e)}

    def get_health(self):
        """Check if Kubernetes API is reachable."""
        if not self._init_client():
            return {'status': 'unhealthy', 'reachable': False, 'error': self._init_error}

        try:
            # Simple API health check
            self.v1.list_namespace(limit=1)
            return {'status': 'healthy', 'reachable': True}
        except Exception as e:
            return {'status': 'unhealthy', 'reachable': False, 'error': str(e)}
