import shutil
import boto3
import fnmatch
import os
import pip
import yaml
import hashlib
from boto3.session import Session
from multiprocessing import Process


class s3_sync(object):
    def __init__(self, profile, config_file, environment):
        self.profile = profile
        self.environment = environment
        self.config = self.get_config(config_file)
        self.region = self.get_config_att('region')
        self.release = self.get_config_att('release').replace('/', '.')
        self.base = self.get_config_att('sync_base')
        self.sync_dirs = self.get_config_att('sync_dirs')
        self.dest_bucket = self.get_config_att('sync_dest_bucket')
        self.session = Session(profile_name=profile, region_name=self.region)
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
            excludes = ["*%s*" % exclude for exclude in excludes]
        return excludes

    def generate_etag(self,fname):
        md5s = []
        with open(fname, 'rb') as f:
            count = 0
            for chunk in iter(lambda: f.read(8388608), b""):
                md5s.append(hashlib.md5(chunk))
        if len(md5s) > 1:
            digests = b"".join(m.digest() for m in md5s)
            new_md5 = hashlib.md5(digests)
            etag = '"%s-%s"' % (new_md5.hexdigest(),len(md5s))
        else: 
            etag = '"%s"' % md5s[0].hexdigest()
        return etag

    def skip_or_send(self, fname, thisdir):
        only_fname = os.path.split(fname)[1]
        if thisdir == "":
            dest_key = "%s/%s" % (self.release,only_fname)
        else:
            dest_key = "%s/%s/%s" % (self.release,thisdir,only_fname)
        if os.name == 'nt':
            dest_key = dest_key.replace("\\", "/")
        try:
            etag = self.generate_etag(fname)
            s3_obj = self.client.get_object(Bucket=self.dest_bucket, IfMatch=etag, Key=dest_key)
            print "Skipped: %s" % (fname)
        except Exception as e:
            self.client.upload_file(fname, self.dest_bucket, dest_key)
            print "Uploaded: %s to s3://%s/%s" % (fname, self.dest_bucket, dest_key)

    def sync(self):
        if self.sync_dirs:
            for sync_dir in self.sync_dirs:
                sync_dir = sync_dir.strip(".")
                for dirName, subdirList, fileList in os.walk("%s%s" %(self.base,sync_dir)):
                    thisdir = "".join(dirName.rsplit(self.base)).strip("/")
                    fileList = [os.path.join(dirName,filename) for filename in fileList]
                    for ignore in self.excludes:
                        fileList = [n for n in fileList if not fnmatch.fnmatch(n,ignore)] 
                    count = 0
                    for fname in fileList:
                        rv = Process(target=self.skip_or_send, args=(fname, thisdir))
                        rv.deamon = True
                        rv.start()
                        if count % 20 == 0:
                            rv.join()
                        count += 1
                    if 'rv' in vars():
                        rv.join()
