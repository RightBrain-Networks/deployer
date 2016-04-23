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

    def get_config(self): 
         with open(self.config) as f:
             data = yaml.load(f)
         return data

    def construct_template_url(self):
        config = self.get_config()
        url_string = "https://{}.amazonaws.com/{}/{}/{}"
        if config['global']['region'] == 'us-east-1':
            s3_endpoint = 's3'
        else:
            s3_endpoint = "s3-%s" % config['global']['region']
        self.template_url = url_string.format(
            s3_endpoint,
            config['global']['parameters']['CloudToolsBucket'],
            self.release,
            config[self.environment]['template'])
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
        sleep(10)
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

class NetworkStack(AbstractCloudFormation):
    def __init__(self, profile, config):
        self.profile = profile
        self.environment = 'Network'
        self.config = config
        data = self.get_config()
        self.region = data['global']['region']
        self.stack_name = data[self.environment]['stack_name']
        self.release = str(data[self.environment]['release']).replace('/','.')
        self.template = data[self.environment]['template']
        self.template_url = self.construct_template_url()
        self.session = Session(profile_name=profile,region_name=self.region)
        self.client = self.session.client('cloudformation')
        self.ec2 = self.session.client('ec2')
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
        print "Parameters Created"
        return params

    def delete_stack(self):
        for output in self.get_outputs():
            if output['OutputKey'] == "VPC":
                VPC_ID = output['OutputValue']
        vpc_endpoints = self.ec2.describe_vpc_endpoints(
            Filters=[
                { "Name": "vpc-id",
                  "Values": [ VPC_ID ]
                }
            ]
        )['VpcEndpoints']
        endpoint_ids = []
        for endpoint in vpc_endpoints:
            endpoint_ids.append(endpoint['VpcEndpointId'])
        
        endpoint_resp = self.ec2.delete_vpc_endpoints(
            VpcEndpointIds=endpoint_ids
        )
        resp = self.client.delete_stack(StackName=self.stack_name)
        return True
                

class EnvironmentStack(AbstractCloudFormation):
    def __init__(self, profile, config, environment):
        self.profile = profile
        self.environment = environment
        self.config = config
        data = self.get_config()
        self.region = data['global']['region']
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

    def delete_stack(self):
        resp = self.client.delete_stack(StackName=self.stack_name)
        return True

