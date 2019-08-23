import os, errno
import shutil
import subprocess
import yaml

from deployer.logger import logger


class LambdaPrep:

    def __init__(self, config_file, environment):
        self.config_file = config_file
        self.config = self.get_config(config_file)
        self.environment = environment
        self.lambda_dirs = self.get_config_att('lambda_dirs', [])
        self.sync_base = self.get_config_att('sync_base', '.')

        if not isinstance(self.lambda_dirs, list):
            logger.error("Attribute 'lambda_dirs' must be a list.")
            exit(5)
        elif not self.lambda_dirs:
            logger.warning("Lambda packaging requested but no directories specified with the 'lambda_dirs' attribute")

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

                    # Move package to either sync_base or next to lambda directory
                    if self.sync_base.split('/')[-1] not in dir and self.sync_base != './' and dir[0] == '/':
                        # Goes to ${sync_base}/lambas/${file_name}.zip
                        dest = '/'.join([self.sync_base , '/'.join('lambdas')]).replace('//', '/')
                        if not os.path.exists(dest): os.mkdir(dest)
                        shutil.copy(file_name, dest)
                    else:
                        # Goes to ${dir}/${file_name}.zip
                        dest = '/'.join(dir.split('/')[:-1]).replace('//', '/')
                        if not os.path.exists(dest): os.mkdir(dest)
                        shutil.copy(file_name, dest)

                    os.remove(file_name) #Remove ./${file}.zip
                else:
                    raise ValueError("Lambda path '{}' does not exist.".format(dir))
        else:
            logger.debug("No 'lambda_dirs' defined in stack; ignoring -z flag")
