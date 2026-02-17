import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Jenkins Configuration
    JENKINS_URL = os.getenv('JENKINS_URL', 'http://jenkins.jenkins.svc.cluster.local:8080')
    JENKINS_USER = os.getenv('JENKINS_USER', '')
    JENKINS_TOKEN = os.getenv('JENKINS_TOKEN', '')
    JENKINS_JOB_NAME = os.getenv('JENKINS_JOB_NAME', 'ci-pipeline')

    # ArgoCD Configuration
    ARGOCD_URL = os.getenv('ARGOCD_URL', 'https://argocd.argocd.svc.cluster.local')
    ARGOCD_TOKEN = os.getenv('ARGOCD_TOKEN', '')
    ARGOCD_APP_NAME = os.getenv('ARGOCD_APP_NAME', 'ci-dashboard')

    # Kubernetes Configuration
    K8S_NAMESPACE = os.getenv('K8S_NAMESPACE', 'web-app')

    # Mock mode for local development
    MOCK_MODE = os.getenv('MOCK_MODE', 'false').lower() == 'true'

    # GitHub Repository URLs
    GITHUB_APP_REPO = os.getenv('GITHUB_APP_REPO', 'https://github.com/sagi-l/simple_flask_app')
    GITHUB_INFRA_REPO = os.getenv('GITHUB_INFRA_REPO', 'https://github.com/sagi-l/ci-cd-platform-k8s')

    # GitHub API Token for triggering builds via version bump
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
    GITHUB_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER', 'sagi-l')
    GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME', 'ci-dashboard')
