#!/usr/bin/env python
import argparse
import ruamel.yaml
import json

def config_update(config,item):
    for thing in item.items():
        if isinstance(thing[1],dict):
            config[thing[0]] = config_update(config[thing[0]],thing[1])
        else:
            config[thing[0]] = thing[1]
    return config

def main():
    parser = argparse.ArgumentParser(description='Deployer Config Updater')
    parser.add_argument("-c","--config", help="Path to config file.")
    parser.add_argument("-u","--updates", help="The updates that need to be changed in JSON formatted string.")

    args = parser.parse_args()

    options_broken = False
    if not args.config or not args.updates:
        options_broken = True
    if options_broken:
        parser.print_help()
        exit(1)

    updates = json.loads(args.updates)
    with open(args.config) as f:
        config = ruamel.yaml.round_trip_load(f)
    config = config_update(config,updates) 

    with open(args.config, 'w') as f:
        f.write(ruamel.yaml.round_trip_dump(config))

if __name__ == '__main__':
    try: main()
    except: raise

