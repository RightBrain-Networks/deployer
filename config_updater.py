#!/usr/bin/env python2.7
from optparse import OptionParser
from ConfigParser import ConfigParser
import ruamel.yaml
import json

def config_update(config,item):
    for thing in item.iteritems():
        if isinstance(thing[1],dict):
            config[thing[0]] = config_update(config[thing[0]],thing[1])
        else:
            config[thing[0]] = thing[1]
    return config

def main():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-c","--config", help="Path to config file.")
    parser.add_option("-u","--updates", help="The updates that need to be changed in JSON formatted string.")

    (opts, args) = parser.parse_args()

    options_broken = False
    if not opts.config or not opts.updates:
        options_broken = True
    if options_broken:
        parser.print_help()
        exit(1)

    updates = json.loads(opts.updates)
    with open(opts.config) as f:
        config = ruamel.yaml.round_trip_load(f)
    config = config_update(config,updates) 

    with open(opts.config, 'w') as f:
        f.write(ruamel.yaml.round_trip_dump(config))

if __name__ == '__main__':
    try: main()
    except: raise

