pipeline {
  agent none

  environment {
    DOCKERHUB_USER = 'sabichon'
    IMAGE_NAME = 'ci-dashboard'
    IS_DEV = "${env.BRANCH_NAME == 'dev' ? 'true' : 'false'}"
    IMAGE_TAG = "${env.BRANCH_NAME == 'dev' ? 'dev-' : ''}${BUILD_NUMBER}"
    DEPLOY_NAMESPACE = "${env.BRANCH_NAME == 'dev' ? 'ci-dashboard-dev' : 'ci-dashboard'}"
    BASE_BRANCH = "${env.BRANCH_NAME == 'dev' ? 'dev' : 'main'}"
  }

  options {
    timeout(time: 30, unit: 'MINUTES')
    buildDiscarder(logRotator(          
      numToKeepStr: '30',
      daysToKeepStr: '30',
      artifactDaysToKeepStr: '7',
      artifactNumToKeepStr: '5'
    ))
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

    stage('Verify') {
      parallel {

        stage('Lint') {
          agent {
            kubernetes {
              label "lint-${BUILD_NUMBER}"
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
              label "secrets-scan-${BUILD_NUMBER}"
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
                for i in 1 2 3; do
                  wget -qO- https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz | tar xz -C /tmp gitleaks && break
                  sleep 5
                done
                /tmp/gitleaks detect --source . --verbose --no-git
              '''
            }
          }
        }

        stage('Test - Unit') {
          agent {
            kubernetes {
              label "test-unit-${BUILD_NUMBER}"
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
                  pytest test_services.py -v --cov=services --cov-report=term-missing --cov-fail-under=0
                '''
              }
            }
          }
        }

        stage('Test - API') {
          agent {
            kubernetes {
              label "test-api-${BUILD_NUMBER}"
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
                  pytest test_app.py -v --cov=app --cov-report=term-missing --cov-fail-under=45
                '''
              }
            }
          }
        }

      }
    }

    stage('Initiate Build and Push') {
      agent {
        kubernetes {
          label "build-${BUILD_NUMBER}"
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
              withCredentials([usernamePassword(
                credentialsId: 'dockerhub-creds',
                usernameVariable: 'DOCKER_USER',
                passwordVariable: 'DOCKER_PASS'
              )]) {
                sh '''
                  mkdir -p /root/.docker
                  AUTH=$(echo -n "$DOCKER_USER:$DOCKER_PASS" | base64 | tr -d '\n')
                  printf '{"auths":{"https://index.docker.io/v1/":{"auth":"%s"}}}' "$AUTH" > /root/.docker/config.json

                  buildctl --addr unix:///run/buildkit/buildkitd.sock build \
                    --frontend dockerfile.v0 \
                    --local context=. \
                    --local dockerfile=. \
                    --output type=docker,dest=/tmp/image.tar \
                    --import-cache type=registry,ref=docker.io/${DOCKERHUB_USER}/${IMAGE_NAME}:buildcache \
                    --export-cache type=registry,ref=docker.io/${DOCKERHUB_USER}/${IMAGE_NAME}:buildcache,mode=max
                '''
              }
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
                wget -qO /tmp/grype-install.sh https://raw.githubusercontent.com/anchore/grype/main/install.sh
                sh /tmp/grype-install.sh -b /tmp
                /tmp/grype /tmp/image.tar \
                  --fail-on high \
                  --only-fixed \
                  --config $WORKSPACE/.grype.yaml
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
              script {
                def manifest   = env.BASE_BRANCH == 'dev' ? 'k8s/app-dev/deployment.yaml' : 'k8s/app/deployment.yaml'
                def imageTag   = env.IMAGE_TAG
                def imgName    = env.IMAGE_NAME
                def dockerUser = env.DOCKERHUB_USER
                def baseBranch = env.BASE_BRANCH
                def namespace  = env.DEPLOY_NAMESPACE
                def buildNum   = env.BUILD_NUMBER

                // Update image and APP_VERSION in manifest
                sh """
                  git config user.email jenkins@ci.local
                  git config user.name 'Jenkins CI'
                  sed -i 's|image: ${dockerUser}/${imgName}:.*|image: ${dockerUser}/${imgName}:${imageTag}|' ${manifest}
                  LINE=\$(grep -n 'Jenkins will update this' ${manifest} | cut -d: -f1)
                  sed -i \"\\${LINE}s/.*/              value: \\\"${imageTag}\\\"  # Jenkins will update this/\" ${manifest}
                  git add ${manifest}
                """

                def status = sh(script: 'git diff --cached --quiet; echo $?', returnStdout: true).trim()

                if (status == '1') {
                  if (baseBranch == 'dev') {
                    sh """
                      git commit -m '[skip ci] Deploy ${imgName}:${imageTag} to ${namespace}'
                      git push https://\${GIT_USER}:\${GIT_TOKEN}@github.com/sagi-l/ci-dashboard.git HEAD:dev
                    """
                    echo 'Dev deployment pushed directly to dev branch'
                  } else {
                    def deployBranch = "deploy/main/v${imageTag}"
                    sh """
                      git checkout -b ${deployBranch}
                      git commit -m '[skip ci] Deploy ${imgName}:${imageTag} to ${namespace}'
                      git push https://\${GIT_USER}:\${GIT_TOKEN}@github.com/sagi-l/ci-dashboard.git ${deployBranch}
                      curl -s -X POST \\
                        -H 'Authorization: token '\${GIT_TOKEN} \\
                        -H 'Accept: application/vnd.github.v3+json' \\
                        https://api.github.com/repos/sagi-l/ci-dashboard/pulls \\
                        -d '{"title":"[deploy/main] ${imgName}:${imageTag}","head":"${deployBranch}","base":"main","body":"Automated deployment PR for build #${buildNum}. Approve from CI Dashboard to deploy."}'
                    """
                  }
                } else {
                  echo 'No changes to commit - manifest already up to date'
                }
              }
            }
          }
        }
      }
    }
  }

  post {
    success {
      echo "Pushed ${DOCKERHUB_USER}/${IMAGE_NAME}:${IMAGE_TAG} to ${DEPLOY_NAMESPACE} - deployment PR created, awaiting approval"
    }
    failure {
      echo 'Build or push failed'
    }
  }
}
