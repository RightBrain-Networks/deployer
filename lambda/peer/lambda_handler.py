#!/usr/bin/env python2.7
import json
import boto3
import urllib2
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
        group = event['ResourceProperties']['Environment']
        if context:
            client = boto3.session.Session(region_name=region).client('ec2')
        else:
            client = boto3.session.Session(profile_name=event['ResourceProperties']['Profile'],region_name=region).client('ec2')
        peer = get_peer_vpc(client, region, group)
        tables = get_route_tables(client, region, str(peer['VpcId']), group)
        for table in tables['RouteTables']:
            for tag in table['Tags']:
                if tag['Key'] == 'Name':
                    names  =  tag['Value'].split("-")
                    #names = tag['Value'].replace(event['ResourceProperties']['Environment']+"-","")
                    peer[names[-1]] = table['RouteTableId']
        if 'PrivateRouteTableAz3' not in peer:
            peer['PrivateRouteTableAz3'] = ''
        if 'PrivateRouteTableAz4' not in peer:
            peer['PrivateRouteTableAz4'] = ''
        nacls = get_nacls(client, region, str(peer['VpcId']), group)
        entries = []
        for acl in nacls['NetworkAcls']:
            entries = entries + acl['Entries']
            for tag in acl['Tags']:
                if tag['Key'] == 'Name':
                    acl_name = tag['Value'].replace(event['ResourceProperties']['Environment']+"-","") + 'Nacl'
                    peer[acl_name] = acl['NetworkAclId']
        rule_numbers = list(map((lambda x: x['RuleNumber']),entries))
        open_numbers = list(set(range(200,1000)) - set(rule_numbers))
        peer['OpenRuleNumber'] = str(open_numbers[0])
        if context:
            send(event, context, SUCCESS, None, peer, str(peer['VpcId']))
        else:
            print peer
    except Exception as e:
        logger.error(e)
        if context:
            send(event, context, FAILED, str(e))
        raise e
    return

def get_peer_vpc(client, region, group):
    vpcs = client.describe_vpcs(Filters=[{ 'Name':'tag:Environment', 'Values':[group]}])['Vpcs']
    if vpcs:
        vpcId = vpcs[0]['VpcId']
        vpcCidr = vpcs[0]['CidrBlock']
    else:
        vpcId = ""
        vpcCidr = ""
    return {'VpcId': vpcId, 'VpcCidr': vpcCidr}

def get_route_tables(client, region, vpc_id, group):
    tables = client.describe_route_tables(Filters=[{ 'Name':'vpc-id', 'Values':[vpc_id]}, { 'Name':'tag:Environment', 'Values':[group]}])
    return tables

def get_nacls(client, region, vpc_id, group):
    client = boto3.client('ec2', region)
    nacls = client.describe_network_acls(Filters=[{ 'Name':'vpc-id', 'Values':[vpc_id]}, { 'Name':'tag:Environment', 'Values':[group]}])
    return nacls

if __name__ == "__main__":
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-r","--region", help="Region in which to run.")
    parser.add_option("-g","--group", help="Environment Name to peer with.", default="Infrastructure")
    parser.add_option("-p","--profile", help="Profile name to use when connecting to aws.", default="default")
    (opts, args) = parser.parse_args()

    options_broken = False
    if not opts.region:
        logger.error("Must Specify Region")
        options_broken = True
    if options_broken:
        parser.print_help()
        exit(1) 

    event = { 'ResourceProperties': { 'Environment': opts.group, 'Region': opts.region, 'Profile': opts.profile } }
    lambda_handler(event, None)
