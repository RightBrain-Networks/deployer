#!/usr/bin/env python
import git
import json
import pytz
import re
import ruamel.yaml
import signal
from boto3.session import Session
from botocore.exceptions import ClientError, WaiterError
from tabulate import tabulate
from abc import ABCMeta, abstractmethod
from time import sleep 
from datetime import datetime 
from parse import parse
from deployer.decorators import retry
from deployer.logger import logger
from collections import defaultdict

# Used to enable parsing of yaml templates using shorthand notation
def general_constructor(loader, tag_suffix, node):
    return node.value

ruamel.yaml.SafeLoader.add_multi_constructor(u'!',general_constructor)


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

    def get_repository(self):
        try:
            return git.Repo(self.base, search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            return None

    def get_repository_origin(self):
        if self.repository:
            try:
                origin = self.repository.remotes.origin.url
                return origin.split('@', 1)[-1] if origin else None
            except (StopIteration, ValueError):
                return None
        else:
            return None

    def upsert(self):
        self.update() if self.check_stack_exists() else self.create()

    def create(self):
        signal.signal(signal.SIGINT, self.cancel_create)
        if not self.transforms:
            self.create_stack()
        else:
            start_time = datetime.now(pytz.utc)
            change_set_name = "{0}-1".format(self.get_config_att('change_prefix'))
            self.get_change_set(change_set_name, "Deployer Automated", 'CREATE')
            self.execute_change_set(change_set_name)
            self.create_waiter(start_time)

    def update(self):
        signal.signal(signal.SIGINT, self.cancel_update)
        if not self.transforms:
            self.update_stack()
        else:
            latest_change = self.get_latest_change_set_name()
            if latest_change:
                change_number = int(latest_change.strip(self.get_config_att('change_prefix') + '-'))
                change_number += 1
            else:
                change_number = 1
            start_time = datetime.now(pytz.utc)
            change_set_name = "{0}-{1}".format(self.get_config_att('change_prefix'),change_number)
            self.get_change_set(change_set_name, "Deployer Automated", 'UPDATE')
            self.execute_change_set(change_set_name)
            self.update_waiter(start_time)

    def cancel_create(self, signal, frame):
        logger.critical('Process Interupt')
        logger.critical('Deleteing Stack: %s' % self.stack_name)
        self.delete_stack()
        exit(1)

    def cancel_update(self, signal, frame):
        logger.critical('Process Interupt')
        logger.critical('Cancelling Stack Update: %s' % self.stack_name)
        self.client.cancel_update_stack(RoleARN=self.role, StackName=self.stack_name)
        exit(1)

    @retry(ClientError,logger=logger)
    def get_outputs(self):
        resp = self.client.describe_stacks(RoleARN=self.role, StackName=self.stack_name)
        self.outputs = resp['Stacks'][0]['Outputs']
        return self.outputs

    @retry(ClientError,tries=6,logger=logger)
    def reload_stack_status(self): 
        try:
            resp = self.client.describe_stacks(RoleARN=self.role, StackName=self.stack_name)
            self.stack_status = resp['Stacks'][0]['StackStatus']
        except Exception as e:
            self.stack_status = 'False'
        return self.stack_status

    def reload_change_set_status(self, change_set_name): 
        try:
            resp = self.client.describe_change_set(
                RoleARN=self.role, 
                ChangeSetName=change_set_name,
                StackName=self.stack_name
            )
            self.change_set_status = resp['Status']
        except Exception as e:
            self.change_set_status = 'False'
        return self.change_set_status

    def get_config(self): 
        with open(self.config_file) as f:
            data = ruamel.yaml.safe_load(f)
        return data

    def get_config_att(self, key, default=None, required=False):
        base = self.config.get('global', {}).get(key, None)
        base = self.config.get(self.stack).get(key, base)
        if required and base is None:
            logger.error("Required attribute '{}' not found in config '{}'.".format(key, self.config_file))
            exit(3)
        return base if base is not None else default

    def construct_template_url(self):
        alt = 'full_template_url'
        if alt in self.config[self.stack]:
            self.template_url = self.config[self.stack][alt]
        elif self.get_template_bucket() is None:
            return None
        else:
            s3 = self.session.client('s3')
            url_string = "https://{}.amazonaws.com/{}/{}/{}"
            self.template_bucket = self.get_template_bucket()
            s3_endpoint = 's3' if self.region == 'us-east-1' else "s3-%s" % self.region
            try:
                s3.head_object(Bucket=self.template_bucket, Key="{}/{}".format(self.release, self.template))
                template_url = url_string.format(s3_endpoint, self.template_bucket, self.release, self.template)
                self.template_url = template_url
            except ClientError:
                self.template_url = None
        return self.template_url

    def get_template_bucket(self):
        bucket = self.get_config_att('template_bucket')
        if not bucket:
            ssm = self.session.client('ssm')
            try:
                name = '/global/buckets/cloudtools/name'
                return ssm.get_parameter(Name=name).get('Parameter', {}).get('Value', None)
            except ClientError:
                return None
        else:
            return bucket

    def get_template_file(self):
        if 'template' in self.config[self.stack]:
            return self.config[self.stack]['template']
        else:
            format_string = "http://{sub}.amazonaws.com/{bucket}/{release}/{template}"
            return parse(format_string, self.template_url)['template']

    def get_template_body(self):
        bucket = self.get_config_att('template_bucket')
        if not bucket:
            try:
                with open(self.template, 'r') as f:
                    return f.read()
            except Exception as e:
                logger.warning("Failed to read template file")
                return None
        else:
            return None

    def construct_tags(self): 
        tags = self.get_config_att('tags')
        if tags:
            tags = [ { 'Key': key, 'Value': value } for key, value in tags.items() ] 
            if len(tags) > 47:
                raise ValueError('Resources tag limit is 50, you have provided more than 47 tags. Please limit your tagging, save room for name and deployer tags.')
        else:
            tags = []
        tags.append({'Key': 'deployer:stack', 'Value': self.stack})
        tags.append({'Key': 'deployer:caller', 'Value': self.identity_arn})
        tags.append({'Key': 'deployer:git:commit', 'Value': self.commit})
        tags.append({'Key': 'deployer:git:origin', 'Value': self.origin})
        tags.append({'Key': 'deployer:config', 'Value': self.config_file.replace('\\', '/')})
        return tags

    def create_stack(self):
        # create the stack 
        start_time = datetime.now(pytz.utc)
        args = {
            "StackName": self.stack_name,
            "Parameters": self.build_params(),
            "DisableRollback": self.disable_rollback,
            "Tags": self.construct_tags(),
            "Capabilities": [
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ]
        }
        args.update({"RoleARN": self.role}) if self.role else logger.debug("Not using deployment role!")
        args.update({'TemplateBody': self.template_body} if self.template_body else {"TemplateURL": self.template_url})

        args.update({'TimeoutInMinutes': self.timeout}) if self.timeout else logger.debug("Not using timeout!")
        if self.template_body:
            logger.info("Using local template due to null template bucket")
        self.client.create_stack(**args)
        self.create_waiter(start_time)
        

    def create_waiter(self, start_time):
        waiter = self.client.get_waiter('stack_create_complete')
        logger.info("Creation Started")
        sleep(5)
        logger.info(self.reload_stack_status())
        if self.print_events:
            try:
                self.output_events(start_time, 'create')
            except RuntimeError as e:
                if self.timed_out:
                    logger.error('Stack creation exceeded timeout of {} minutes and was aborted.'.format(self.timeout))
                    exit(2)
                else:
                    raise e
        else:
            try:
                waiter.wait(RoleARN=self.role, StackName=self.stack_name)
            except WaiterError as e:
                status = self.reload_stack_status()
                logger.info(status)
                self.output_events(start_time, 'create')
        logger.info(self.reload_stack_status())
           
    
    def update_stack(self):
        # update the stack 
        waiter = self.client.get_waiter('stack_update_complete')
        start_time = datetime.now(pytz.utc)
        args = {
            "StackName": self.stack_name,
            "Parameters": self.build_params(),
            "Tags": self.construct_tags(),
            "Capabilities": [
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ]
        }
        args.update({"RoleARN": self.role}) if self.role else logger.debug("Not using deployment role!")
        args.update({'TemplateBody': self.template_body} if self.template_body else {"TemplateURL": self.template_url})
        if self.template_body:
            logger.info("Using local template due to null template bucket")
        if self.stack_status:
            try:
                self.client.update_stack(**args)
                self.update_waiter(start_time)
            except ClientError as e:
                if 'No updates are to be performed' in e.response['Error']['Message']:
                    logger.warning('No updates are to be performed')
                else:
                    raise e
        else:
            raise RuntimeError("Stack does not exist")

    def update_waiter(self, start_time):
        waiter = self.client.get_waiter('stack_update_complete')
        logger.info("Update Started")
        sleep(5)
        logger.info(self.reload_stack_status())
        if self.print_events:
            self.output_events(start_time, 'update')
        else:
            try:
                waiter.wait(RoleARN=self.role, StackName=self.stack_name)
            except WaiterError as e:
                status = self.reload_stack_status()
                logger.info(status)
                self.output_events(start_time, 'update')
            logger.info(self.reload_stack_status())

    def output_events(self, start_time, action):
        update_time = start_time
        headers = [ 'Time', 'Status', 'Type', 'Logical ID', 'Status Reason' ]
        if action == 'create':
            END_STATUS = 'CREATE_COMPLETE'
        elif action == 'update':
            END_STATUS = 'UPDATE_COMPLETE'
        count = 0
        while self.stack_status != END_STATUS:
            status = self.reload_stack_status()
            table = []
            sleep(15)
            events = self.client.describe_stack_events(RoleARN=self.role, StackName=self.stack_name)
            events = events['StackEvents']
            events.reverse()
            for event in events:
                if event['Timestamp'] > start_time and event['Timestamp'] > update_time:
                    reason = event.get('ResourceStatusReason', '')
                    if reason == 'Stack creation time exceeded the specified timeout. Rollback requested by user.':
                        self.timed_out = True
                    table.append([
                        event['Timestamp'].strftime('%Y/%m/%d %H:%M:%S'),
                        event['ResourceStatus'],
                        event['ResourceType'],
                        event['LogicalResourceId'],
                        reason
                    ])
            update_time = datetime.now(pytz.utc) 
            if len(table) > 0:
                if count == 0:
                    print(tabulate(table,headers,tablefmt='simple'))
                else:
                    print(tabulate(table,[],tablefmt='plain'))
            if action == 'create':
                if status in [ 'CREATE_FAILED', 'ROLLBACK_IN_PROGRESS', 'ROLLBACK_COMPLETE', 'ROLLBACK_FAILED' ]:
                    raise RuntimeError("Create stack Failed")
            elif action == 'update':
                if status in [ 'UPDATE_FAILED', 'UPDATE_ROLLBACK_IN_PROGRESS', 'UPDATE_ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_FAILED' ]:
                    raise RuntimeError("Update stack Failed")
            count += 1

    def delete_stack(self):
        args = { "StackName" : self.stack_name }
        args.update({"RoleARN": self.role}) if self.role else logger.debug("Not using deployment role!")
        self.client.delete_stack(**args)
        logger.info(self.colors['error'] + "Sent delete request to stack" + self.colors['reset'])
        return True

    def get_latest_change_set_name(self):
        resp = {}
        latest = None
        while 'NextToken' in resp or latest == None:
            if 'NextToken' in resp:
                resp = self.client.list_change_sets(
                    RoleARN=self.role, 
                    StackName=self.stack_name,
                    NextToken=resp['NextToken']
                )
            else:
                resp = self.client.list_change_sets(
                    RoleARN=self.role, 
                    StackName=self.stack_name
                )
            for change in resp['Summaries']:
                if not latest:
                    latest = change
                if change['CreationTime'] > latest['CreationTime']:
                    latest = change
            if resp['Summaries'] == []:
                return None
        return latest['ChangeSetName']

    def get_change_set(self, change_set_name, change_set_description, change_set_type):
        # create the change set
        if self.stack_status: 
            resp = self.client.create_change_set(
                RoleARN=self.role, 
                StackName=self.stack_name,
                TemplateURL=self.template_url,
                Parameters=self.build_params(),
                Capabilities=[
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM',
                    'CAPABILITY_AUTO_EXPAND'
                ],
                ChangeSetName=change_set_name, 
                Description=change_set_description,
                ChangeSetType=change_set_type
            )
            logger.info("Change Set Started: %s" % resp['Id'])
            sleep(5)
            self.change_set_status = self.reload_change_set_status(change_set_name)
            while self.change_set_status != 'CREATE_COMPLETE':
                sleep(10)
                status = self.reload_change_set_status(change_set_name)
                logger.info(status)
                if status == 'FAILED':
                    raise RuntimeError("Change set Failed")
            self.print_change_set(change_set_name, change_set_description)
        else:
            raise RuntimeError("Stack does not exist")

    def execute_change_set(self, change_set_name):
        resp = self.client.execute_change_set(
            RoleARN=self.role, 
            ChangeSetName=change_set_name,
            StackName=self.stack_name
        )
    
    def print_change_set(self, change_set_name, change_set_description):    
        resp = self.client.describe_change_set(
            RoleARN=self.role, 
            ChangeSetName=change_set_name,
            StackName=self.stack_name
        )
        self.changes = resp['Changes']
        print("==================================== Change ===================================")
        headers = ["Action","LogicalId","ResourceType","Replacement"]
        table = []
        for change in self.changes:
            row = []
            row.append(change['ResourceChange']['Action'])
            row.append(change['ResourceChange']['LogicalResourceId'])
            row.append(change['ResourceChange']['ResourceType'])
            if 'Replacement' in change['ResourceChange']:
                row.append(change['ResourceChange']['Replacement'])
            else:
                row.append('')
            table.append(row)
        print(tabulate(table, headers, tablefmt='simple'))

    def check_stack_exists(self):
        try:
            self.client.describe_stacks(RoleARN=self.role, StackName=self.stack_name)
            return True
        except ClientError:
            return False

    def describe(self):
        try:
            return self.client.describe_stacks(RoleARN=self.role, StackName=self.stack_name)['Stacks'][0]
        except ClientError:
            return {}
            

import pdb

class Stack(AbstractCloudFormation):
    def __init__(self, profile, config_file, stack, disable_rollback=False, print_events=False, timeout=None, params=None, colors= defaultdict(lambda: '')):
        self.profile = profile
        self.stack = stack
        self.config_file = config_file
        self.disable_rollback = disable_rollback
        self.print_events = print_events
        self.config = self.get_config()
        self.stack_name = self.get_config_att('stack_name', required=True)
        self.base = self.get_config_att('sync_base', '.')
        self.session = Session(profile_name=profile,region_name=self.get_config_att('region'))
        self.role = self.get_config_att('deployment_role')
        self.repository = self.get_repository()
        self.region = self.session.region_name
        self.commit = self.repository.head.object.hexsha if self.repository else 'null'
        self.origin = self.get_repository_origin() if self.repository else 'null'
        self.release = self.get_config_att('release', self.commit).replace('/','.')
        self.template = self.get_config_att('template', required=True)
        self.template_url = self.construct_template_url()
        self.template_file = self.get_template_file()
        self.template_body = self.get_template_body()
        self.timeout = timeout or self.get_config_att('timeout')
        self._timed_out = False
        self.transforms = self.get_config_att('transforms')
        self.client = self.session.client('cloudformation')
        self.colors = colors           
        self.sts = self.session.client('sts')
        self.identity_arn = self.sts.get_caller_identity().get('Arn', '')
        self.reload_stack_status()
        self.params = params or {}

    def build_params(self):
        # create parameters from the config.yml file
        self.parameter_file = "%s-params.json" % self.stack
        expanded_params = []
        expanded_params.append({ "ParameterKey": "Release", "ParameterValue": self.release })
        # Order of the stacks is priority on overwrites, authoritative is last
        # Here we loop through all of the params in the config file, we need to 
        # create a array of parameter objects, we have to loop through our array 
        # to ensure we dont already have one of that key.
        for env in ['global', self.stack]:
            if 'parameters' in self.config.get(env, {}):
                logger.debug("env {0} has parameters: {1}".format(env, self.config[env]['parameters']))
                for param_key, param_value in self.config[env]['parameters'].items():
                    count = 0 
                    overwritten = False
                    param_xform = ','.join(param_value) if isinstance(param_value, list) else param_value
                    for param_item in expanded_params:
                        if param_item['ParameterKey'] == param_key:
                            expanded_params[count] = { "ParameterKey": param_key, "ParameterValue": param_xform } 
                            overwritten = True 
                        count += 1
                    if not overwritten:
                        expanded_params.append({ "ParameterKey": param_key, "ParameterValue": param_xform })
            if 'lookup_parameters' in self.config.get(env, {}):
                for param_key, lookup_struct in self.config[env]['lookup_parameters'].items():
                    stack = Stack(self.profile, self.config_file, lookup_struct['Stack'])
                    stack.get_outputs()
                    for output in stack.outputs:
                        if output['OutputKey'] == lookup_struct['OutputKey']:
                            expanded_params.append({ "ParameterKey": param_key, "ParameterValue": output['OutputValue'] })

        # Remove overridden parameters and set them based on the override
        # provided. Explicit overrides take priority over anything in the
        # configuration files.
        expanded_params = [x for x in expanded_params if x['ParameterKey'] not in self.params.keys()]
        expanded_params += [{"ParameterKey": x, "ParameterValue": self.params[x]} for x in self.params.keys()]

        # Here we restrict the returned parameters to only the ones that the
        # template accepts by copying expanded_params into return_params and removing
        # the item in question from return_params
        logger.debug("expanded_params: {0}".format(expanded_params))
        return_params = list(expanded_params)
        with open(self.template_file, 'r') as template_file:
            if re.match(".*\.json",self.template_file):
                parsed_template_file = json.load(template_file)
            elif re.match(".*\.ya?ml",self.template_file):
                parsed_template_file = ruamel.yaml.safe_load(template_file)
            else:
                logger.info("Filename does not end in json/yml/yaml")
                return return_params
            for item in expanded_params:
                logger.debug("item: {0}".format(item))
                if item['ParameterKey'] not in parsed_template_file.get('Parameters', {}):
                    logger.debug("Not using parameter '{0}': not found in template '{1}'".format(item['ParameterKey'], template_file))
                    return_params.remove(item)
        logger.info("Parameters Created")
        return return_params
