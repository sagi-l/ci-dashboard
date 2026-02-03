# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About

A fully automated CI/CD platform on bare metal Kubernetes. Cloud credits ran out, but the constraints forced deeper learning - when you can't throw money at managed services, you actually understand what's running.

This dashboard (Python Flask + vanilla JS) provides real-time monitoring of the pipeline.

## Infrastructure

- Jenkins on K8s with ephemeral BuildKit agents (spin up per build, auto-terminate)
- ArgoCD for GitOps - git push triggers automatic deployment
- All credentials managed via Kubernetes Secrets
- Self-healing through K8s with proper namespace isolation
- Jenkins fully governed by Helm + JCasC - plugins, jobs, cloud config, everything is version controlled. Lose the pod? Helm redeploys identical state.

## Hard Problems Solved

- **Jenkins K8s plugin strictness** - pod templates silently fail with wrong YAML structure, inheritFrom falls back to empty templates without warning
- **Duplicate Kubernetes clouds** - Helm injected a default cloud that conflicted with JCasC config, causing non-deterministic agent failures
- **WebSocket vs TCP agent mismatch** - agents failing to connect until protocol was aligned
- **BuildKit running privileged** (rootless deferred) - made deliberate tradeoff to prioritize delivery over security hardening in phase 1
- **Webhook loop prevention** - Jenkins commits triggering infinite builds, solved with fast abort on controller before spinning up K8s pods

## Common Commands

```bash
# Local development (mock mode - no external dependencies needed)
export MOCK_MODE=true FLASK_DEBUG=true
python app.py

# Production server
gunicorn --bind 0.0.0.0:5000 --workers 2 app:app

# Docker build and run
docker build -t ci-dashboard:1 .
docker run -p 5000:5000 -e MOCK_MODE=true ci-dashboard:1

# Kubernetes deployment
kubectl apply -f k8s/

# Health check endpoints
curl http://localhost:5000/healthz   # Liveness probe
curl http://localhost:5000/readyz    # Readiness probe
```

## Architecture

```
Frontend (Browser)                    Flask Backend (app.py)
┌─────────────────────┐              ┌──────────────────────┐
│ templates/index.html│◄────────────►│ Routes:              │
│ static/css/style.css│   Polling    │  /api/pipeline/*     │
│ static/js/dashboard │   (3-30s)    │  /api/systems/*      │
└─────────────────────┘              │  /api/deployment/*   │
                                     └──────────┬───────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    ▼                           ▼                           ▼
            services/jenkins.py         services/argocd.py         services/kubernetes.py
            services/github.py          (Build trigger)            (Redis, deployment info)
```

### Service Clients (`services/`)

- **jenkins.py** - Pipeline status, build stages, health via Jenkins REST API + wfapi
- **argocd.py** - Application sync/health status via ArgoCD REST API
- **kubernetes.py** - Redis pod status, deployment versions (lazy-initialized)
- **github.py** - Triggers builds by bumping VERSION file via GitHub API

### Frontend Polling (`static/js/dashboard.js`)

- Pipeline status: every 3 seconds
- System status: every 10 seconds
- Deployment version: every 30 seconds

### Mock Mode

Set `MOCK_MODE=true` for local development without external service access. The backend returns realistic mock data for all endpoints.

## Key Files

- **app.py** - Main Flask application with all routes and mock data generation
- **config.py** - Environment-based configuration (Jenkins, ArgoCD, K8s, GitHub settings)
- **Jenkinsfile** - CI/CD pipeline: builds Docker image, pushes to DockerHub, updates K8s manifest
- **k8s/** - Kubernetes manifests (deployment, service, ingress, RBAC, namespace)

## Environment Configuration

Copy `.env.example` to `.env` for local development. Required variables for production:
- Jenkins: `JENKINS_URL`, `JENKINS_USER`, `JENKINS_TOKEN`, `JENKINS_JOB`
- ArgoCD: `ARGOCD_URL`, `ARGOCD_TOKEN`, `ARGOCD_APP_NAME`
- GitHub: `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_VERSION_PATH`
- Kubernetes: Uses in-cluster config or kubeconfig automatically

## Jenkins Pipeline Notes

The Jenkinsfile includes loop prevention:
- Aborts if commit author is "Jenkins CI"
- Aborts if commit message contains "[skip ci]"

Image tags use `BUILD_NUMBER` and auto-update `k8s/deployment.yaml`.
