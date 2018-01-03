#!/usr/bin/env python
import argparse
from deployer.cloudformation import Stack
from deployer.s3_sync import s3_sync
from deployer.lambda_prep import LambdaPrep
from deployer.logger import logging, logger, console_logger

import ruamel.yaml


__version__ = 'v0.3.5'

def main():
    parser = argparse.ArgumentParser(description='Deploy CloudFormation Templates')
    parser.add_argument("-c","--config", help="Path to config file.")
    parser.add_argument("-s","--stack", help="Stack Name.")
    parser.add_argument("-x","--execute", help="Execute ( create | update | delete | sync | change ) of stack.")
    parser.add_argument("-p","--profile", help="Profile.",default=None)
    parser.add_argument("-t","--change-set-name", help="Change Set Name.")
    parser.add_argument("-d","--change-set-description", help="Change Set Description.")
    parser.add_argument("-y","--copy",help="copy directory structure", action="store_true", dest="sync", default=False)
    parser.add_argument("-A","--all", help="Create or Update all environments in a config", action="store_true", dest="all", default=False)
    parser.add_argument("-r","--disable-rollback", help="Disable rollback on failure.", action="store_true", dest="rollback", default=False)
    parser.add_argument("-e","--events",help="Print events",action="store_true",dest="events",default=False)
    parser.add_argument("-z","--zip-lambdas", help="Zip lambda functions move them to synced directory", action="store_true", dest="zip_lambdas", default=False)
    parser.add_argument("-D","--debug", help="Sets logging level to DEBUG", action="store_true", dest="debug", default=False)

    args = parser.parse_args()

    options_broken = False
    if not args.config:
        args.config = 'config.yml'
    if not args.all:
        if not args.execute:
            print("Must Specify execute flag!")
            options_broken = True
        if not args.stack:
            print("Must Specify stack flag!")
            options_broken = True
    if options_broken:
        parser.print_help()
        exit(1)

    if args.debug:
        console_logger.setLevel(logging.DEBUG)

    if args.zip_lambdas:
        LambdaPrep(args.config, args.stack).zip_lambdas()

    if args.sync:
        syncer = s3_sync(args.profile, args.config, args.stack)

    if args.all:
        # Read Environment Config
        with open(args.config) as f:
            config = ruamel.yaml.load(f)

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
        env_stack = Stack(args.profile, args.config, args.stack, args.rollback, args.events)
        if args.execute == 'create':
            env_stack.create()
        elif args.execute == 'update':
            env_stack.update()
        elif args.execute == 'delete':
            env_stack.delete_stack()
        elif args.execute == 'change':
            env_stack.get_change_set(args.change_set_name, args.change_set_description, 'UPDATE')
        elif args.sync or args.execute == 'sync':
            syncer = s3_sync(args.profile, args.config, args.stack)


if __name__ == '__main__':
    try: main()
    except: raise
