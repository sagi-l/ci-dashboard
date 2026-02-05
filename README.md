# CI/CD Dashboard

A real-time monitoring and control dashboard for a fully automated CI/CD platform running on bare metal Kubernetes.

<img width="1149" height="933" alt="Screenshot from 2026-02-05 09-58-41" src="https://github.com/user-attachments/assets/8db76c71-7216-4a85-a071-e5f21356d620" />


## About

This is a learning project - a fully self-hosted CI/CD platform running on a single bare metal machine with a single-node Kubernetes cluster. Yes, single-node K8s isn't great for HA - you work with what you've got.

The goal was to build everything from scratch without relying on managed services. No EKS, no GitHub Actions, no cloud magic - just a machine, Kubernetes, and figuring out how all the pieces actually connect.

The dashboard provides real-time visibility into the entire pipeline: Jenkins build status, ArgoCD sync state, and the ability to trigger new deployments with one click.

## Related

**[ci-cd-platform-k8s](https://github.com/sagi-l/ci-cd-platform-k8s)** - The infrastructure side of this project. Contains Helm charts and configuration for Jenkins, ArgoCD, and everything else that makes the platform run.

## Features

- **Real-time Pipeline Monitoring** - Watch builds progress through stages with live status updates
- **One-Click Build Trigger** - Bump version and trigger builds directly from the dashboard
- **System Health Signals** - Monitor Jenkins, ArgoCD, and sync status at a glance
- **Webhook Health Check** - Prevents triggering builds when the webhook path is down
- **Build History** - Track recent builds with duration and status
- **GitOps Deployment** - ArgoCD automatically syncs changes to the cluster

## Build Trigger Flow

1. **Trigger** - Click "Trigger Build" → bumps `VERSION` file via GitHub API
2. **Webhook** - GitHub sends webhook to Jenkins (via Cloudflare tunnel)
3. **Build** - Jenkins spins up ephemeral BuildKit pod, builds container image
4. **Push** - Image pushed to container registry with version tag
5. **Update** - Jenkins patches `k8s/deployment.yaml` with new image tag
6. **Commit** - Jenkins commits with `[skip ci]` to prevent infinite loop
7. **Sync** - ArgoCD detects manifest change and syncs to cluster
8. **Deploy** - New version rolling out on Kubernetes

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.12, Flask 3.0 |
| **Frontend** | Vanilla JS, HTML5, CSS3 |
| **CI Server** | Jenkins (on K8s with ephemeral agents) |
| **GitOps** | ArgoCD |
| **Image Builder** | BuildKit (ephemeral pods) |
| **Orchestration** | Kubernetes (bare metal) |
| **Ingress** | Traefik |
| **Tunnel** | Cloudflare Tunnel |

## Quick Start

### Local Development (Mock Mode)

```bash
# Install dependencies
pip install -r requirements.txt

# Run with mock data (no cluster needed)
MOCK_MODE=true FLASK_DEBUG=true python app.py

# Open http://localhost:5000
```

### Container (Local Testing)

```bash
# Build and run the dashboard container locally
docker build -t ci-dashboard:test .
docker run -p 5000:5000 -e MOCK_MODE=true ci-dashboard:test
```

### Production (Kubernetes)

The dashboard is designed to run inside the cluster with proper RBAC:

```bash
# Apply manifests
kubectl apply -f k8s/

# Or let ArgoCD manage it
kubectl apply -f k8s/argocd-application.yaml
```

## Configuration

Create a `.env` file based on `.env.example`:

```bash
# Mock mode for local development
MOCK_MODE=false

# Jenkins
JENKINS_URL=http://jenkins.jenkins.svc.cluster.local:8080
JENKINS_USER=admin
JENKINS_TOKEN=your-token
JENKINS_JOB_NAME=ci-dashboard

# ArgoCD
ARGOCD_URL=https://argocd.argocd.svc.cluster.local
ARGOCD_TOKEN=your-token
ARGOCD_APP_NAME=ci-dashboard

# GitHub (for build triggers)
GITHUB_TOKEN=your-token
GITHUB_REPO_OWNER=your-username
GITHUB_REPO_NAME=ci-dashboard

# Kubernetes
K8S_NAMESPACE=web-app
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe (checks dependencies) |
| `/api/pipeline/status` | GET | Current build status and stages |
| `/api/pipeline/trigger` | POST | Trigger new build |
| `/api/pipeline/history` | GET | Recent build history |
| `/api/pipeline/logs` | GET | Progressive build logs |
| `/api/systems/status` | GET | Jenkins, ArgoCD, webhook health |
| `/api/deployment/version` | GET | Current deployed version |

## Hard Problems Solved

- **Jenkins K8s Plugin** - Pod templates silently fail with wrong YAML structure
- **Duplicate Kubernetes Clouds** - Helm injected default cloud conflicting with JCasC
- **WebSocket vs TCP Agents** - Protocol mismatch causing connection failures
- **Webhook Loop Prevention** - `[skip ci]` commits with fast abort before spinning up K8s pods
- **Webhook Health Monitoring** - Check GitHub delivery status before allowing triggers

## Project Structure

```
ci-dashboard/
├── app.py                 # Flask application
├── config.py              # Configuration management
├── services/
│   ├── jenkins.py         # Jenkins API client
│   ├── argocd.py          # ArgoCD API client
│   ├── kubernetes.py      # K8s client (lazy init)
│   └── github.py          # GitHub API (version bumping)
├── templates/
│   └── index.html         # Dashboard template
├── static/
│   ├── css/style.css      # Styles
│   └── js/dashboard.js    # Frontend logic
├── k8s/
│   ├── deployment.yaml    # App deployment
│   ├── service.yaml       # ClusterIP service
│   ├── ingress.yaml       # Traefik ingress
│   ├── rbac.yaml          # ServiceAccount & roles
│   └── argocd-application.yaml
├── Jenkinsfile            # Pipeline definition
├── Dockerfile             # Container build
└── requirements.txt       # Python dependencies
```

## License

MIT
