#!/usr/bin/env python
import argparse
import json
import os
from deployer.cloudformation import Stack
from deployer.s3_sync import s3_sync
from deployer.lambda_prep import LambdaPrep
from deployer.logger import logging, logger, console_logger
from distutils.dir_util import copy_tree

import ruamel.yaml
import sys, traceback

__version__ = '0.3.18'


def main():
    if (len(sys.argv) == 2 or len(sys.argv) == 3) and sys.argv[1] == 'init':
        script_dir = os.path.dirname(__file__)
        skel_dir = os.path.join(script_dir, 'skel')
        if not 2 in sys.argv:
            copy_tree(skel_dir, ".")
        else:
            copy_tree(skel_dir, sys.argv[2])
        logger.info("Intialized directory for deployer")
        exit(0)

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
        print("\n  [init] DIR            Intializes the current directory")
        exit(1)

    if args.debug:
        console_logger.setLevel(logging.DEBUG)

    if args.execute == 'describe':
        console_logger.setLevel(logging.ERROR)

    if args.zip_lambdas:
        LambdaPrep(args.config, args.stack).zip_lambdas()

    if args.sync:
        s3_sync(args.profile, args.config, args.stack, args.assume_valid)

    try:
        if args.all:
            # Read Environment Config
            with open(args.config) as f:
                config = ruamel.yaml.safe_load(f)

            # Create or update all Environments
            for stack, obj in config.items():
                if stack != 'global':
                    print(stack)
                    env_stack = Stack(args.profile, args.config, stack, args.rollback, args.events)
                    env_stack = Stack(args.profile, args.config, stack, args.events)
                    if env_stack.stack_status:
                        print("Update %s" % stack)
                        env_stack.update_stack()
                    else:
                        print("Create %s" % stack)
                        env_stack.create_stack()
        else:

                env_stack = Stack(args.profile, args.config, args.stack, args.rollback, args.events, params)
                if args.execute == 'create':
                    env_stack.create()
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
    except (Exception) as e:
        logger.error(e)
        if args.debug:
            ex_type, ex, tb = sys.exc_info()
            traceback.print_tb(tb)
        if args.debug:
            del tb


if __name__ == '__main__':
    try: main()
    except: raise
