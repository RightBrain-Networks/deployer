#!/usr/bin/env python
import argparse
import json
import os
from botocore.exceptions import ClientError
from deployer.cloudformation import Stack
from deployer.s3_sync import s3_sync
from deployer.lambda_prep import LambdaPrep
from deployer.logger import logging, logger, console_logger
from distutils.dir_util import copy_tree

import ruamel.yaml
import sys, traceback

__version__ = '0.3.18'


def main():
    parser = argparse.ArgumentParser(description='Deploy CloudFormation Templates')
    parser.add_argument("-c", "--config", help="Path to config file.")
    parser.add_argument("-s", "--stack", help="Stack Name.")
    parser.add_argument("-x", "--execute", help="Execute ( create | update | delete | upsert | sync | change ) of stack.")
    parser.add_argument("-P", "--param", action='append', help='An override for a parameter')
    parser.add_argument("-p", "--profile", help="Profile.",default=None)
    parser.add_argument("-t", "--change-set-name", help="Change Set Name.")
    parser.add_argument("-d", "--change-set-description", help="Change Set Description.")
    parser.add_argument("-y", "--copy",help="copy directory structure", action="store_true", dest="sync", default=False)
    parser.add_argument("-A", "--all", help="Create or Update all environments in a config", action="store_true", dest="all", default=False)
    parser.add_argument("-r", "--disable-rollback", help="Disable rollback on failure.", action="store_true", dest="rollback", default=False)
    parser.add_argument("-e", "--events",help="Print events",action="store_false",dest="events",default=True)
    parser.add_argument("-z", "--zip-lambdas", help="Zip lambda functions move them to synced directory", action="store_true", dest="zip_lambdas", default=False)
    parser.add_argument("-j", "--assume-valid", help="Assumes templates are valid and does not do upstream validation (good for preventing rate limiting)", action="store_true", dest="assume_valid", default=False)
    parser.add_argument("-D", "--debug", help="Sets logging level to DEBUG & enables traceback", action="store_true", dest="debug", default=False)
    parser.add_argument("-v", "--version", help='Print version number', action='store_true', dest='version')
    parser.add_argument("-T", "--timeout", type=int, help='Stack create timeout')
    parser.add_argument('--init', default=None, const='.', nargs='?', help='Initialize a skeleton directory')
    parser.add_argument("--disable-color", help='Disables color output', action='store_true', dest='no_color')


    args = parser.parse_args()

    if not args.no_color:
        # Set level formatting and colors
        logging.addLevelName( logging.DEBUG, "\033[3;35m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
        logging.addLevelName( logging.INFO, "\033[3m%s\033[1;0m" % logging.getLevelName(logging.INFO))
        logging.addLevelName( logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
        logging.addLevelName( logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))

    if args.version:
        print(__version__)
        exit(0)

    if args.init is not None:
        script_dir = os.path.dirname(__file__)
        skel_dir = os.path.join(script_dir, 'skel')
        copy_tree(skel_dir, args.init)
        exit(0)

    print
    options_broken = False
    params = {}
    if not args.config:
        args.config = 'config.yml'
    if not args.all:
        if not args.execute:
            print("\033[1;33mMust Specify execute flag!\033[1;0m")
            options_broken = True
        if not args.stack:
            print("\033[1;33mMust Stack execute flag!\033[1;0m")
            options_broken = True
    if args.param:
        for param in args.param:
            split = param.split('=', 1)
            if len(split) == 2:
                params[split[0]] = split[1]
            else:
                print("\033[3mInvalid format for parameter\033[1;0m '{}'".format(param))
                options_broken = True

    if options_broken:
        parser.print_help()
        exit(1)

    if args.debug:
        console_logger.setLevel(logging.DEBUG)

    if args.execute == 'describe':
        console_logger.setLevel(logging.ERROR)

    if args.zip_lambdas:
        LambdaPrep(args.config, args.stack).zip_lambdas()



    try:
        # Read Environment Config
        with open(args.config) as f:
            config = ruamel.yaml.safe_load(f)

        stackQueue = []
        if not args.all:
            stackQueue = [args.stack]
        else:
            for stack in config.items():
                if stack[0] != "global":
                    stackQueue = find_deploy_path(config, stack[0], stackQueue)

        if args.timeout and args.execute not in ['create', 'upsert']:
            logger.warning("Timeout specified but action is not 'create'. Timeout will be ignored.")

        # Create or update all Environments
        for stack in stackQueue:
            if stack != 'global' and (args.all or stack == args.stack):
                if args.sync:
                    s3_sync(args.profile, args.config, stack, args.assume_valid)
                if args.no_color:
                    logger.info("Running " + str(args.execute) + " on stack: " + stack)
                else:
                    logger.info("Running \033[4m" + str(args.execute) + "\033[0m on stack: \033[1;93m" + stack + "\033[0m")
                env_stack = Stack(args.profile, args.config, stack, args.rollback, args.events, args.timeout, params)
                if args.execute == 'create':
                    try:
                        env_stack.create()
                    except ClientError as e:
                        if not args.all:
                            raise e
                        elif e.response['Error']['Code'] == 'AlreadyExistsException':
                            logger.info("Stack, " + stack + ", already exists.")
                        else:
                            raise e
                elif args.execute == 'update':
                    env_stack.update()
                elif args.execute == 'delete':
                    env_stack.delete_stack()
                elif args.execute == 'upsert':
                    env_stack.update() if env_stack.check_stack_exists() else env_stack.create()
                elif args.execute == 'describe':
                    print(json.dumps(env_stack.describe(),
                                    sort_keys=True,
                                    indent=4,
                                    separators=(',', ': '),
                                    default=lambda x: x.isoformat()))
                elif args.execute == 'change':
                    env_stack.get_change_set(args.change_set_name, args.change_set_description, 'UPDATE')
                elif args.sync or args.execute == 'sync':
                    s3_sync(args.profile, args.config, args.stack, args.assume_valid, args.debug)
    except (Exception) as e:
        logger.error(e)
        if args.debug:
            ex_type, ex, tb = sys.exc_info()
            traceback.print_tb(tb)

def find_deploy_path(stackConfig, checkStack, resolved = []):
    #Generate depedency graph
    graph = {}
    for stack in stackConfig.items():
        if stack[0] != "global":
            edges = []
            if 'lookup_parameters' in stack[1]:
                for param in stack[1]['lookup_parameters']:
                    edge = stack[1]['lookup_parameters'][param]
                    if edge['Stack'] not in edges:
                        edges.append(edge['Stack'])
            graph[stack[0]] = edges

    #Find dependency order
    resolve_dependency(graph, checkStack, resolved)
    return resolved

def resolve_dependency(graph, node, resolved, seen = []):
    seen.append(node)
    for edge in graph[node]:
        if edge not in resolved:
            #If node has already been seen, it's a circular dependency
            if edge in seen:
                raise Exception("Circular dependency detected between stacks %s and %s." % (node, edge))
            #Check edge for dependencies
            resolve_dependency(graph, edge, resolved, seen)
    if node not in resolved:
        resolved.append(node)


if __name__ == '__main__':
    try: main()
    except: raise
