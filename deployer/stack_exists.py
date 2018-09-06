#!/usr/bin/python

import argparse
import boto3
import ruamel.yaml
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(region=None, profile=None, silent=False)
    parser.add_argument('stack', metavar='STACK', help='The stack label to find')
    parser.add_argument('config', metavar='CONFIG', help='The path to the config file')
    parser.add_argument('-p', '--profile', help='An AWS profile name')
    parser.add_argument('-r', '--region', help='An AWS region')
    parser.add_argument('-s', '--silent', action='StoreTrue', help='Suppress stdout')
    args = parser.parse_args()

    config = ruamel.yaml.safe_load(open(args.config))
    stack = config[args.stack]['stack_name']

    session = boto3.Session(region_name=args.region, profile_name=args.profile)
    client = session.client('cloudformation')

    result = client.list_stacks()
    if [x for x in result['StackSummaries'] if x['StackName'] == stack]:
        args.silent or sys.stdout.write('true')
        exit(0)
    else:
        args.silent or sys.stdout.write('false')
        exit(1)

if __name__ == '__main__':
    main()
