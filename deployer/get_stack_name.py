#!/usr/bin/python

import argparse
import ruamel.yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stack', metavar='STACK', help='The stack label to find')
    parser.add_argument('config', metavar='CONFIG', help='The path to the config file')
    args = parser.parse_args()

    config = ruamel.yaml.safe_load(open(args.config))
    print(config[args.stack]['stack_name'])

if __name__ == '__main__':
    main()
