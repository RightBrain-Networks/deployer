#!/usr/bin/env python2.7
from cloudformation import EnvironmentStack
from lib import *
from optparse import OptionParser
from ConfigParser import ConfigParser

import yaml



def main():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage) 
    parser.add_option("-c","--config", help="Path to config file.")
    parser.add_option("-e","--environment", help="Environment name of stack.")
    parser.add_option("-x","--execute", help="Execute ( create | update | delete | change ) of stack.")
    parser.add_option("-p","--profile", help="Profile.")
    parser.add_option("-t","--change-set-name", help="Change Set Name.")
    parser.add_option("-d","--change-set-description", help="Change Set Description.")

    parser.add_option("-A","--all", help="Create or Update all environments in a config", action="store_true", dest="all", default=False)

    (opts, args) = parser.parse_args()

    options_broken = False
    if not opts.profile:
        opts.profile = 'default'
    if not opts.config:
        opts.config = 'config.yml'
    if not opts.all:
        if not opts.execute:
            print "Must Specify execute flag!"
            options_broken = True 
        if not opts.environment:
            print "Must Specify environment flag!"
            options_broken = True 
    if options_broken:
        parser.print_help()
        exit(1)


    if opts.all:
        # Read Environment Config
        with open(opts.config) as f:
            config = yaml.load(f)

        # Create or update all Environments
        for environment, obj in config.iteritems(): 
            if environment != 'global':
                print environment
                env_stack = EnvironmentStack(opts.profile, opts.config, environment)
                if env_stack.stack_status:
                    print "Update %s" % environment
                    env_stack.update_stack()
                else:
                    print "Create %s" % environment
                    env_stack.create_stack()
            
    else:
        env_stack = EnvironmentStack(opts.profile, opts.config, opts.environment)
        if opts.execute == 'create':
            env_stack.create_stack()
        elif opts.execute == 'update':
            env_stack.update_stack()
        elif opts.execute == 'delete':
            env_stack.delete_stack()
        elif opts.execute == 'change':
            env_stack.get_change_set(opts.change_set_name, opts.change_set_description)
        

if __name__ == '__main__':
    try: main()
    except: raise

