#!/usr/bin/env python2.7
import json
import urllib
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
        cidr = event['ResourceProperties']['VpcCidr']
        ip_network = IPNetwork(cidr)
        mask = cidr.split("/")
        slash = int(mask[1])+3
        subnets = ip_network.subnet(slash)
        half = len(list(subnets))/2
        result = {}
        count = 1
        for subnet in ip_network.subnet(slash):
            if int(count) <= int(half):
                key = "PublicSubnetAz" + str(count)
                result[key] = str(subnet)
            else:
                key = "PrivateSubnetAz" + str(count-half)
                result[key] = str(subnet)
            count= count + 1
        if context:
            send(event, context, SUCCESS, None, result, None)
        else:
            print result
    except Exception as e:
        logger.error(e)
        if context:
            send(event, context, FAILED, str(e))
        raise e
    return


if __name__ == "__main__":
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-c","--cidr", help="Cidr Range to divide out.")
    (opts, args) = parser.parse_args()
    options_broken = False
    if not opts.cidr:
        logger.error("Must Specify Cidr Block")
    if options_broken:
        parser.print_help()
        exit(1)

    event = { 'ResourceProperties': { 'VpcCidr': opts.cidr } }
    lambda_handler(event, None)
