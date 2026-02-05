pipeline {
  agent none

  environment {
    DOCKERHUB_USER = 'sabichon'
    IMAGE_NAME = 'ci-dashboard'
    IMAGE_TAG = "${BUILD_NUMBER}"
  }

  options {
    timeout(time: 30, unit: 'MINUTES')
  }

  stages {
    stage('Check Trigger') {
      agent { label 'built-in' }
      steps {
        checkout scm
        script {
          def lastCommitAuthor = sh(script: 'git log -1 --pretty=%an', returnStdout: true).trim()
          def lastCommitMsg = sh(script: 'git log -1 --pretty=%s', returnStdout: true).trim()
          echo "Last commit by: ${lastCommitAuthor}"
          echo "Last commit message: ${lastCommitMsg}"

          if (lastCommitAuthor == 'Jenkins CI' || lastCommitMsg.contains('[skip ci]')) {
            currentBuild.result = 'ABORTED'
            error('Skipping build triggered by Jenkins commit')
          }
        }
      }
    }

    stage('Lint') {
      agent {
        kubernetes {
          cloud 'kubernetes'
          yaml '''
            apiVersion: v1
            kind: Pod
            spec:
              containers:
              - name: python
                image: python:3.14-slim
                command: ['sleep', 'infinity']
          '''
        }
      }
      steps {
        container('python') {
          sh '''
            pip install flake8 --quiet
            flake8 . --max-line-length=120 --exclude=venv,.git
          '''
        }
      }
    }

    stage('Secrets Scan') {
      agent {
        kubernetes {
          cloud 'kubernetes'
          yaml '''
            apiVersion: v1
            kind: Pod
            spec:
              containers:
              - name: gitleaks
                image: alpine:3.19
                command: ['sleep', 'infinity']
          '''
        }
      }
      steps {
        container('gitleaks') {
          sh '''
            # Download gitleaks
            wget -qO- https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz | tar xz -C /tmp gitleaks

            # Scan for secrets (API keys, passwords, tokens, etc.)
            /tmp/gitleaks detect --source . --verbose --no-git
          '''
        }
      }
    }

    stage('Test') {
      agent {
        kubernetes {
          cloud 'kubernetes'
          yaml '''
            apiVersion: v1
            kind: Pod
            spec:
              containers:
              - name: python
                image: python:3.14-slim
                command: ['sleep', 'infinity']
          '''
        }
      }
      steps {
        container('python') {
          withEnv(['MOCK_MODE=true']) {
            sh '''
              pip install -r requirements.txt --quiet
              pip install pytest pytest-cov --quiet

              # Run tests with coverage - fail if below 60%
              pytest -v --cov=. --cov-report=term-missing --cov-fail-under=60
            '''
          }
        }
      }
    }

    stage('Build and Push') {
      agent {
        kubernetes {
          cloud 'kubernetes'
          inheritFrom 'buildkit-agent'
          namespace 'jenkins-agents'
          defaultContainer 'jnlp'
        }
      }
      stages {
        stage('Verify BuildKit') {
          steps {
            container('buildctl') {
              sh 'buildctl --addr unix:///run/buildkit/buildkitd.sock debug workers'
            }
          }
        }

        stage('Build Image') {
          steps {
            container('buildctl') {
              sh '''
                buildctl --addr unix:///run/buildkit/buildkitd.sock build \
                  --frontend dockerfile.v0 \
                  --local context=. \
                  --local dockerfile=. \
                  --output type=docker,dest=/tmp/image.tar
              '''
            }
          }
        }

        stage('Security Scan') {
          options {
            timeout(time: 4, unit: 'MINUTES')
          }
          steps {
            container('buildctl') {
              sh '''
                # Download and install Grype (faster than Trivy)
                wget -qO- https://github.com/anchore/grype/releases/download/v0.74.0/grype_0.74.0_linux_amd64.tar.gz | tar xz -C /tmp grype

                # Scan the image tarball
                # --fail-on high = fail if HIGH or CRITICAL found
                # --only-fixed = ignore vulnerabilities with no fix
                /tmp/grype /tmp/image.tar \
                  --fail-on high \
                  --only-fixed
              '''
            }
          }
        }

        stage('Push Image') {
          steps {
            container('buildctl') {
              withCredentials([usernamePassword(
                credentialsId: 'dockerhub-creds',
                usernameVariable: 'DOCKER_USER',
                passwordVariable: 'DOCKER_PASS'
              )]) {
                sh '''
                  wget -qO- https://github.com/google/go-containerregistry/releases/download/v0.20.0/go-containerregistry_Linux_x86_64.tar.gz | tar xz -C /tmp crane

                  echo "$DOCKER_PASS" | /tmp/crane auth login index.docker.io -u "$DOCKER_USER" --password-stdin
                  /tmp/crane push /tmp/image.tar docker.io/${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG}
                '''
              }
            }
          }
        }

        stage('Update K8s Manifest') {
          steps {
            withCredentials([usernamePassword(
              credentialsId: 'github-creds',
              usernameVariable: 'GIT_USER',
              passwordVariable: 'GIT_TOKEN'
            )]) {
              sh '''
                git config user.email "jenkins@ci.local"
                git config user.name "Jenkins CI"

                sed -i "s|image: ${DOCKERHUB_USER}/${IMAGE_NAME}:.*|image: ${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG}|" k8s/deployment.yaml

                sed -i "s|value: \\".*\\"  # Jenkins will update this|value: \\"${IMAGE_TAG}\\"  # Jenkins will update this|" k8s/deployment.yaml

                git add k8s/deployment.yaml

                # Only create PR if there are changes
                if git diff --cached --quiet; then
                  echo "No changes to commit - manifest already up to date"
                else
                  # Create deploy branch and push
                  BRANCH_NAME="deploy/v${IMAGE_TAG}"
                  git checkout -b ${BRANCH_NAME}
                  git commit -m "[skip ci] Deploy ${IMAGE_NAME}:${IMAGE_TAG}"
                  git push https://${GIT_USER}:${GIT_TOKEN}@github.com/sagi-l/ci-dashboard.git ${BRANCH_NAME}

                  # Create PR using GitHub API
                  curl -X POST \
                    -H "Authorization: token ${GIT_TOKEN}" \
                    -H "Accept: application/vnd.github.v3+json" \
                    https://api.github.com/repos/sagi-l/ci-dashboard/pulls \
                    -d "{
                      \\"title\\": \\"[deploy] ${IMAGE_NAME}:${IMAGE_TAG}\\",
                      \\"head\\": \\"${BRANCH_NAME}\\",
                      \\"base\\": \\"main\\",
                      \\"body\\": \\"Automated deployment PR for version ${IMAGE_TAG}\\n\\nThis PR was created by Jenkins build #${BUILD_NUMBER}.\\n\\nApprove this PR from the CI Dashboard to deploy.\\"
                    }"
                fi
              '''
            }
          }
        }
      }
    }
  }

  post {
    success {
      echo "Pushed ${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG} - deployment PR created, awaiting approval"
    }
    failure {
      echo 'Build or push failed'
    }
  }
}
