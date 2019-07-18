library('pipeline-library')

pipeline {
  options { timestamps() }
  agent any
  environment {
    SERVICE = 'deployer'
    GITHUB_KEY = 'Deployer'
    GITHUB_URL = 'git@github.com:RightBrain-Networks/deployer.git'
    DOCKER_REGISTRY = '356438515751.dkr.ecr.us-east-1.amazonaws.com'
  }
  stages {
    stage("Pull Versioning Image")
    {
        steps
        {
          withEcr {
            sh "docker pull ${DOCKER_REGISTRY}/auto-semver:null"
          }
        }
    }
    stage('Version') {
        agent {
            docker {
                image "${DOCKER_REGISTRY}/auto-semver:null"
            }
        }
      steps {
        // runs the automatic semver tool which will version, & tag,
        runAutoSemver()

        //Grabs current version
        script
        {
            env.VERSION = getVersion('-d')
        }
      }
      post{
        // Update Git with status of version stage.
        success {
          updateGithubCommitStatus(GITHUB_URL, 'Passed version stage', 'SUCCESS', 'Version')
        }
        failure {
          updateGithubCommitStatus(GITHUB_URL, 'Failed version stage', 'FAILURE', 'Version')
        }
      }
    }
    stage('Build') {
      steps {


        echo "Building ${env.SERVICE} docker image"

        // Docker build flags are set via the getDockerBuildFlags() shared library.
        sh "docker build ${getDockerBuildFlags()} -t ${env.DOCKER_REGISTRY}/${env.SERVICE}:${env.VERSION} ."

        sh "python setup.py sdist"
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
    stage('Ship')
    {
      steps {     
        withEcr {
            sh "docker push ${env.DOCKER_REGISTRY}/${env.SERVICE}:${env.VERSION}"
        }
        
        //Copy tar.gz file to s3 bucket
        sh "aws s3 cp dist/${env.SERVICE}-*.tar.gz s3://rbn-ops-pkg-us-east-1/${env.SERVICE}/${env.SERVICE}-${env.VERSION}.tar.gz"
        //}
      }
    }
    stage('GitHub Release')
    {
      when {
          expression {
              "${env.SEMVER_STATUS}" == "0" && "${env.BRANCH_NAME}"  == "development"
          }
      }
      steps
      {
        echo "New version deteced!"
        script
        {

          //Needs to releaseToken from Secrets Manager
          releaseToken = sh(returnStdout : true, script: "aws secretsmanager get-secret-value --secret-id deployer/gitHub/releaseKey --region us-east-1 --output text --query SecretString").trim()

          releaseId = sh(returnStdout : true, script : """
          curl -XPOST -H 'Authorization:token ${releaseToken}' --data '{"tag_name": "${env.VERSION}", "target_commitish": "development", "name": "v${env.VERSION}", "draft": false, "prerelease": false}' https://api.github.com/repos/RightBrain-Networks/deployer/releases |  jq -r ."id"
          """).trim()

          echo("Uploading artifacts...")
          sh("""
              chmod 777 dist/${env.SERVICE}-*.tar.gz
              curl -XPOST -H "Authorization:token ${releaseToken}" -H "Content-Type:application/octet-stream" --data-binary @\$(echo dist/${env.SERVICE}-*.tar.gz) https://uploads.github.com/repos/RightBrain-Networks/deployer/releases/${releaseId}/assets?name=deployer.tar.gz
        """)
        }
      }
    }
    stage('Push Version and Tag') {
        steps {
            echo "The current branch is ${env.BRANCH_NAME}."
            gitPush(env.GITHUB_KEY, env.BRANCH_NAME, true)
        }
    }
  }
  post {
    always {
      removeDockerImages()
      cleanWs()
    }
  }
}
