library('pipeline-library')

pipeline {
  options { timestamps() }
  agent any
  environment {
    SERVICE = 'deployer'
    GITHUB_KEY = 'Deployer'
    GITHUB_URL = 'https://github.com/RightBrain-Networks/deployer'
    DOCKER_REGISTRY = '247046769567.dkr.ecr.us-east-1.amazonaws.com'
  }
  stages {
    stage('Version') {
      steps {
        // runs the automatic semver tool which will version, & tag,
        runAutoSemver()
      }
    }
    stage('Build') {
      steps {
        withEnv(["HOME=${env.WORKSPACE}"]) {
        sh 'pip install -r requirements.txt --user'
        
        
        sh "python setup.py sdist"

        echo "Building ${env.SERVICE} docker image"
        sh "aws ecr get-login --no-include-email --region us-east-1 | sed 's|https://||'"
        // Docker build flags are set via the getDockerBuildFlags() shared library.
        sh "docker build ${getDockerBuildFlags()} -t ${env.DOCKER_REGISTRY}/${env.SERVICE}:${getVersion('-d')} ."

        //sh "tar -czvf ${env.SERVICE}-${getVersion('-d')}.tar.gz ./"
        }
      }
      post{
        // Update Git with status of build stage.
        success {
          updateGithubCommitStatus(GITHUB_URL, 'Passed build stage', 'SUCCESS', 'Build')
        }
        failure {
          updateGithubCommitStatus(GITHUB_URL, 'Failed build stage', 'FAILURE', 'Build')
        }
      }
    }
    stage('Push')
    {
      steps {
        withEnv(["HOME=${env.WORKSPACE}"]) {
        // aws ecr get-login returns a docker command you run in bash.
        //sh "aws ecr get-login --no-include-email --region us-east-1"
        
        sh "docker push ${env.DOCKER_REGISTRY}/${env.SERVICE}:${getVersion('-d')}"
        //Push docker image to registry
        
        //Copy tar.gz file to s3 bucket
        //sh "aws s3 cp ${env.SERVICE}-${getVersion('-d')}.tar.gz s3://rbn-ops-pkg-us-east-1/${env.SERVICE}/${env.SERVICE}-${getVersion('-d')}.tar.gz"
        }
      }
    }
  }
  post {
    always {
      removeDockerImages()
    }
  }
}
