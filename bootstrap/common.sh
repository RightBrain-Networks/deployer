#!/usr/bin/env bash

set -e
# Set variables

function usage()
{
  echo "ERROR: Incorrect arguments provided."
  echo "Usage: $0 {args}"
  echo "Where valid args are: "
  echo "  -b <bootstrap_bucket> bucket and prefix to pull files from."
  echo "  -p <project name> (REQUIRED) -- Name of the project"
  echo "  -e <environment> (REQUIRED) Environment name"
  echo "  -r <release> (REQUIRED) release name"
  echo "  -n <instanceRole> (REQUIRED) Chef Role"
  exit 1
}

# Parse args
if [[ "$#" -lt 4 ]] ; then
  usage
fi

while getopts "b:n:p:e:r:" opt; do
  case $opt in
    b)
      BOOTSTRAP_BUCKET=$OPTARG
    ;;
    n)
      INSTANCE_ROLE=$OPTARG
    ;;
    p)
      PROJECT=$OPTARG
    ;;
    e)
      ENVIRONMENT=$OPTARG
    ;;
    r)
      RELEASE=$OPTARG
    ;;
    \?)
      echo "Invalid option: -$OPTARG"
      usage
    ;;
  esac
done

## Variables are re-exported here to ensure lowercase.
export PROJECT=${PROJECT,,}
export VARS=/usr/local/etc/vars


# Install utilities
yum -y install jq

## These variables should rarely change.
LOG=/var/log/bootstrap.log
ID=$(curl -q http://169.254.169.254/latest/meta-data/instance-id)
HOSTNAME=${PROJECT}-${ENVIRONMENT}-${ROLE}-${ID}
ID_DOC=$(curl -q http://169.254.169.254/latest/dynamic/instance-identity/document)
REGION=$(echo $ID_DOC | jq .region | sed 's/"//g')
AZ=$(echo $ID_DOC | jq .availabilityZone | sed 's/"//g')

{

# Set hostname.
hostname "$HOSTNAME"
echo "New hostname is $(hostname)."

# Configure AWS CLI
aws configure set default.region "$REGION"
aws configure set default.s3.signature_version s3v4
#Add support for EFS to the CLI configuration
aws configure set preview.efs true

# EFS Setup
if ! rpm -qa | grep -qw nfs-utils; then
    yum -y install nfs-utils
fi
if ! rpm -qa | grep -qw python27; then
	yum -y install python27
fi

service docker restart

start ecs

} | tee --append $LOG
