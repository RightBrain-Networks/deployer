import yaml
import subprocess
import boto3
from boto3.session import Session


def s3_sync(release, profile):
    subprocess.call("bash s3_sync.sh -p %s -r %s" % (profile,release))
