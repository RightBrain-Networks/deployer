#!/usr/bin/env python

import boto3
from boto3.session import Session
import yaml
import json
from abc import ABCMeta, abstractmethod, abstractproperty
from time import sleep 

class AbstractCloudFormation(object):
    __metaclass__ = ABCMeta
   
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def build_params(self):
        # Method to build parameters file
        pass

    @abstractmethod
    def delete_stack(self):
        pass 
     
    def get_outputs(self):
        resp = self.client.describe_stacks(
                   StackName=self.stack_name)
        self.outputs = resp['Stacks'][0]['Outputs']
        return self.outputs

    def reload_stack_status(self): 
        try:
            resp = self.client.describe_stacks(
                StackName=self.stack_name)
            self.stack_status = resp['Stacks'][0]['StackStatus']
        except Exception as e:
            self.stack_status = 'False'
        return self.stack_status

    def reload_change_set_status(self, change_set_name): 
        try:
            resp = self.client.describe_change_set(
                ChangeSetName=change_set_name,
                StackName=self.stack_name
            )
            self.change_set_status = resp['Status']
        except Exception as e:
            self.change_set_status = 'False'
        return self.change_set_status

    def get_config(self): 
        with open(self.config) as f:
            data = yaml.load(f)
        return data

    def get_region(self):
        config = self.get_config()
        region = None
        key = 'region'
        if key in config['global']:
            region = config['global'][key]
        if key in config[self.environment]:
            region = config[self.environment][key]
        return region

    def construct_template_url(self):
        alt = 'full_template_url'
        config = self.get_config()
        if alt in config[self.environment]:
            self.template_url = config[self.environment][alt]
        else:
            url_string = "https://{}.amazonaws.com/{}/{}/{}"
            self.template_bucket = config[self.environment]['template_bucket']
            self.template = config[self.environment]['template']
            if self.region == 'us-east-1':
                s3_endpoint = 's3'
            else:
                s3_endpoint = "s3-%s" % self.region
            self.template_url = url_string.format(
                s3_endpoint,
                self.template_bucket,
                self.release,
                self.template)
        return self.template_url
 

    def create_stack(self):
        # create the Network stack 
        resp = self.client.create_stack(
            StackName=self.stack_name,
            TemplateURL=self.template_url,
            Parameters=self.build_params(),
            Capabilities=[
                'CAPABILITY_IAM'
            ] 
        )
        print "Creation Started"
        print "Waiting for Create Complete"
        self.reload_stack_status()
        while self.stack_status != 'CREATE_COMPLETE':
            sleep(30)
            status = self.reload_stack_status()
            print status
            if status in [ 'CREATE_FAILED', 'ROLLBACK_IN_PROGRESS', 'ROLLBACK_COMPLETE', 'ROLLBACK_FAILED' ]:
                raise RuntimeError("Create stack Failed")
           
    
    def update_stack(self):
        # create the Network stack 
        if self.stack_status: 
            resp = self.client.update_stack(
                StackName=self.stack_name,
                TemplateURL=self.template_url,
                Parameters=self.build_params(),
                Capabilities=[
                    'CAPABILITY_IAM'
                ] 
            )
            print "Update Started"
            sleep(10)
            self.reload_stack_status()
            while self.stack_status != 'UPDATE_COMPLETE':
                sleep(30)
                status = self.reload_stack_status()
                print status
                if status in [ 'UPDATE_FAILED', 'UPDATE_ROLLBACK_IN_PROGRESS', 'UPDATE_ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_FAILED' ]:
                    raise RuntimeError("Update stack Failed")
        else:
            raise RuntimeError("Stack does not exist")

    def delete_stack(self):
        resp = self.client.delete_stack(StackName=self.stack_name)
        return True

    def get_change_set(self, change_set_name, change_set_description):
        # create the change set
        if self.stack_status: 
            resp = self.client.create_change_set(
                StackName=self.stack_name,
                TemplateURL=self.template_url,
                Parameters=self.build_params(),
                Capabilities=[
                    'CAPABILITY_IAM'
                ],
                ChangeSetName=change_set_name, 
                Description=change_set_description
            )
            print "Change Set Started: %s" % resp['Id']
            sleep(5)
            self.change_set_status = self.reload_change_set_status(change_set_name)
            while self.change_set_status != 'CREATE_COMPLETE':
                sleep(5)
                status = self.reload_change_set_status(change_set_name)
                print status
                if status == 'FAILED':
                    raise RuntimeError("Change set Failed")
            self.print_change_set(change_set_name, change_set_description)
        else:
            raise RuntimeError("Stack does not exist")

    
    def print_change_set(self, change_set_name, change_set_description):    
        resp = self.client.describe_change_set(
            ChangeSetName=change_set_name,
            StackName=self.stack_name
        )
        self.changes = resp['Changes']
        print "==================================== Change ===================================" 
        print "= Action |\tLogicalId\t|\tResourceType\t|\tReplacement\t="
        for change in self.changes:
            print "| %s |\t%s\t|\t%s\t|\t%s\t|" % (
                change['ResourceChange']['Action'],
                change['ResourceChange']['LogicalResourceId'],
                change['ResourceChange']['ResourceType'],
                change['ResourceChange']['Replacement']
            )
                 
            

class EnvironmentStack(AbstractCloudFormation):
    def __init__(self, profile, config, environment):
        self.profile = profile
        self.environment = environment
        self.config = config
        data = self.get_config()
        self.region = self.get_region()
        self.stack_name = data[self.environment]['stack_name']
        self.release = str(data[self.environment]['release']).replace('/','.')
        self.template = data[self.environment]['template']
        self.template_url = self.construct_template_url()
        self.session = Session(profile_name=profile,region_name=self.region)
        self.client = self.session.client('cloudformation')
        self.reload_stack_status()

    def build_params(self):
        # create parameters from the config.yml file
        self.parameter_file = "%s-params.json" % self.environment
        config = self.get_config()
        params = []
        params.append({ "ParameterKey": "Environment", "ParameterValue": self.environment })
        params.append({ "ParameterKey": "Release", "ParameterValue": self.release })
        # Order of the environments is priority on overwrites, authoritative is last
        for env in ['global', self.environment]:
            for param_key, param_value in config[env]['parameters'].iteritems():
                count = 0 
                overwritten = False
                for param_item in params:
                    if param_item['ParameterKey'] == param_key:
                        params[count] = { "ParameterKey": param_key, "ParameterValue": param_value } 
                        overwritten = True 
                    count += 1
                if not overwritten:
                    params.append({ "ParameterKey": param_key, "ParameterValue": param_value })
            try:
                for param_key, lookup_struct in config[env]['lookup_parameters'].iteritems():
                    stack = EnvironmentStack(self.profile, self.config, lookup_struct['Stack'])
                    stack.get_outputs()
                    for output in stack.outputs:
                        if output['OutputKey'] == lookup_struct['OutputKey']:
                            params.append({ "ParameterKey": param_key, "ParameterValue": output['OutputValue'] })
            except:
                pass
        print "Parameters Created"
        return params


