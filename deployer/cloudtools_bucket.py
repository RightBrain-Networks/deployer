import boto3
from botocore.exceptions import ClientError

from deployer.logger import logger

# Allow Python 2.x
try:
    input = raw_input
except NameError:
    pass

class CloudtoolsBucket():
    def __init__(self, session, override_bucket = None):

        self.override_bucket = override_bucket

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
        bucket = None
        parameter_name = '/deployerBucket/' + self.session.region_name
        try:
            result = self.ssm.get_parameter(Name=parameter_name)
            bucket = result['Parameter']['Value']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                account = self.sts.get_caller_identity().get('Account')
                return "cloudtools-" + str(account) + "-" + self.session.region_name
        return bucket


    @property
    def bucket_exists(self):
        if self.s3.creation_date:
            return True
        return False