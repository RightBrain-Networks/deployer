import fnmatch
import git
import hashlib
import os
import re
import yaml
from boto3.session import Session
from botocore.exceptions import ClientError
from multiprocessing import Process
from deployer.decorators import retry
from deployer.logger import logger
from deployer.cloudtools_bucket import CloudtoolsBucket

import sys, traceback

class s3_sync(object):
    def __init__(self, profile, config_file, environment, valid=False, debug=False):
        try:
            self.profile = profile
            self.debug = debug
            self.environment = environment
            self.config_file = config_file
            self.config = self.get_config(config_file)
            self.region = self.get_config_att('region')
            self.base = self.get_config_att('sync_base', '.')
            self.sync_dirs = self.get_config_att('sync_dirs', [])
            self.repository = self.get_repository()
            self.commit = self.repository.head.object.hexsha if self.repository else 'null'
            self.release = self.get_config_att('release', self.commit).replace('/', '.')
            self.session = Session(profile_name=profile, region_name=self.region)
            self.client = self.session.client('s3')
            self.cfn = self.session.client('cloudformation')
            self.excludes = self.construct_excludes()
            self.valid = valid

            self.cloudtools_bucket = CloudtoolsBucket(self.session, self.get_config_att('sync_dest_bucket', None))


            if not isinstance(self.sync_dirs, list):
                logger.error("Attribute 'sync_dirs' must be a list.")
                exit(4)
            elif not self.sync_dirs:
                logger.warning("Sync requested but no directories specified with the 'sync_dirs' attribute")

            self.sync()
        except (Exception) as e:
            logger.error(e)
            if self.debug:
                ex_type, ex, tb = sys.exc_info()
                traceback.print_tb(tb)

    def get_sync_dest_bucket(self):
        bucket = self.get_config_att('sync_dest_bucket')
        if not bucket:
            ssm = self.session.client('ssm')
            try:
                name = '/global/buckets/cloudtools/name'
                return ssm.get_parameter(Name=name).get('Parameter', {}).get('Value', None)
            except ClientError:
                return None
        else:
            return bucket

    def get_repository(self):
        try:
            return git.Repo(self.base, search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            return None

    def get_config(self, config):
        with open(config) as f:
            data = yaml.safe_load(f)
        return data

    def get_config_att(self, key, default=None, required=False):
        base = self.config.get('global', {}).get(key, None)
        base = self.config.get(self.environment).get(key, base)
        if required and base is None:
            logger.error("Required attribute '{}' not found in config '{}'.".format(key, self.config_file))
            exit(3)
        return base if base is not None else default

    def construct_excludes(self):
        excludes = self.get_config_att('sync_exclude')
        if excludes:
            excludes = ["*%s*" % exclude for exclude in excludes]
        return excludes


    def generate_etag(self,fname):
        md5s = []
        with open(fname, 'rb') as f:
            for chunk in iter(lambda: f.read(8388608), b""):
                md5s.append(hashlib.md5(chunk))
            if len(md5s) == 0:
                md5s.append(hashlib.md5(f.read(8388608)))
        if len(md5s) > 1:
            digests = b"".join(m.digest() for m in md5s)
            new_md5 = hashlib.md5(digests)
            etag = '"%s-%s"' % (new_md5.hexdigest(),len(md5s))
        else: 
            etag = '"%s"' % md5s[0].hexdigest()
        return etag
    
    @retry(ClientError,logger=logger)
    def validate(self, fname, dest_key):
        if re.match(".*cloudformation.*\.(json|yml)$", fname):
            try:
                etag = self.generate_etag(fname)
                s3_obj = self.client.get_object(Bucket=self.cloudtools_bucket.name, IfMatch=etag, Key=dest_key)
            except:
                filesize = os.stat(fname).st_size
                validate_path = "deployer_validate/%s" % dest_key
                if self.region != 'us-east-1':
                    validate_url = "https://s3-%s.amazonaws.com/%s/%s" % (self.region, self.cloudtools_bucket.name, validate_path)
                else:
                    validate_url = "https://s3.amazonaws.com/%s/%s" % (self.cloudtools_bucket.name, validate_path)
                try: 
                    if filesize > 51200:
                        self.client.upload_file(fname, self.cloudtools_bucket.name, validate_path)
                        self.cfn.validate_template(TemplateURL=validate_url)
                        self.client.delete_object(Bucket=self.cloudtools_bucket.name, Key=validate_path)
                    else:
                        with open(fname, 'r') as f:
                            resp = self.cfn.validate_template(TemplateBody=f.read())
                except Exception as e:
                    self.validate_failed(fname, validate_url, e.message)

    def validate_failed(self, fname, validate_url, message):
        try:
            logger.critical("Failed to Validate: %s\n%s" % (fname, message))
            self.client.delete_object(Bucket=self.cloudtools_bucket.name, Key=validate_path)
            exit(1)
        except:
            exit(1)

    def generate_dest_key(self, fname, thisdir):
        only_fname = os.path.split(fname)[1]
        if thisdir == "":
            dest_key = "%s/%s" % (self.release,only_fname)
        else:
            dest_key = "%s/%s/%s" % (self.release,thisdir,only_fname)
        if os.name == 'nt':
            dest_key = dest_key.replace("\\", "/")
        return dest_key

    def skip_or_send(self, fname, dest_key):
        try:
            etag = self.generate_etag(fname)
            if etag:
                self.client.get_object(Bucket=self.cloudtools_bucket.name, IfMatch=etag, Key=dest_key)
            else:
                logger.error("%s has no etag!" % (fname))
            logger.debug("Skipped: %s" % (fname))
            return
        except ClientError:
            logger.debug("Uploading: %s" % (fname))

        try:
            self.client.upload_file(fname, self.cloudtools_bucket.name, dest_key)
            logger.info("Uploaded: %s to s3://%s/%s" % (fname, self.cloudtools_bucket.name, dest_key))
        except (Exception) as e:
            logger.error(e)
            if self.debug:
                ex_type, ex, tb = sys.exc_info()
                traceback.print_tb(tb)
                
    def upload(self):
        if self.sync_dirs:
            for sync_dir in self.sync_dirs:
                sync_dir = sync_dir.strip(".")
                for dirName, subdirList, fileList in os.walk("%s%s" %(self.base,sync_dir)):
                    thisdir = "".join(dirName.rsplit(self.base)).strip("/")
                    fileList = [os.path.join(dirName,filename) for filename in fileList]
                    if self.excludes:
                        for ignore in self.excludes:
                            fileList = [n for n in fileList if not fnmatch.fnmatch(n,ignore)]
                    procs = []
                    for fname in fileList:
                        dest_key = self.generate_dest_key(fname, thisdir)
                        if os.name != 'nt':
                            procs.append(Process(target=self.skip_or_send, args=(fname, dest_key)))
                            procs[-1].deamon = True
                            procs[-1].start()
                            if len(procs) >= 20:
                                list(map(lambda x: x.join(), procs))
                                procs = []
                        else:
                            self.skip_or_send(fname, dest_key)
                    list(map(lambda x: x.join(), procs))
    def test(self):
        logger.info("Validating Templates")
        if self.sync_dirs:
            count = 0
            processes = []
            for sync_dir in self.sync_dirs:
                sync_dir = sync_dir.strip(".")
                for dirName, subdirList, fileList in os.walk("%s%s" %(self.base,sync_dir)):
                    thisdir = "".join(dirName.rsplit(self.base)).strip("/")
                    fileList = [os.path.join(dirName,filename) for filename in fileList]
                    if self.excludes:
                        for ignore in self.excludes:
                            fileList = [n for n in fileList if not fnmatch.fnmatch(n,ignore)] 
                    for fname in fileList:
                        dest_key = self.generate_dest_key(fname, thisdir)
                        if os.name != 'nt':
                            processes.append(Process(target=self.validate, args=(fname, dest_key)))
                            processes[count].deamon = True
                            processes[count].start()
                            if count % 5 == 0:
                                processes[count].join()
                        else:
                            self.validate(fname,dest_key)
                        count += 1
            if len(processes) != 0:
                for process in processes: 
                    process.join()
                for process in processes: 
                    if process.exitcode:
                        logger.critical("Failed to validate templates before upload")
                        exit(1)

    def sync(self):
        if self.valid:
            logger.debug("Assuming templates are valid and continuing to sync.")
        else:
            self.test()
        self.upload()
