import unittest
import __init__ as deployer
import boto3, json
import sys, subprocess, os, shutil, time
from botocore.exceptions import ClientError
import yaml
from datetime import tzinfo, timedelta, datetime

deployerExecutor = "./__init__.py"
configUpdateExecutor = "./config_updater.py"

apiHitRate = 0.25

#------------------------#
# CFN Testing Parameters #
#------------------------#
testStackName = "deployer-test-case"
testStackConfig = "./tests/config.yaml"
testStackCloudFormation = "./tests/cloudformation.yaml"

testBucket = "deployer-testing-us-east-1"

testStackConfig_data = """
global:
  sync_base: ./
  sync_dest_bucket: deployer-testing-us-east-1
  sync_dirs: [tests]
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
    Environment: stack-updated
test:
  stack_name: deployer-test-case
  template: tests/cloudformation.yaml
lambda:
  stack_name: deployer-test-case
  template: tests/cloudformation.yaml
  lambda_dirs: [ tests/lambda ]
timeout:
  stack_name: deployer-test-case
  template: tests/timeout.yaml
"""


cloudformation = boto3.client('cloudformation', region_name="us-east-1")
simplestorageservice = boto3.client('s3', region_name="us-east-1")


class DeployerTestCase(unittest.TestCase):
    def test_version(self):
        # Checks if -v returns the version stored in the python file
        v = ""
        from . import __version__
        try:
            v = subprocess.check_output(['python', deployerExecutor, '-v']).rstrip()
        except SystemExit as e:
            if e.code != 0:
                raise e
        self.assertEqual(__version__, v.decode())

    def test_help(self):
        # Checks if -h returns the help message
        output = ""
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-h'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit
        self.assertTrue("show this help message and exit" in str(output))

    def test_intialize(self):
        # Checks if --init creates a config & cloudformation folder
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
        if(get_stack_status(testStackName) != "NULL"):
            cloudformation.delete_stack(StackName=testStackName)
        while(get_stack_status(testStackName) != "NULL"):
            time.sleep(apiHitRate)

        #Run deployer -x create
        try:
            subprocess.check_output(['python', deployerExecutor, '-x', 'create', '-c', testStackConfig, '-s','test', '-D'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        self.assertEqual(get_stack_status(testStackName), 'CREATE_COMPLETE')

    #Checks if a basic stack can be deleted
    def test_delete(self):
        reset_config()

        #Create test stack
        if(get_stack_status(testStackName) == "NULL"):
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

        self.assertEqual(get_stack_status(testStackName), "NULL")


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

    def test_lambda(self):
        reset_config()
        print("You are here: " + str(os.getcwd()))
        print(subprocess.check_output(['ls', 'tests']))
        try:
            output = subprocess.check_output(['python', deployerExecutor,'-s', 'lambda', '-c', 'tests/config.yaml', '-x', 'sync', '-z', '-D'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        self.assertTrue(os.path.exists('tests/lambda.zip'))
       

    def test_sync(self):
        reset_config()

        # Delete possible odd file
        simplestorageservice.delete_object(Bucket=testBucket, Key="deployer-test/tests/cloudformation.yaml")

        # Try to sync
        try:
            subprocess.check_output(['python', deployerExecutor, '-x', 'sync', '-c', testStackConfig, '-s','test', '-D'])
        except SystemExit as e:
            if e.code != 0:
                raise e

        s3obj = simplestorageservice.get_object(Bucket=testBucket, Key="deployer-test/tests/cloudformation.yaml")
        self.assertTrue(s3obj['LastModified'] > datetime.now(UTC()) - timedelta(seconds=10))

    # Checks if a basic stack can be created
    def test_timeout(self):
        reset_config()

        # Make sure no stack exists
        if get_stack_status(testStackName) != "NULL":
            cloudformation.delete_stack(StackName=testStackName)
        while get_stack_status(testStackName) != "NULL":
            time.sleep(apiHitRate)

        # Run deployer -x create with timeout
        result = subprocess.call(['python', deployerExecutor, '-x', 'create', '-c', testStackConfig, '-s', 'timeout', '-T', '1'])
        self.assertEqual(result, 2)


class IntegrationLambdaTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(IntegrationLambdaTestCase, self).__init__(*args, **kwargs)
        self.client = boto3.client('cloudformation')
        self.stack_name = 'deployer-lambda'

    def stack_create(self):
        result = subprocess.call(['deployer', '-x', 'create', '-c', 'tests/config/lambda.yaml', '-s' 'create', '-P', 'Cli=create', '-yzD'])
        self.assertEqual(result, 0)

        stack = self.client.describe_stacks(StackName=self.stack_name)
        self.assertIn('Stacks', stack.keys())
        self.assertEquals(len(stack['Stacks']), 1)

        outputs = stack['Stacks'][0].get('Outputs', [])
        self.assertEquals(len(outputs), 1)

        func = [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Function']
        self.assertEquals(len(func), 1)

        client = boto3.client('lambda')
        resp = client.invoke(FunctionName=func[0])

        self.assertNotEquals(resp.get("Payload", None), None)
        payload = json.loads(resp['Payload'].read())
        self.assertEquals(payload.get("message", ''), "hello world")

    def stack_reset(self):
        try:
            stack = self.client.describe_stacks(StackName=self.stack_name)
            if len(stack.get('Stacks', [])) > 0:
                self.client.delete_stack(StackName=self.stack_name)
                self.stack_wait()
        except ClientError as e:
            self.assertIn('does not exist', e.message)

    def stack_wait(self):
        waiter = self.client.get_waiter('stack_delete_complete')
        waiter.wait(StackName=self.stack_name)

    def test_stack(self):
        self.stack_reset()
        self.stack_create()


class IntegrationStackTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(IntegrationStackTestCase, self).__init__(*args, **kwargs)
        self.client = boto3.client('cloudformation')
        self.stack_name = 'deployer-test'

    def stack_create(self):
        result = subprocess.call(['deployer', '-x', 'create', '-c', 'tests/config/test.yaml', '-s' 'create', '-P', 'Cli=create', '-D'])
        self.assertEqual(result, 0)

        stack = self.client.describe_stacks(StackName=self.stack_name)
        self.assertIn('Stacks', stack.keys())
        self.assertEquals(len(stack['Stacks']), 1)

        outputs = stack['Stacks'][0].get('Outputs', [])
        self.assertIn('create', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Cli'])
        self.assertIn('global', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Global'])
        self.assertIn('create', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Local'])
        self.assertIn('create', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Override'])
        self.assertIn('prod', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Release'])

        tags = stack['Stacks'][0].get('Tags', [])
        self.assertIn('create', [x['Value'] for x in tags if x['Key'] == 'Local'])
        self.assertIn('create', [x['Value'] for x in tags if x['Key'] == 'Override'])
        self.assertIn('deployer:caller', [x['Key'] for x in tags])
        self.assertIn('deployer:config', [x['Key'] for x in tags])
        self.assertIn('deployer:git:commit', [x['Key'] for x in tags])
        self.assertIn('deployer:git:origin', [x['Key'] for x in tags])
        self.assertIn('deployer:stack', [x['Key'] for x in tags])

    def stack_delete(self):
        result = subprocess.call(['deployer', '-x', 'delete', '-c', 'tests/config/test.yaml', '-s' 'update', '-D'])
        self.assertEqual(result, 0)

        try:
            stack = self.client.describe_stacks(StackName=self.stack_name)
            self.assertIn('Stacks', stack.keys())
            self.assertEquals(len(stack['Stacks']), 1)
            self.assertEquals(stack['Stacks'][0].get('StackStatus', ''), 'DELETE_IN_PROGRESS')
            self.stack_wait()
        except ClientError as e:
            self.assertIn('does not exist', e.message)

    def stack_reset(self):
        try:
            stack = self.client.describe_stacks(StackName=self.stack_name)
            if len(stack.get('Stacks', [])) > 0:
                self.client.delete_stack(StackName=self.stack_name)
                self.stack_wait()
        except ClientError as e:
            self.assertIn('does not exist', e.message)

    def stack_update(self):
        result = subprocess.call(['deployer', '-x', 'update', '-c', 'tests/config/test.yaml', '-s' 'update', '-P', 'Cli=update', '-D'])
        self.assertEqual(result, 0)

        stack = self.client.describe_stacks(StackName=self.stack_name)
        self.assertIn('Stacks', stack.keys())
        self.assertEquals(len(stack['Stacks']), 1)

        outputs = stack['Stacks'][0].get('Outputs', [])
        self.assertIn('update', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Cli'])
        self.assertIn('global', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Global'])
        self.assertIn('update', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Local'])
        self.assertIn('update', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Override'])
        self.assertIn('prod', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Release'])

        tags = stack['Stacks'][0].get('Tags', [])
        self.assertIn('update', [x['Value'] for x in tags if x['Key'] == 'Local'])
        self.assertIn('update', [x['Value'] for x in tags if x['Key'] == 'Override'])
        self.assertIn('deployer:caller', [x['Key'] for x in tags])
        self.assertIn('deployer:config', [x['Key'] for x in tags])
        self.assertIn('deployer:git:commit', [x['Key'] for x in tags])
        self.assertIn('deployer:git:origin', [x['Key'] for x in tags])
        self.assertIn('deployer:stack', [x['Key'] for x in tags])

    def stack_wait(self):
        waiter = self.client.get_waiter('stack_delete_complete')
        waiter.wait(StackName=self.stack_name)

    def test_stack(self):
        self.stack_reset()
        self.stack_create()
        self.stack_update()
        self.stack_delete()


class IntegrationStackSetTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(IntegrationStackSetTestCase, self).__init__(*args, **kwargs)
        self.client = boto3.client('cloudformation')
        self.stackset_name = 'deployer-stackset-test'

    def stackset_create(self):
        result = subprocess.call(['deployer', '-x', 'create', '-c', 'tests/config/stackset.yaml', '-s' 'create', '-P', 'Cli=create', '-D'])
        self.assertEqual(result, 0)

        instances = self.client.list_stack_instances(StackSetName=self.stackset_name)
        accounts = set([x['Account'] for x in instances.get('Summaries', [])])
        regions = set([x['Region'] for x in instances.get('Summaries', [])])
        self.assertEquals(len(accounts), 1)
        self.assertEquals(len(regions), 1)

        for instance in [x for x in instances.get('Summaries', [])]:
            client = boto3.client('cloudformation', region_name=instance['Region'])
            stack = client.describe_stacks(StackName=instance['StackId'])
            self.assertIn('Stacks', stack.keys())
            self.assertEquals(len(stack['Stacks']), 1)

            outputs = stack['Stacks'][0].get('Outputs', [])
            self.assertIn('create', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Cli'])
            self.assertIn('global', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Global'])
            self.assertIn('create', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Local'])
            self.assertIn('create', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Override'])
            self.assertIn('prod', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Release'])

            tags = stack['Stacks'][0].get('Tags', [])
            self.assertIn('create', [x['Value'] for x in tags if x['Key'] == 'Local'])
            self.assertIn('create', [x['Value'] for x in tags if x['Key'] == 'Override'])
            self.assertIn('deployer:caller', [x['Key'] for x in tags])
            self.assertIn('deployer:config', [x['Key'] for x in tags])
            self.assertIn('deployer:git:commit', [x['Key'] for x in tags])
            self.assertIn('deployer:git:origin', [x['Key'] for x in tags])
            self.assertIn('deployer:stack', [x['Key'] for x in tags])

    def stackset_delete(self):
        result = subprocess.call(['deployer', '-x', 'delete', '-c', 'tests/config/stackset.yaml', '-s' 'update', '-D'])
        self.assertEqual(result, 0)

        self.assertRaises(ClientError, self.client.describe_stack_set, StackSetName=self.stackset_name)

    def stackset_reset(self):
        try:
            instances = self.client.list_stack_instances(StackSetName=self.stackset_name)
            accounts = list(set([x['Account'] for x in instances.get('Summaries', [])]))
            regions = list(set([x['Region'] for x in instances.get('Summaries', [])]))

            if regions and accounts:
                op = self.client.delete_stack_instances(
                    StackSetName=self.stackset_name,
                    Accounts=accounts,
                    Regions=regions,
                    RetainStacks=False
                ).get('OperationId', None)

                desired = ['SUCCEEDED', 'FAILED', 'STOPPED']
                status = self.client.describe_stack_set_operation(StackSetName=self.stackset_name, OperationId=op)
                while status['StackSetOperation']['Status'] not in desired:
                    time.sleep(5)
                    status = self.client.describe_stack_set_operation(StackSetName=self.stackset_name, OperationId=op)

                self.assertEquals(status['StackSetOperation']['Status'], 'SUCCEEDED')

            self.client.delete_stack_set(StackSetName=self.stackset_name)
        except ClientError as e:
            self.assertIn('StackSetNotFoundException', e.message)

    def stackset_update(self):
        result = subprocess.call(['deployer', '-x', 'update', '-c', 'tests/config/stackset.yaml', '-s' 'update', '-P', 'Cli=update', '-D'])
        self.assertEqual(result, 0)

        instances = self.client.list_stack_instances(StackSetName=self.stackset_name)
        accounts = set([x['Account'] for x in instances.get('Summaries', [])])
        regions = set([x['Region'] for x in instances.get('Summaries', [])])
        self.assertEquals(len(accounts), 1)
        self.assertEquals(len(regions), 2)

        for instance in [x for x in instances.get('Summaries', [])]:
            client = boto3.client('cloudformation', region_name=instance['Region'])
            stack = client.describe_stacks(StackName=instance['StackId'])
            self.assertIn('Stacks', stack.keys())
            self.assertEquals(len(stack['Stacks']), 1)

            outputs = stack['Stacks'][0].get('Outputs', [])
            self.assertIn('update', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Cli'])
            self.assertIn('global', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Global'])
            self.assertIn('update', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Local'])
            self.assertIn('update', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Override'])
            self.assertIn('prod', [x['OutputValue'] for x in outputs if x['OutputKey'] == 'Release'])

            tags = stack['Stacks'][0].get('Tags', [])
            self.assertIn('update', [x['Value'] for x in tags if x['Key'] == 'Local'])
            self.assertIn('update', [x['Value'] for x in tags if x['Key'] == 'Override'])
            self.assertIn('deployer:caller', [x['Key'] for x in tags])
            self.assertIn('deployer:config', [x['Key'] for x in tags])
            self.assertIn('deployer:git:commit', [x['Key'] for x in tags])
            self.assertIn('deployer:git:origin', [x['Key'] for x in tags])
            self.assertIn('deployer:stack', [x['Key'] for x in tags])

    def test_stackset(self):
        self.stackset_reset()
        self.stackset_create()
        self.stackset_update()
        self.stackset_delete()


# Used for UTC time
ZERO = timedelta(0)
class UTC(tzinfo):
  def utcoffset(self, dt):
    return ZERO
  def tzname(self, dt):
    return "UTC"
  def dst(self, dt):
    return ZERO


# Returns the status of a stack by name
def get_stack_status(stack):
    try:
        result = cloudformation.describe_stacks(StackName=stack)
        if 'Stacks' in result:
            if len(result['Stacks']) > 0:
                if result['Stacks'][0]['StackStatus'] == "DELETE_COMPLETE":
                    return "NULL"
                return result['Stacks'][0]['StackStatus']
    except ClientError as e:
        if e.response['Error']['Code'] != "ValidationError":
            raise e
        else:
            return "NULL"


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
                if(result['Stacks'][0]['StackStatus'] != "NULL"):
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