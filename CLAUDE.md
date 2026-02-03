# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CI-Dashboard is a real-time monitoring and control dashboard for a fully automated CI/CD platform built on bare metal Kubernetes. It provides visibility into Jenkins pipeline status, ArgoCD deployment synchronization, and allows triggering new builds directly from the web interface.

## Technology Stack

- **Backend**: Python 3.12 with Flask 3.0.0, Gunicorn
- **Frontend**: Vanilla JavaScript, HTML5/Jinja2, CSS3
- **CI/CD**: Jenkins, ArgoCD, GitHub webhooks
- **Infrastructure**: Kubernetes (bare metal), Traefik ingress, Docker

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally with mock data (no cluster access needed)
MOCK_MODE=true FLASK_DEBUG=true python app.py

# Run with live cluster (requires kubeconfig and .env config)
MOCK_MODE=false python app.py

# Docker build and run
docker build -t ci-dashboard:test .
docker run -p 5000:5000 -e MOCK_MODE=true ci-dashboard:test
```

## Architecture

### Service Layer (`services/`)
Client wrappers for external systems, all following the same pattern:
- `jenkins.py` - Jenkins REST API wrapper for build status and stages
- `argocd.py` - ArgoCD application and sync status monitoring
- `kubernetes.py` - Lazy-initialized K8s client with in-cluster detection
- `github.py` - VERSION file management and semantic versioning

### API Endpoints
- `GET /` - Dashboard HTML
- `GET /healthz` - Liveness probe
- `GET /readyz` - Readiness probe (checks external services)
- `GET /api/pipeline/status` - Jenkins build status and stages
- `POST /api/pipeline/trigger` - Bump VERSION to trigger build
- `GET /api/systems/status` - Jenkins/ArgoCD health status
- `GET /api/deployment/version` - Current K8s deployment version

### Build Trigger Flow
1. POST to `/api/pipeline/trigger` bumps VERSION file via GitHub API
2. GitHub webhook triggers Jenkins build
3. Jenkins builds Docker image, pushes to registry
4. Jenkins patches `k8s/deployment.yaml` with new image tag
5. Jenkins commits with `[skip ci]` to prevent loop
6. ArgoCD detects manifest change and syncs to cluster

## Configuration

Environment variables (see `.env.example`):
- `MOCK_MODE=true` - Returns mock data without cluster access
- `FLASK_DEBUG=true` - Enable Flask debug mode
- Jenkins, ArgoCD, GitHub, and K8s connection settings

## Kubernetes Manifests (`k8s/`)

- `deployment.yaml` - Main app deployment (image tag updated by Jenkins)
- `service.yaml` - ClusterIP service
- `ingress.yaml` - Traefik ingress at `dashboard.local`
- `rbac.yaml` - Read-only ServiceAccount for pod/deployment access
- `argocd-application.yaml` - ArgoCD GitOps sync configuration

## Key Patterns

- **Mock Mode**: Use `MOCK_MODE=true` for local development without cluster
- **CI Loop Prevention**: Jenkins commits use `[skip ci]` prefix; Jenkinsfile checks and aborts early
- **Semantic Versioning**: VERSION file drives build triggers via patch bumps
- **Health Probes**: `/healthz` (liveness) and `/readyz` (readiness with dependency checks)
