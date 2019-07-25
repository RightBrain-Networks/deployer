#!/usr/bin/env python
import argparse
import json
from deployer.cloudformation import Stack
from deployer.s3_sync import s3_sync
from deployer.lambda_prep import LambdaPrep
from deployer.logger import logging, logger, console_logger
from botocore.exceptions import ClientError, WaiterError

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

    args = parser.parse_args()

    if args.version:
        print(__version__)
        exit(0)

    options_broken = False
    params = {}
    if not args.config:
        args.config = 'config.yml'
    if not args.all:
        if not args.execute:
            print("Must Specify execute flag!")
            options_broken = True
        if not args.stack:
            print("Must Specify stack flag!")
            options_broken = True
    if args.param:
        for param in args.param:
            split = param.split('=', 1)
            if len(split) == 2:
                params[split[0]] = split[1]
            else:
                console_logger.error("Invalid format for parameter '{}'".format(param))
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

        effectedStacks = []
        stackQueue = []
        if not args.all:
            # Add specified stack to queue
            stackQueue.append(args.stack)
        else:
            # Add available stacks to queue
            stackQueue = get_deployableStacks(config, effectedStacks)

        #While there are stacks to be created
        while(len(stackQueue) > 0):
            # Create or update all Environments
            for stack in stackQueue:
                if stack != 'global' and (args.all or stack == args.stack):
                    if args.sync:
                        s3_sync(args.profile, args.config, stack, args.assume_valid)
                    logger.info("Running " + str(args.execute) + " on stack: " + stack)
                    env_stack = Stack(args.profile, args.config, stack, args.rollback, args.events, params)
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
                        s3_sync(args.profile, args.config, args.stack, args.assume_valid)
                    effectedStacks.append(stack)
            if args.all:
                #Generate check for new deployable stacks
                stackQueue = get_deployableStacks(config, effectedStacks)
            else:
                stackQueue.remove(stack)

        #Check for any remaining stacks
        if args.all:
            remainingStacks = []
            for item in config.items():
                if item[0] not in effectedStacks and item[0] != "global":
                    remainingStacks.append(item[0])
            #Give error message if there were any circular dependencies
            if(len(remainingStacks) > 0):
                logger.error(str(len(remainingStacks)) + " stack(s) had circular dependencies:")
                for stack in remainingStacks:
                    logger.error("      " + stack)

    except (Exception) as e:
        logger.error(e)
        if args.debug:
            ex_type, ex, tb = sys.exc_info()
            traceback.print_tb(tb)
    finally:
        if args.debug:
            try:
                del tb
            except:
                pass

def find_deploy_path(stackConfig, stack, deployed = []):
    #Generate depedency graph
    graph = {}
    for stack in stackConfig.items():
        if stack[0] != "global":
            edges = []
            for param in stackConfig[1]['lookup_parameters']:
                if param['Stack'] not in edges:
                    edges.append(param['Stack'])
            graph[stack[0]] = edges
    result = []
    resolve_dependency(graph, stack, result)

def resolve_dependency(graph, node, resolved, seen = []):
    seen.append(node)
    for edge in graph[node]:
        if edge not in resolved:
            if edge in seen:
                raise Exception("Circular dependency detected between stacks %s and %s." % (node, edge))
            resolve_dependency(graph, edge, resolved, seen)
    resolved.append(node)


def get_deployableStacks(config, effectedStacks):
    deployableStacks = [] #Output
    checkQueue = []

    #Add any stacks that were not created to queue
    for item in config.items():
        if item[0] not in effectedStacks and item[0] != "global":
            checkQueue.append(item[0])

    #Check stacks for dependencies
    for stack in checkQueue:
        haveAllDependency = True
        for item in config.items():
            if item[0] == stack:
                if 'lookup_parameters' in item[1]:
                    for parameter in item[1]['lookup_parameters']:
                        if item[1]['lookup_parameters'][parameter]['Stack'] not in effectedStacks:
                            haveAllDependency = False
                            break
        if haveAllDependency:
            deployableStacks.append(stack)
    return deployableStacks


if __name__ == '__main__':
    try: main()
    except: raise
