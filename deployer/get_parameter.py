#!/usr/bin/python

import argparse
import ruamel.yaml
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stack', metavar='STACK', help='The stack label to find')
    parser.add_argument('config', metavar='CONFIG', help='The path to the config file')
    parser.add_argument('param', metavar='PARAM', help='The parameter to retrieve')
    args = parser.parse_args()

    config = ruamel.yaml.safe_load(open(args.config))

    params = config.get('global', {}).get('parameters', {})
    params.update(config.get(args.stack, {}).get('parameters', {}))

    result = params.get(args.param, None)
    result and sys.stdout.write(result) or exit(1)

if __name__ == '__main__':
    main()
