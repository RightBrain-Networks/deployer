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

while getopts "b:n:p:e:r::" opt; do
  case $opt in
    b)  
      STRAP_BKT=$OPTARG
    ;;  
    n)  
      ROLE=$OPTARG
    ;;  
    p)  
      PROJECT=$OPTARG
    ;;  
    e)  
      ENVIRON=$OPTARG
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

## Before we convert to lowercase
EFS_NAME="${ENVIRON}-${ROLE}-EFS"

## Variables are re-exported here to ensure lowercase.
export PROJECT=${PROJECT,,}
export ENVIRON=${ENVIRON,,}
export ROLE=${ROLE,,}
export VARS=/usr/local/etc/bootstrap.vars

## These variables should rarely change.
LOG=/var/log/bootstrap.log
ID=$(curl -q http://169.254.169.254/latest/meta-data/instance-id)
HOSTNAME=${PROJECT}-${ENVIRON}-${ROLE}-${ID}
ID_DOC=$(curl -q http://169.254.169.254/latest/dynamic/instance-identity/document)

{

# Set hostname.
hostname "$HOSTNAME"
echo "New hostname is $(hostname)."

# Install utilities
yum -y install jq nfs-utils python27

REGION=$(echo $ID_DOC | jq .region | sed 's/"//g')
AZ=$(echo $ID_DOC | jq .availabilityZone | sed 's/"//g')

# Configure AWS CLI
aws configure set default.region "$REGION"
aws configure set default.s3.signature_version s3v4

# Add support for EFS to the CLI configuration
aws configure set preview.efs true

# Get EFS FileSystemID attribute - requires IAM read permissions for EFS
EFS_ID=$(aws efs describe-file-systems | jq -r ".FileSystems[] | select(.Name==\"${EFS_NAME}\") | .FileSystemId")

# Check to see if the variable is set. If not, then exit.
if [ -z "$EFS_ID" ]; then
    echo "[ERROR] EFS_ID variable not set"
    exit
fi

# Mount EFS volume - port 2049 must be open inbound/outbound
NFS=$AZ.$EFS_ID.efs.$REGION.amazonaws.com
MNT=/mnt/efs
mkdir -p $MNT
mount -t nfs4 $NFS:/ $MNT
cp -p /etc/fstab /etc/fstab.back-$(date +%F)
# Append line to fstab
echo -e "$NFS:/ \t\t $MNT \t\t nfs \t\t defaults \t\t 0 \t\t 0" | tee -a /etc/fstab

JENKINS_HOME=$MNT/jenkins_home
useradd -G docker -u 996 jenkins
mkdir -p $JENKINS_HOME
OWNER=$(ls -lah /mnt/efs/jenkins_home | head -2 | cut -d' ' -f3)
if [ $OWNER != "jenkins" ]; then
  chown jenkins -R $JENKINS_HOME
fi

# Mount Dev-WordPress-EFS
#DEV_EFS_ID=$(aws efs describe-file-systems | jq -r ".FileSystems[] | select(.Name==\"Stage-Jenkins-EFS\") | .FileSystemId")
#DEV_NFS=$AZ.$DEV_EFS_ID.efs.$REGION.amazonaws.com
#DEV_MNT=/mnt/dev-wordpress-efs
#mkdir -p $DEV_MNT
#mount -t nfs4 $DEV_NFS:/ $DEV_MNT
#echo -e "$DEV_NFS:/ \t\t $DEV_MNT \t\t nfs \t\t defaults \t\t 0 \t\t 0" | tee -a /etc/fstab

service docker restart
start ecs

echo \
"STRAP_BKT=$STRAP_BKT
ROLE=$ROLE
PROJECT=$PROJECT
ENVIRON=$ENVIRON
RELEASE=$RELEASE
REGION=$REGION
AZ=$AZ
EFS_NAME=$EFS_NAME
EFS_ID=$EFS_ID
NFS=$NFS
MNT=$MNT
DEV_EFS_ID=$EFS_ID
DEV_NFS=$NFS
DEV_MNT=$MNT" > $VARS

} | tee --append $LOG
