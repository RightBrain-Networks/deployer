import unittest
import __init__ as deployer
import boto3, json
import sys, subprocess, os, shutil, time
from botocore.exceptions import ClientError


deployerExecutor = "deployer/__init__.py"
configUpdateExecutor = "deployer/config_updater.py"

class DeployerTestCase(unittest.TestCase):
    def test_version(self):
        #Checks if -v returns the version stored in the python file
        v = ""
        from deployer import __version__ 
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


    def test_create(self):
        #Checks if a basic stack can be created
        stack = "deployer-test-case"
        client = boto3.client('cloudformation')

        #Make sure no stack exists
        if(get_stack_status(stack) != "DELETE_COMPLETE"):
            client.delete_stack(StackName=stack)
        while(get_stack_status(stack) != "DELETE_COMPLETE"):
            time.sleep(0.25)

        #Run deployer -x create
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-x', 'create', '-c', 'deployer/tests/create/config.yaml', '-s','test'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        self.assertEqual(get_stack_status(stack), 'CREATE_COMPLETE')

    def test_delete(self):
        #Checks if a basic stack can be deleted
        stack = "deployer-test-case"
        client = boto3.client('cloudformation')


        #Create test stack
        if(get_stack_status(stack) == "DELETE_COMPLETE"):
            create_test_stack()
        while("IN_PROGRESS" in get_stack_status(stack)):
            time.sleep(0.25)

        #Run deployer -x delete
        try:
            output = subprocess.check_output(['python', deployerExecutor, '-x', 'delete', '-c', 'deployer/tests/create/config.yaml', '-s','test'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit

        #Wait for result
        while("IN_PROGRESS" in get_stack_status(stack)):
            time.sleep(0.25)

        self.assertEqual(get_stack_status(stack), "DELETE_COMPLETE")


    def test_config_updater(self):
        self.assertTrue(False)
        #Test whether config updater changes config file
        subprocess.check_output(['python', configUpdateExecutor, '-c', 'deployer/tests/create/config.yaml', '-u', json.dumps({'tags':{ 'Environment' : 'successful-config-update' }})])
        data = ""
        with open('deployer/tests/create/config.yaml', 'r') as file:
            data = file.read()
        self.assertTrue('successful-config-update' in data)

    def test_update(self):
        self.assertTrue(False)

    def test_sync(self):
        self.assertTrue(False)

def get_stack_status(stack):
    client = boto3.client('cloudformation')

    try:
        result = client.describe_stacks(StackName=stack)
        if 'Stacks' in result:
            if(len(result['Stacks']) > 0):
                return result['Stacks'][0]['StackStatus']
    except ClientError as e:
        if e.response['Error']['Code'] != "ValidationError":
            raise e
        else:
            return "DELETE_COMPLETE"

def create_test_stack():
    stack = "deployer-test-case"
    client = boto3.client('cloudformation')

    try:
        result = client.describe_stacks(StackName=stack)
        if 'Stacks' in result:
            if(len(result['Stacks']) > 0):
                if(result['Stacks'][0]['StackStatus'] != "DELETE_COMPLETE"):
                    client.delete_stack(StackName=stack)
    except ClientError as e:
        if e.response['Error']['Code'] != "ValidationError":
            raise e

    data = ""
    with open('deployer/tests/create/cloudformation.yaml', 'r') as file:
        data = file.read()
    result = client.create_stack(StackName=stack, TemplateBody=data)
    if 'StackId' in result:
        return True
    else:
        return False

    


def main():
    unittest.main()

if __name__ == "__main__":
    main()