#!/usr/bin/env python2.7
import json
import urllib2
import boto3
from cfnresponse import send, SUCCESS,FAILED
import logging
from optparse import OptionParser


logger = logging.getLogger()
logger.setLevel(logging.ERROR)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

def lambda_handler(event, context):
    try:
        region = event['ResourceProperties']['Region']
        if context:
            client = boto3.session.Session(region_name=region).client('ec2')
        else:
            client = boto3.session.Session(profile_name=event['ResourceProperties']['Profile'],region_name=region).client('ec2')
        zones = get_availability_zones(client,region)
        if context:
            send(event, context, SUCCESS, None, None, str(len(zones)))
        else:
            print str(len(zones))
    except Exception as e:
        logger.error(e)
        if context:
            send(event, context, FAILED, str(e))
        raise e
    return

def get_availability_zones(client,region):
    zones = []
    all = client.describe_availability_zones()
    zones = [zone['ZoneName'] for zone in all['AvailabilityZones'] if zone['ZoneName'] not in all]
    return zones

if __name__ == "__main__":
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-r","--region", help="Region in which to run.")
    parser.add_option("-p","--profile", help="Profile name to use when connecting to aws.", default="default")
    (opts, args) = parser.parse_args()
    options_broken = False
    if not opts.region:
        logger.error("Must Specify Region")
        options_broken = True
    if options_broken:
        parser.print_help()
        exit(1)

    event = { 'ResourceProperties': { 'Region': opts.region, 'Profile': opts.profile } }
    lambda_handler(event, None)
