#!/usr/bin/env python2.7
import json
import urllib
import botocore.session
import boto3
from netaddr import IPSet, IPNetwork
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
        if(event['RequestType'] == 'Create'):
            if not validate_mask(event['ResourceProperties']['GlobalCidr'], event['ResourceProperties']['MaskBit']):
                logger.debug("Mask bit length is smaller than the mask for the VPN Cidr")
                if context:
                    send(event, context, FAILED, "Mask bit length is smaller than the mask for the VPN Cidr")
                return
            ip_network = IPNetwork(event['ResourceProperties']['GlobalCidr'])
            ipv4_addr_space = IPSet([ip_network])
            if context:
                session = boto3.session.Session()
            else:
                session = boto3.session.Session(profile_name=event['ResourceProperties']['Profile'])
            client = session.client('ec2')
            regions = get_regions(client)

            #get reserved ip cidrs
            reserved = get_reserved_vpc_cidr(session,regions)

            #define available
            available = ipv4_addr_space

            #define unavailable
            unavailable = None

            #get reserved vpc cidrs
            if reserved:
                unavailable  = IPSet(reserved)

            #merge with passed vpc cidrs
            if len(event['ResourceProperties']['Reserved']) >0:
                print "reserved"
                if str(event['ResourceProperties']['Reserved'][0]) != '':
                    unavailable =  IPSet(event['ResourceProperties']['Reserved']) | IPSet(reserved)
            if unavailable is not None:
                available = ipv4_addr_space ^ unavailable
            print available
            subnets = ip_network.subnet(int(event['ResourceProperties']['MaskBit']))
            for subnet in subnets:
                if subnet in available:
                    if context:
                        send(event, context, SUCCESS, None, None, str(subnet))
                    else:
                        print str(subnet)
                    return
            logger.debug("Unable to find available ip space")
            if context:
                send(event, context, FAILED, "Unable to find available ip space, try a bigger mask bit length")
        else:
            if context:
                send(event, context, SUCCESS)
    except Exception as e:
        logger.error(e)
        if context:
            send(event, context, FAILED, str(e))
        raise e
    return

def get_reserved_vpc_cidr(session, regions):
    vpcs = []
    for region in regions:
        client = session.client('ec2', region)
        vpc = client.describe_vpcs(Filters=[{"Name" : "isDefault", "Values" : ["false"]}])
        cidrs = [cidr['CidrBlock'] for cidr in vpc['Vpcs'] if cidr['CidrBlock'] not in vpcs]
        vpcs = vpcs + cidrs
    return vpcs

def get_regions(client):
    regions = []
    all = client.describe_regions()
    regions = [region['RegionName'] for region in all['Regions']]
    return regions

def validate_mask(cidr, mask):
    valid = False
    slash = cidr.split("/")
    if slash:
        if int(slash[1]) <= mask:
            valid = True
    return valid

def parse_list_callback(option, opt, value, parser):
  setattr(parser.values, option.dest, value.split(','))

if __name__ == "__main__":
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-b","--bitmask", help="BitMask for the VPC. Example: 22", default='22')
    parser.add_option("-g","--globalCidr", help="Global Cidr Range to usable.", default="10.0.0.0/8")
    parser.add_option("-r","--reserved", help="Reserved Range, must be in form of a comma delimited string. Example: '10.5.0.0/24,10.0.4.0/22'", type='string',action='callback',callback=parse_list_callback)
    parser.add_option("-p","--profile", help="Profile name to use when connecting to aws.", default="default")
    (opts, args) = parser.parse_args()
    opts.reserved = list(opts.reserved)
    event = { 'RequestType': 'Create', 'ResourceProperties': { 'Reserved': opts.reserved, 'GlobalCidr': opts.globalCidr, 'MaskBit': opts.bitmask, 'Profile': opts.profile } }
    lambda_handler(event, None)
