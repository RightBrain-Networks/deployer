import boto3
from botocore.exceptions import ClientError
from parse import parse

from deployer.logger import logger

# Allow Python 2.x
try:
    input = raw_input
except NameError:
    pass

class CloudtoolsBucket():
    def __init__(self, session, override_bucket = None, create_bucket = True):

        self.override_bucket = override_bucket

        # Create boto3 objects
        self.session = session
        self.ssm = session.client('ssm')
        self.sts = session.client('sts')

        self.s3 = session.resource('s3').Bucket(self.name)

        # Create bucket if bucket does not exist
        if not self.bucket_exists:
            if create_bucket:
                self.s3.create()

    @property
    def name(self):
        if self.override_bucket:
            return self.override_bucket

        # If bucket name not set, search ssm for bucket
        parameter_name = '/global/' + self.session.region_name
        for parameter_name in ['/' + self.session.region_name,'/global']:
            try:
                result = self.ssm.get_parameter(Name=parameter_name + "/buckets/cloudtools/name")
                return result['Parameter']['Value']
            except ClientError as e:
                if e.response['Error']['Code'] == 'ParameterNotFound':
                    account = self.sts.get_caller_identity().get('Account')
                else:
                    raise e
        # If no bucket is found, use default bucket
        return "cloudtools-" + str(account) + "-" + self.session.region_name


    @property
    def bucket_exists(self):
        if self.s3.creation_date:
            return True
        return False

    def construct_template_url(self, config, stack, release, template):
        alt = 'full_template_url'
        if alt in config.config[stack]:
            self.template_url = config.config[stack][alt]
        else:
            s3 = self.session.client('s3')
            url_string = "https://{}.amazonaws.com/{}/{}/{}"
            template_bucket = self.name
            s3_endpoint = 's3' if self.session.region_name == 'us-east-1' else "s3-%s" % self.session.region_name
            try:
                s3.head_object(Bucket=template_bucket, Key="{}/{}".format(release, template))
                template_url = url_string.format(s3_endpoint, template_bucket, release, template)
                self.template_url = template_url
            except ClientError:
                self.template_url = None
        return self.template_url

    def get_template_file(self, config, stack):
        if 'template' in config.config[stack]:
            return config.config[stack]['template']
        else:
            format_string = "http://{sub}.amazonaws.com/{bucket}/{release}/{template}"
            return parse(format_string, self.template_url)['template']

    def get_template_body(self, config, template):
        bucket = config.get_config_att('template_bucket')
        if not bucket:
            try:
                with open(template, 'r') as f:
                    return f.read()
            except Exception as e:
                logger.warning("Failed to read template file: " + str(e))
                return None
        else:
            return None