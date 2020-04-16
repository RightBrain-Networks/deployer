#!/usr/bin/python

import tabulate
import time

from botocore.exceptions import ClientError
from collections import defaultdict

from .cloudformation import Stack
from .logger import logger


class StackSet(Stack):

    def __init__(self, profile, config_file, stack, disable_rollback=False, print_events=False, timeout=None, params=None, colors=defaultdict(lambda: '')):
        super(StackSet, self).__init__(profile, config_file, stack, disable_rollback, print_events, timeout, params, colors)
        self.account = self.get_config_att('account', None)
        self.accounts = self.get_config_att('accounts', None)
        self.execution_role = self.get_config_att('execution_role', None)
        self.regions = self.get_config_att('regions', None)
        self.stack_set_id = None
        self.stack_status = self.stack_set_status

        self.validate_account()

        if not self.accounts or not self.regions:
            return super(StackSet, self).wait_for_complete()

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
        config_value = self.get_config_att('administration_role', None)
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

    def wait_for_complete(self):
        NextToken = None
        response = self.client.list_stack_set_operations(StackSetName=self.stack_name)
        for operation in response['Summaries']:
            if operation['Status'] in ['RUNNING', 'STOPPING']:
                self.stack_set_waiter(operation['OperationId'], "Waiting...")

        while 'NextToken' in response:
            response = self.client.list_stack_set_operations(StackSetName=self.stack_name, NextToken=NextToken)
            NextToken = response['NextToken']
            for operation in response['Summaries']: 
                if operation['Status'] in ['RUNNING', 'STOPPING']:
                    self.stack_set_waiter(operation['OperationId'], "Waiting...")
                    
        

    def validate_account(self):
        current = self.current_account
        if self.account is not None and current != self.account:
            logger.error("Account validation failed. Expected '{}' but received '{}'".format(self.account, current))
            exit(1)

    def create(self):
        if not self.accounts or not self.regions:
            return super(StackSet, self).create()

        args = {
            "Capabilities": [
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            "Parameters": self.build_params(),
            'StackSetName': self.stack_name,
            "Tags": self.construct_tags()
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

    def upsert(self):
        if not self.accounts or not self.regions:
            return super(StackSet, self).upsert()
        # Update the stack if it already exists,otherwise, create it
        self.update() if self.stack_status == 'ACTIVE' else self.create()

    def delete_stack(self):
        if not self.accounts or not self.regions:
            return super(StackSet, self).delete_stack()

        # Delete existing stack instances
        if len(self.current_accounts) > 0:
            self.stack_set_waiter(self.delete_stack_instances(list(self.current_accounts), list(self.current_regions)), "Deletion")

        # Delete stack set
        args = {'StackSetName': self.stack_name}
        self.client.delete_stack_set(**args)

        logger.info("Delete complete!")

    def stack_set_waiter(self, operation_id, verb="Update"):
        logger.info("Stack Set " + verb + " Started")

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
        if self.print_events:
            print(tabulate.tabulate(table, headers, tablefmt='simple'))

    def update(self):

        if not self.accounts or not self.regions:
            return super(StackSet, self).update()

        args = {
            "Capabilities": [
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            "Parameters": self.build_params(),
            'StackSetName': self.stack_name,
            "Tags": self.construct_tags(),
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
