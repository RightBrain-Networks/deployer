#!/usr/bin/env python
from cloudformation import NetworkStack, EnvironmentStack
from lib import *
from optparse import OptionParser
from ConfigParser import ConfigParser

import yaml



def main():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage) 
    parser.add_option("-c","--config", help="Path to config file.")
    parser.add_option("-e","--environment", help="Environment name of stack.")
    parser.add_option("-x","--execute", help="Execute ( create | update | delete ) of stack.")
    #parser.add_option("-s","--sync", help="Sync to S3 ( Requires Release Number).", action="store_true", dest='sync')
    #parser.add_option("-r","--release", help="Release Number.")
    parser.add_option("-p","--profile", help="Profile.")

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


    network_stack = NetworkStack(opts.profile, opts.config)
    if opts.all:
        
        # Create or update Network
        if network_stack.stack_status:
            print "Update Network"
            network_stack.update_stack()
        else:
            print "Create Network"
            network_stack.create_stack()

        # Read Environment Config
        with open(opts.config) as f:
            config = yaml.load(f)

        # Create or update all Environments
        for environment, obj in config.iteritems(): 
            if environment != 'global' and environment != 'Network':
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
            if network_stack.stack_status == 'False':
                network_stack.create_stack()
            if opts.environment != 'Network':
                env_stack.create_stack()
        elif opts.execute == 'update':
            if opts.environment == 'Network':
                network_stack.update_stack()
            else:
                env_stack.update_stack()
        elif opts.execute == 'delete':
            if opts.environment == 'Network':
                network_stack.delete_stack()
            else:
                env_stack.delete_stack()
        

if __name__ == '__main__':
    try: main()
    except: raise

