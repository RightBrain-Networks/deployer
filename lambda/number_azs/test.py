#!/usr/bin/python

import json
import urllib
import botocore.session
import boto3
from cfnresponse import send, SUCCESS,FAILED
import logging


client = boto3.client('ec2', 'us-east-1')
all = client.describe_availability_zones()
zones = [zone['ZoneName'] for zone in all['AvailabilityZones'] if zone['ZoneName'] not in all]
print len(zones)