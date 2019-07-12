library('pipeline-library@feature/add-with-ecr')

pipeline {
  options { timestamps() }
  agent any
  environment {
    SERVICE = 'deployer'
    GITHUB_KEY = 'Deployer'
    GITHUB_URL = 'git@github.com:RightBrain-Networks/deployer.git'
    DOCKER_REGISTRY = '356438515751.dkr.ecr.us-east-1.amazonaws.com'
    SEMVER_EXIT = ""
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


        echo "Building ${env.SERVICE} docker image"

        // Docker build flags are set via the getDockerBuildFlags() shared library.
        sh "docker build ${getDockerBuildFlags()} -t ${env.DOCKER_REGISTRY}/${env.SERVICE}:${getVersion('-d')} ."

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
            sh "docker push ${env.DOCKER_REGISTRY}/${env.SERVICE}:${getVersion('-d')}"
        }
        
        //Copy tar.gz file to s3 bucket
        sh "aws s3 cp dist/${env.SERVICE}-*.tar.gz s3://rbn-ops-pkg-us-east-1/${env.SERVICE}/${env.SERVICE}-${getVersion('-d')}.tar.gz"
        //}
      }
    }
    stage('Push Version and Tag') {
        steps {
            echo "The current branch is ${env.BRANCH_NAME}."
            gitPush(env.GITHUB_KEY, env.BRANCH_NAME, true)
        }
    }
    stage('GitHub Release')
    {
      when {
          expression {
              env.SEMVER_NEW_VERSION != env.SEMVER_RESOLVED_VERSION
          }
      }
      steps
      {
        echo "New version deteced!"
        script
        {
          echo("${env.SEMVER_NEW_VERSION}")
          echo("${env.SEMVER_RESOLVED_VERSION}")


          //Needs to releaseToken from Secrets Manager
          releaseToken = sh(returnStdout : true, script: "aws secretsmanager get-secret-value --secret-id deployer/gitHub/releaseKey --region us-east-1 --output text --query SecretString").trim()

          releaseId = sh(returnStdout : true, script : """
          curl -XPOST -H 'Authorization:token ${releaseToken}' --data '{"tag_name": "${getVersion('-d')}", "target_commitish": "development", "name": "v${getVersion('-d')}", "draft": true, "prerelease": true}' https://api.github.com/repos/RightBrain-Networks/deployer/releases |  jq -r ."id"
          """).trim()

          echo("Uploading artifacts...")
          sh("""
              chmod 777 dist/${env.SERVICE}-*.tar.gz
              curl -XPOST -H "Authorization:token ${releaseToken}" -H "Content-Type:application/octet-stream" --data-binary @\$(echo dist/${env.SERVICE}-*.tar.gz) https://uploads.github.com/repos/RightBrain-Networks/deployer/releases/${releaseId}/assets?name=deployer.tar.gz
        """)
        }
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
