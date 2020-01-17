import boto3
from botocore.exceptions import ClientError

from deployer.logger import logger

# Allow Python 2.x
try:
    input = raw_input
except NameError:
    pass

class CloudtoolsBucket():
    def __init__(self, session, override_bucket = None, project = None):

        self.override_bucket = override_bucket
        self.project = project

        # Create boto3 objects
        self.session = session
        self.ssm = session.client('ssm')
        self.sts = session.client('sts')

        self.s3 = session.resource('s3').Bucket(self.name)

        # Ask to create bucket if bucket does not exist
        if not self.bucket_exists:
            response = None
            while not response:
                print("Bucket named: " + self.name + " does not exist.\nWould you like to create it? (y/n)")
                response = input()
                if response.lower() == 'y':
                    logger.info("Creating s3 bucket named: " + self.name)
                    self.s3.create()
                elif response.lower() != 'n':
                    response = None

    @property
    def name(self):
        if self.override_bucket:
            return self.override_bucket
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
        return "cloudtools-" + str(account) + "-" + self.session.region_name


    @property
    def bucket_exists(self):
        if self.s3.creation_date:
            return True
        return False