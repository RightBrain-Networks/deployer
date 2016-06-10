import os
import yaml
import boto3
import fnmatch
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
        self.dest_bucket = self.get_config_att('sync_dest_bucket')
        self.session = Session(profile_name=profile,region_name=self.region)
        self.client = self.session.client('s3')
        self.excludes = self.construct_excludes()
        self.sync()

    def get_config(self, config):
        with open(config) as f:
            data = yaml.load(f)
        return data

    def get_config_att(self, key):
        base = None
        if key in self.config['global']:
            base = self.config['global'][key]
        if key in self.config[self.environment]:
            base = self.config[self.environment][key]
        return base

    def construct_excludes(self):
        excludes = self.get_config_att('sync_exclude')
        if excludes:
            excludes = [ "*%s*" % exclude for exclude in excludes]
        return excludes

    def sync(self):
        if self.sync_dirs:
            for sync_dir in self.sync_dirs:
                for dirName, subdirList, fileList in os.walk("%s%s" %(self.base,sync_dir)):
                    thisdir = "".join(dirName.rsplit(self.base))
                    fileList = [os.path.join(dirName,filename) for filename in fileList]
                    for ignore in self.excludes:
                        fileList = [n for n in fileList if not fnmatch.fnmatch(n,ignore)] 
                    for fname in fileList:
                        only_fname = os.path.split(fname)[1]
                        if thisdir == "":
                            dest_key = "%s/%s" % (self.release,only_fname)
                        else:
                            dest_key = "%s/%s/%s" % (self.release,thisdir,only_fname)
                        self.client.upload_file(fname, self.dest_bucket, dest_key)
                        print "Uploaded: %s to s3://%s/%s" % (fname, self.dest_bucket, dest_key)
