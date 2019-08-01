import os, errno
import shutil
import subprocess
import yaml

from deployer.logger import logger


class LambdaPrep:

    def __init__(self, config_file, environment):
        self.config = self.get_config(config_file)
        self.environment = environment
        self.lambda_dirs = self.get_config_att('lambda_dirs')
        self.sync_base = self.get_config_att('sync_base')
        self.sync_dirs = self.get_config_att('sync_dirs')
        pass

    def get_config(self, config):
        with open(config) as f:
            data = yaml.safe_load(f)
        return data

    def get_config_att(self, key):
        base = None
        if key in self.config['global']:
            base = self.config['global'][key]
        if key in self.config[self.environment]:
            base = self.config[self.environment][key]
        return base

    #  zip_lambdas() will traverse through our configured lambda_dirs array,
    #  create a temp lambda directory, install necessary dependencies,
    #  zip it, move it, and cleanup all temp artifacts
    def zip_lambdas(self):
        logger.info('Creating Lambda Archives')
        if self.lambda_dirs:
            for dir in self.lambda_dirs:
                logger.info('Archiving ' + dir)
                if os.path.exists(dir):
                    temp_dir = dir + "_temp"
                    logger.debug('Creating ' + temp_dir)
                    shutil.copytree(dir, temp_dir)
                    if os.path.exists("/".join([temp_dir, "package.json"])):
                        req_txt = temp_dir + "/package.json"
                        logger.debug('Found ' + req_txt)
                        # Nodejs
                        subprocess.call(["npm","install"], cwd=temp_dir)
                        subprocess.call(["npm","run","build"], cwd=temp_dir)
                    if os.path.exists("/".join([temp_dir, "requirements.txt"])):
                        req_txt = "/".join([temp_dir, "requirements.txt"])
                        logger.debug('Found ' + req_txt)
                        try:
                            # Python 3
                            subprocess.run(["pip", "install", "-q", "-r", req_txt, "-t", temp_dir])
                        except AttributeError:
                            # Python 2
                            subprocess.call(["pip", "install", "-q", "-r", req_txt, "-t", temp_dir])
                    logger.debug('Archiving ' + dir.split('/')[-1])
                    shutil.make_archive(dir.split('/')[-1], "zip", temp_dir)
                    logger.debug('Removing ' + temp_dir)
                    shutil.rmtree(temp_dir)
                    file_name = "{}.zip".format(dir.split('/')[-1])

                    # Move package to sync_base if not already in sync scope
                    if (self.sync_base == './' and '/' != dir[0]) or (self.sync_base != './' and self.sync_base.remove('./') not in dir):
                        dest = '/'.join([self.sync_base, '/'.join(dir.split('/')[:-1])]).replace('//', '/')
                        try:
                            shutil.copytree(file_name, dest)
                        except OSError as e:
                            if e.errno == errno.ENOTDIR:
                                shutil.copy(file_name, dest)
                            else:
                                raise e
                        logger.debug('Moving archive to ' + dest)
                        shutil.copy(file_name, dest)
                        os.remove(file_name)
                else:
                    raise ValueError("Lambda path '{}' does not exist.".format(dir))
        else:
            logger.debug("No 'lambda_dirs' defined in stack; ignoring -z flag")
