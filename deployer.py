#!/usr/bin/env python2.7
from cloudformation import Stack
from s3_sync import s3_sync
from optparse import OptionParser
from ConfigParser import ConfigParser
from lambda_prep import LambdaPrep
from logger import logger

import yaml

def main():
    logger.info('test')
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-c","--config", help="Path to config file.")
    parser.add_option("-s","--stack", help="Stack Name.")
    parser.add_option("-x","--execute", help="Execute ( create | update | delete | sync | change ) of stack.")
    parser.add_option("-p","--profile", help="Profile.",default=None)
    parser.add_option("-t","--change-set-name", help="Change Set Name.")
    parser.add_option("-d","--change-set-description", help="Change Set Description.")
    parser.add_option("-y","--copy",help="copy directory structure", action="store_true", dest="sync", default=False)
    parser.add_option("-A","--all", help="Create or Update all environments in a config", action="store_true", dest="all", default=False)
    parser.add_option("-r","--disable-rollback", help="Disable rollback on failure.", action="store_true", dest="rollback", default=False)
    parser.add_option("-e","--events",help="Print events",action="store_true",dest="events",default=False)
    parser.add_option("-z","--zip-lambdas", help="Zip lambda functions move them to synced directory", action="store_true", dest="zip_lambdas", default=False)

    (opts, args) = parser.parse_args()

    options_broken = False
    if not opts.config:
        opts.config = 'config.yml'
    if not opts.all:
        if not opts.execute:
            print "Must Specify execute flag!"
            options_broken = True
        if not opts.stack:
            print "Must Specify stack flag!"
            options_broken = True
    if options_broken:
        parser.print_help()
        exit(1)

    if opts.zip_lambdas:
        LambdaPrep(opts.config, opts.stack).zip_lambdas()

    if opts.sync:
        syncer = s3_sync(opts.profile, opts.config, opts.stack)

    if opts.all:
        # Read Environment Config
        with open(opts.config) as f:
            config = yaml.load(f)

        # Create or update all Environments
        for stack, obj in config.iteritems():
            if stack != 'global':
                print stack
                env_stack = Stack(opts.profile, opts.config, stack, opts.rollback, opts.events)
                env_stack = Stack(opts.profile, opts.config, stack, opts.events)
                if env_stack.stack_status:
                    print "Update %s" % stack
                    env_stack.update_stack()
                else:
                    print "Create %s" % stack
                    env_stack.create_stack()
    else:
        env_stack = Stack(opts.profile, opts.config, opts.stack, opts.rollback, opts.events)
        if opts.execute == 'create':
            env_stack.create_stack()
        elif opts.execute == 'update':
            env_stack.update_stack()
        elif opts.execute == 'delete':
            env_stack.delete_stack()
        elif opts.execute == 'change':
            env_stack.get_change_set(opts.change_set_name, opts.change_set_description)
        elif opts.sync or opts.execute == 'sync':
            syncer = s3_sync(opts.profile, opts.config, opts.stack)


if __name__ == '__main__':
    try: main()
    except: raise
