import unittest
import __init__ as deployer
import boto3, json
import sys, subprocess, os, shutil, time
from botocore.exceptions import ClientError
import yaml
from datetime import tzinfo, timedelta, datetime

deployerExecutor = "deployer/__init__.py"
configUpdateExecutor = "deployer/config_updater.py"

apiHitRate = 0.25

#------------------------#
# CFN Testing Parameters #
#------------------------#
testStackName = "deployer-test-case"
testStackConfig = "deployer/tests/config.yaml"
testStackCloudFormation = "deployer/tests/cloudformation.yaml"

testBucket = "deployer-testing-us-east-1"

testStackConfig_data = """
global:
  sync_base: ./deployer/
  sync_dest_bucket: deployer-testing-us-east-1
  sync_dirs: [ tests ]
  region: us-east-1
  release: deployer-test
  sync_exclude:
  - .swp
  - .git
  - .DS_Store
  - README.md
  - config.yaml
  parameters:
    Environment: test-case
  tags:
    Environment: test-case
test:
  stack_name: deployer-test-case
  template: deployer/tests/cloudformation.yaml
  parameters: {}
"""



cloudformation = boto3.client('cloudformation', region_name="us-east-1")
simplestorageservice = boto3.client('s3', region_name="us-east-1")

class DeployerTestCase(unittest.TestCase):
    def test_version(self):
        #Checks if -v returns the version stored in the python file
        v = ""
        from __init__ import __version__ 
        try:
            v = subprocess.check_output(['python', deployerExecutor, '-v']).rstrip()
        except SystemExit as exit:
            if exit.code != 0:
                raise exit
        self.assertEqual(__version__, v)

    def test_help(self):
        #Checks if -h returns the help message
        output = ""
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-h'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit
        self.assertTrue("show this help message and exit" in output)

    def test_intialize(self):
        #Checks if --init creates a config & cloudformation folder
        try:
            output = subprocess.check_output(['python', deployerExecutor, '--init', 'temp'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit
        self.assertTrue(os.path.exists('temp/config') and os.path.exists('temp/cloudformation') )
        shutil.rmtree('temp', ignore_errors=True)

    #Checks if a basic stack can be created
    def test_create(self):
        reset_config()
        
        #Make sure no stack exists
        if(get_stack_status(testStackName) != "DELETE_COMPLETE"):
            cloudformation.delete_stack(StackName=testStackName)
        while(get_stack_status(testStackName) != "DELETE_COMPLETE"):
            time.sleep(apiHitRate)

        #Run deployer -x create
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-x', 'create', '-c', testStackConfig, '-s','test', '-D'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        self.assertEqual(get_stack_status(testStackName), 'CREATE_COMPLETE')

    #Checks if a basic stack can be deleted
    def test_delete(self):
        reset_config()

        #Create test stack
        if(get_stack_status(testStackName) == "DELETE_COMPLETE"):
            create_test_stack()


        time.sleep(apiHitRate)

        #Run deployer -x delete
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-x', 'delete', '-c', testStackConfig, '-s','test','-D'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        time.sleep(apiHitRate)

        #Wait for result
        while("IN_PROGRESS" in get_stack_status(testStackName)):
            time.sleep(apiHitRate)

        self.assertEqual(get_stack_status(testStackName), "DELETE_COMPLETE")


    def test_config_updater(self):
        reset_config()

        #Test whether config updater changes config file
        subprocess.check_output(['python', configUpdateExecutor, '-c', testStackConfig, '-u', json.dumps({"global":{'tags':{ 'Environment' : 'successful-config-update' }}})])
        data = {}
        with open(testStackConfig) as f:
            data = yaml.safe_load(f)
        if 'global' in data and 'tags' in data['global'] and 'Environment' in data['global']['tags']:
            data = data['global']['tags']['Environment']
        self.assertEqual('successful-config-update', data)

    def test_update(self):
        reset_config()
        create_test_stack()
        while("IN_PROGRESS" in get_stack_status(testStackName)):
            time.sleep(apiHitRate)
        subprocess.check_output(['python', configUpdateExecutor, '-c', testStackConfig, '-u', json.dumps({"global":{'tags':{ 'Environment' : 'stack-updated' }}})])
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-x', 'update', '-c', testStackConfig, '-s','test', '-D'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit


        self.assertEqual(get_stack_tag(testStackName, "Environment"), "stack-updated")

    def test_sync(self):
        reset_config()

        #Delete possible odd file
        simplestorageservice.delete_object(Bucket=testBucket, Key="deployer-test/tests/cloudformation.yaml")

        #Try to sync
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-x', 'sync', '-c', testStackConfig, '-s','test', '-D'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        s3obj = simplestorageservice.get_object(Bucket=testBucket, Key="deployer-test/tests/cloudformation.yaml")
        fullfillsCriteria = False
        if(s3obj['LastModified'] > datetime.now(UTC()) - timedelta(seconds=10)):
            fullfillsCriteria = True

        self.assertTrue(fullfillsCriteria)

#Used for UTC time
ZERO = timedelta(0)
class UTC(tzinfo):
  def utcoffset(self, dt):
    return ZERO
  def tzname(self, dt):
    return "UTC"
  def dst(self, dt):
    return ZERO


#Returns the status of a stack by name
def get_stack_status(stack):
    try:
        result = cloudformation.describe_stacks(StackName=stack)
        if 'Stacks' in result:
            if(len(result['Stacks']) > 0):
                return result['Stacks'][0]['StackStatus']
    except ClientError as e:
        if e.response['Error']['Code'] != "ValidationError":
            raise e
        else:
            return "DELETE_COMPLETE"

def get_stack_tag(stack, tag):
    cfnStack = cloudformation.describe_stacks(StackName=stack)['Stacks'][0]
    for cfnTag in cfnStack['Tags']:
        if cfnTag['Key'] == tag:
            return cfnTag['Value']
    return None

#Create test stack
def create_test_stack():
    try:
        result = cloudformation.describe_stacks(StackName=testStackName)
        if 'Stacks' in result:
            if(len(result['Stacks']) > 0):
                if(result['Stacks'][0]['StackStatus'] != "DELETE_COMPLETE"):
                    cloudformation.delete_stack(StackName=testStackName)
    except ClientError as e:
        if e.response['Error']['Code'] != "ValidationError":
            raise e
    while("IN_PROGRESS" in get_stack_status(testStackName)):
        time.sleep(apiHitRate)

    data = ""
    with open(testStackCloudFormation, 'r') as file:
        data = file.read()
    result = cloudformation.create_stack(StackName=testStackName, TemplateBody=data)

    while("IN_PROGRESS" in get_stack_status(testStackName)):
        time.sleep(apiHitRate)

    if 'StackId' in result:
        return True
    else:
        return False

def reset_config():
    with open(testStackConfig, "w") as config:
        config.write(testStackConfig_data)

def main():
    reset_config()
    unittest.main()
    cloudformation.delete_stack(StackName=testStackName)
    

if __name__ == "__main__":
    main()