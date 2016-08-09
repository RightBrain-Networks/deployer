#!/usr/bin/env python2.7
from optparse import OptionParser
from ConfigParser import ConfigParser
import yaml

def main():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-c","--config", help="Path to config file.")
    parser.add_option("-s","--stack", help="Stack Name.")
    parser.add_option("-A","--all", help="Create or Update all stacks in a config", action="store_true", dest="all", default=False)
    parser.add_option("-u","--updates", help="The updates that need to be changed in JSON formatted string.")

    (opts, args) = parser.parse_args()

    options_broken = False
    if not opts.config or not opts.updates:
        options_broken = True
    if options_broken:
        parser.print_help()
        exit(1)


if __name__ == '__main__':
    try: main()
    except: raise

