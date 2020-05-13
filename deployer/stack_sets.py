#!/usr/bin/python

import tabulate
import time

from botocore.exceptions import ClientError
from collections import defaultdict

from deployer.cloudformation import AbstractCloudFormation
from deployer.logger import logger


class StackSet(AbstractCloudFormation):
    def __init__(self, session, stack, config, bucket, args = {}):

        # Save important parameters
        self.session = session
        self.stack = stack
        self.config = config
        self.bucket = bucket
        self.stack_set_id = None
        


        self.params = args.get('params', {})

        self.print_events = args.get('print_events', False)

        # Load values from config
        self.release = self.config.get_config_att('release').replace('/','.')
        self.template = self.config.get_config_att('template', required=True)
        self.account = self.config.get_config_att('account', None)
        self.accounts = self.config.get_config_att('accounts', None)
        self.execution_role = self.config.get_config_att('execution_role', None)
        self.regions = self.config.get_config_att('regions', None)
        self.stack_name = stack

        # Intialize objects
        self.client = self.session.client('cloudformation')

        # Load values from methods
        self.template_url = self.bucket.construct_template_url(self.config, self.stack, self.release, self.template) # self.construct_template_url()
        self.template_file = self.bucket.get_template_file(self.config, self.stack)
        self.template_body = self.bucket.get_template_body(self.config, self.template)

        self.stack_status = self.stack_set_status
        self.validate_account()

    @property
    def current_instances(self):
        result = self.client.list_stack_instances(StackSetName=self.stack_name)
        current = result['Summaries']
        while 'NextToken' in result:
            result = self.client.list_stack_instances(StackSetName=self.stack_name, NextToken=result['NextToken'])
            current = current + result['Summaries']
        return current

    @property
    def current_accounts(self):
        return set([x['Account'] for x in self.current_instances])

    @property
    def current_regions(self):
        return set([x['Region'] for x in self.current_instances])

    @property
    def administration_role(self):
        config_value = self.config.get_config_att('administration_role', None)
        if config_value is None or config_value.startswith('arn:'):
            return config_value
        else:
            return "arn:aws:iam::{}:role/service-role/{}".format(self.current_account, config_value)

    @property
    def current_account(self):
        return self.session.client('sts').get_caller_identity().get('Account', None)

    @property
    def stack_instances(self):
        if not self.accounts or not self.regions:
            return None

    def exists(self):
        return self.stack_set_status() == 'ACTIVE'

    def reload_stack_status(self):
        pass

    @property
    def stack_set_status(self):
        if not self.accounts or not self.regions:
            return self.stack_status

        try:
            result = self.client.describe_stack_set(StackSetName=self.stack_name)
            current = result.get('StackSet', {}).get('Status', None)
            return current if current in ['ACTIVE'] else None
        except ClientError:
            return None

    def validate_account(self):
        current = self.current_account
        if self.account is not None and current != self.account:
            logger.error("Account validation failed. Expected '{}' but received '{}'".format(self.account, current))
            exit(1)

    def create_stack(self):

        args = {
            "Capabilities": [
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            "Parameters": self.config.build_params(self.session, self.stack, self.release, self.params, self.template_file),
            'StackSetName': self.stack_name,
            "Tags": self.config.construct_tags()
        }
        if self.template_body:
            logger.info("Using local template due to null template bucket")

        # Add conditional arguements
        args.update({'AdministrationRoleARN': self.administration_role} if self.administration_role else {})
        args.update({'ExecutionRoleName': self.execution_role} if self.execution_role else {})
        args.update({'TemplateBody': self.template_body} if self.template_body else {"TemplateURL": self.template_url})

        # Create stack set
        result = self.client.create_stack_set(**args)
        self.stack_set_id = result['StackSetId']

        self.stack_set_waiter(self.create_stack_instances(self.accounts, self.regions), "Creation")

    def upsert_stack(self):
        # Update the stack if it already exists,otherwise, create it
        self.update_stack() if self.stack_status == 'ACTIVE' else self.create_stack()

    def delete_stack(self):

        # Delete existing stack instances
        if len(self.current_accounts) > 0:
            self.stack_set_waiter(self.delete_stack_instances(list(self.current_accounts), list(self.current_regions)), "Deletion")

        # Delete stack set
        args = {'StackSetName': self.stack_name}
        self.client.delete_stack_set(**args)

        logger.info("Delete complete!")

    def stack_set_waiter(self, operation_id, verb="Update"):
        logger.info("Stack Set " + verb + " Started")

        if self.print_events:
            args = {
                "StackSetName": self.stack_name,
                "OperationId": operation_id
            }

            operation = self.client.describe_stack_set_operation(**args)
            time.sleep(5)

            while operation['StackSetOperation']['Status'] not in ['SUCCEEDED', 'FAILED', 'STOPPED']:
                time.sleep(5)
                operation = self.client.describe_stack_set_operation(**args)

            # Print result
            results = self.client.list_stack_set_operation_results(**args)
            headers = ['Account', 'Region', 'Status', 'Reason']
            table = [[x['Account'], x['Region'], x['Status'], x.get('StatusReason', '')] for x in results['Summaries']]
        
            print(tabulate.tabulate(table, headers, tablefmt='simple'))

    def update_stack(self):


        args = {
            "Capabilities": [
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            "Parameters": self.config.build_params(self.session, self.stack, self.release, self.params, self.template_file),
            'StackSetName': self.stack_name,
            "Tags": self.config.construct_tags(),
        }

        args.update({'AdministrationRoleARN': self.administration_role} if self.administration_role else {})
        args.update({'ExecutionRoleName': self.execution_role} if self.execution_role else {})
        args.update({'TemplateBody': self.template_body} if self.template_body else {"TemplateURL": self.template_url})

        if self.template_body:
            logger.info("Using local template due to null template bucket")

        # Generate API calls based upon what is currently deployed
        api_calls = self.generate_instance_calls()

        # Run update on existing stacks
        result = self.client.update_stack_set(**args)
        operation_id = result.get('OperationId')
        self.stack_set_waiter(operation_id)

        # Delete or create as needed
        for call in api_calls:
            if call['type'] == "create":
                self.stack_set_waiter(self.create_stack_instances(call['accounts'], call['regions']))
            if call['type'] == "delete":
                self.stack_set_waiter(self.delete_stack_instances(call['accounts'], call['regions']))

    def generate_instance_calls(self):
        api_calls = []

        # Create x-y graph where x is accounts and y is regions
        graph = []
        for account in range(0, len(self.accounts)):
            graph.append([])
            for region in range(0, len(self.regions)):
                graph[account].append([])
                if self.regions[region] not in self.current_regions or self.accounts[account] not in self.current_accounts:
                    graph[account][region] = "create"
                    logger.debug(self.accounts[account] + ", " + self.regions[region] + " marked for creation")
                elif (self.regions[region] not in self.regions and self.regions[region] in self.current_regions) or (self.accounts[account] not in self.accounts and self.accounts[account] in self.current_accounts):
                    graph[account][region] = "delete"
                    logger.debug(self.accounts[account] + ", " + self.regions[region] + " marked for deletion")
                else:
                    graph[account][region] = "update"
                    logger.debug(self.accounts[account] + ", " + self.regions[region] + " marked for update")

        for call_type in ["create", "update", "delete"]:
            type_calls = []

            # Get all account based calls
            for account in range(0, len(self.accounts)):
                api_call = {
                    'type': call_type,
                    'accounts': [self.accounts[account]],
                    'regions': []
                }
                for region in range(0, len(self.regions)):
                    if graph[account][region] == call_type:
                        api_call['regions'].append(self.regions[region])
                        graph[account][region] = "done"
                if len(api_call['regions']) > 0:
                    type_calls.append(api_call)
            
            # Get all region based calls
            for region in range(0, len(self.regions)):
                api_call = {
                    'type': call_type,
                    'accounts': [],
                    'regions': [self.regions[region]]
                }
                for account in range(0, len(self.accounts)):
                    if graph[account][region] == call_type:
                        api_call['accounts'].append(self.accounts[account])
                        graph[account][region] = "done"
                if len(api_call['accounts']) > 0:
                    type_calls.append(api_call)

            # Merge account based calls
            for call in type_calls:
                for other_call in type_calls:
                    if call != other_call:
                        if call['regions'] == other_call['regions']:
                            call['accounts'] = call['accounts'] + other_call['accounts']
                            type_calls.remove(other_call)
            
            # Merge region based calls
            for call in type_calls:
                for other_call in type_calls:
                    if call != other_call:
                        if call['accounts'] == other_call['accounts']:
                            call['regions'] = call['regions'] + other_call['regions']
                            type_calls.remove(other_call)

            api_calls = api_calls + type_calls
        return api_calls

    def create_stack_instances(self, accounts, regions):
        logger.info("Creating " + str(len(accounts) * len(regions)) + " stack instances...")
        result = self.client.create_stack_instances(StackSetName=self.stack_name, Accounts=accounts, Regions=regions)
        return result['OperationId']

    def delete_stack_instances(self, accounts, regions):
        logger.info("Deleting " + str(len(accounts) * len(regions)) + " stack instances...")
        result = self.client.delete_stack_instances(StackSetName=self.stack_name, Accounts=accounts, Regions=regions, RetainStacks=False)
        return result['OperationId']
