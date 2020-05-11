#!/usr/bin/env python
import argparse
import json
import os
from botocore.exceptions import ClientError
from deployer.stack import Stack
from deployer.s3_sync import s3_sync
from deployer.lambda_prep import LambdaPrep
from deployer.logger import logging, logger, console_logger
from deployer.stack_sets import StackSet
from distutils.dir_util import copy_tree
from collections import defaultdict
from deployer.logger import update_colors
from deployer.configuration import Config
from deployer.cloudtools_bucket import CloudtoolsBucket
from boto3.session import Session

import ruamel.yaml
import sys, traceback

__version__ = '0.0.0'


def main():
    # Build arguement parser
    parser = argparse.ArgumentParser(description='Deploy CloudFormation Templates')
    parser.add_argument("-c", "--config", help="Path to config file.",default=None)
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


    # Load colors into logger
    colors = defaultdict(lambda: '')
    if not args.no_color:
        update_colors(colors)
        # Set level formatting and colors
        logging.addLevelName( logging.DEBUG, colors['debug'] + "%s" % logging.getLevelName(logging.DEBUG) + colors['reset'])
        logging.addLevelName( logging.INFO, colors['info'] + "%s" % logging.getLevelName(logging.INFO) + colors['reset'])
        logging.addLevelName( logging.WARNING, colors['warning'] + "%s" % logging.getLevelName(logging.WARNING) + colors['reset'])
        logging.addLevelName( logging.ERROR, colors['error'] + "%s" % logging.getLevelName(logging.ERROR) + colors['reset'])

    # Output version `-v`
    if args.version:
        print(__version__)
        exit(0)

    # Build skeleton environment at target directory
    if args.init is not None:
        script_dir = os.path.dirname(__file__)
        skel_dir = os.path.join(script_dir, 'skel')
        copy_tree(skel_dir, args.init)
        exit(0)

    # Validate arguements and parameters
    options_broken = False
    params = {}
    if args.all:
        if not args.config:
            print(colors['warning'] + "Must Specify config flag!" + colors['reset'])
            options_broken = True
    if not args.all:
        if not args.execute:
            print(colors['warning'] + "Must Specify execute flag!" + colors['reset'])
            options_broken = True
        if not args.stack:
            print(colors['warning'] + "Must specify stack flag!" + colors['reset'])
            options_broken = True
    if args.param:
        for param in args.param:
            split = param.split('=', 1)
            if len(split) == 2:
                params[split[0]] = split[1]
            else:
                print(colors['warning'] + "Invalid format for parameter '{}'".format(param) + colors['reset'])
                options_broken = True

    # Print help output
    if options_broken:
        parser.print_help()
        exit(1)

    if args.debug:
        console_logger.setLevel(logging.DEBUG)
    if args.execute == 'describe':
        console_logger.setLevel(logging.ERROR)

    try:

        # Load stacks into queue
        stackQueue = []
        if not args.all:
            stackQueue = [args.stack]
        else:
            #Load config, get stacks
            try:
                with open(args.config) as f:
                    file_data = ruamel.yaml.safe_load(f)
            except Exception as e:
                msg = str(e)
                logger.error("Failed to retrieve data from config file {}: {}".format(file_name,msg))
                exit(3)
            
            for stack in file_data.keys():
                if stack[0] != "global":
                    stackQueue = find_deploy_path(config_object.get_config(), stack[0], stackQueue)

        # Create or update all Environments
        for stack in stackQueue:
            if stack != 'global' and (args.all or stack == args.stack):

                logger.info("Running " + colors['underline'] + str(args.execute) + colors['reset'] + " on stack: " + colors['stack'] + stack + colors['reset'])
                
                # Create deployer config object
                cargs = {
                  'profile': args.profile,
                  'stack_name': stack
                }
                if args.config:
                    cargs['file_name'] = args.config
                    
                if args.param:
                    cargs['override_params'] = params
                
                config_object = Config(**cargs)
        
                # Build lambdas on `-z`
                if args.zip_lambdas:
                    logger.info("Building lambdas for stack: " + stack)
                    lambda_dirs = config_object.get_config_att('lambda_dirs', [])
                    sync_base = config_object.get_config_att('sync_base', '.')
                    LambdaPrep(sync_base, lambda_dirs).zip_lambdas()
                
                # AWS Session object
                session = Session(profile_name=args.profile, region_name=config_object.get_config_att('region'))

                # Pass arguements as dictionary
                arguements = {
                    'disable_rollback' : args.rollback,
                    'print_events' : args.events,
                    'timeout' : args.timeout,
                    'colors' : colors,
                    'params' : params
                }
                
                # S3 bucket to sync to
                bucket = CloudtoolsBucket(session, config_object.get_config_att('sync_dest_bucket', None))
                
                # Check whether stack is a stack set or not and assign corresponding object
                if(len(config_object.get_config_att('regions', [])) > 0 or len(config_object.get_config_att('accounts', [])) > 0):
                    env_stack = StackSet(session, stack, config_object, bucket, arguements)
                else:
                    if args.timeout and args.execute not in ['create', 'upsert']:
                        logger.warning("Timeout specified but action is not 'create'. Timeout will be ignored.")
                    env_stack = Stack(session, stack, config_object, bucket, arguements)
                try:

                    # Sync files to S3
                    if args.sync or args.execute == 'sync':
                        s3_sync(session, config_object, bucket, args.assume_valid, args.debug)

                    # Check which action to execute
                    if args.execute == "describe":
                        print(json.dumps(env_stack.describe(),
                                        sort_keys=True,
                                        indent=4,
                                        separators=(',', ': '),
                                        default=lambda x: x.isoformat()))
                    elif args.execute == 'change':
                        env_stack.get_change_set(args.change_set_name, args.change_set_description, 'UPDATE')
                    else:
                        # Check stack object for supported action
                        operation = getattr(env_stack, (args.execute + "_stack"), None)
                        if callable(operation):
                            operation()
                        else:
                            logger.warning(args.execute + " is not a valid method!")

                except ClientError as e:
                        if not args.all:
                            raise e
                        elif e.response['Error']['Code'] == 'AlreadyExistsException':
                            logger.info("Stack, " + stack + ", already exists.")
                        else:
                            raise e
    except (Exception) as e:
        logger.error(e)
        if args.debug:
            tb = sys.exc_info()[2]
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
            if 'depends_on' in stack[1]:
                for edge in stack[1]['depends_on']:
                    if edge not in edges:
                        edges.append(edge)
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
