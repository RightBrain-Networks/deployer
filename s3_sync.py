import os
import yaml
import boto3
from boto3.session import Session

class s3_sync(object):
    def __init__(self, profile, config_file, environment):
        self.profile = profile
        self.environment = environment
        self.config = self.get_config(config_file)
        self.region = self.get_config_att('region')
        self.release = self.get_config_att('release').replace('/','.')
        self.base = self.get_config_att('sync_base')
        self.sync_dirs = self.get_config_att('sync_dirs')
        self.dest_bucket = self.get_config_att('dest_bucket')
        self.session = Session(profile_name=profile,region_name=self.region)
        self.client = self.session.client('s3')
        self.sync()

    def get_config(self, config):
        with open(config) as f:
            data = yaml.load(f)
        return data

    def get_config_att(self, key):
        region = None
        if key in self.config['global']:
            base = self.config['global'][key]
        if key in self.config[self.environment]:
            base = self.config[self.environment][key]
        return base

    def get_destination_bucket(self):
        alt = 'full_sync_destination'
        if alt in self.date['global']:
            self.destination_bucket = self.config['global'][alt].split('/',1)
        else:
            self.destination_bucket = self.config['global']['template_bucket']
        if alt in self.date[self.environment]:
            self.destination_bucket = self.config[self.environment][alt].split('/',1)
        else:
            self.destination_bucket = self.config[self.environment]['template_bucket']
        return self.destination_bucket

    def sync(self):
        for sync_dir in self.sync_dirs:
            for dirName, subdirList, fileList in os.walk("%s%s" %(self.base,sync_dir)):
                thisdir = "".join(dirName.rsplit(self.base))
                for fname in fileList:
                    origin_path = "%s/%s" %(dirName,fname)
                    dest_key = "%s/%s/%s" % (self.release,thisdir,fname)
                    self.client.upload_file(origin_path, self.dest_bucket, dest_key)
                    print "Uploaded: %s to s3://%s/%s" % (origin_path, self.dest_bucket, dest_key)
