from deployer.cloudformation import AbstractCloudFormation
from deployer.decorators import retry
from deployer.logger import logger
from deployer.cloudtools_bucket import CloudtoolsBucket

import signal, pytz

from collections import defaultdict
from botocore.exceptions import ClientError, WaiterError
from tabulate import tabulate
from time import sleep 
from datetime import datetime 
from parse import parse

class Stack(AbstractCloudFormation):
    def __init__(self, session, stack, config, bucket, args = {}):

        # Save important parameters
        self.session = session
        self.stack = stack
        self.config = config
        if bucket:
            self.bucket = bucket

        # Load values from args
        self.disable_rollback = args.get('disable_rollback', False)
        self.print_events = args.get('print_events', False)
        self.timed_out = args.get('timeout', None)
        self.colors = args.get('colors', defaultdict(lambda: ''))
        self.params = args.get('params', {})

        # Load values from config
        self.stack_name = self.config.get_config_att('stack_name', required=True, stack=self.stack)
        self.base = self.config.get_config_att('sync_base', '.')

        # Load values from methods for config lookup
        self.repository = self.get_repository(self.base)
        self.commit = self.repository.head.object.hexsha if self.repository else 'null'

        # Load values from config
        self.release = self.config.get_config_att('release', self.commit).replace('/','.')
        self.template = self.config.get_config_att('template', required=True)
        self.timeout = self.timed_out if self.timed_out is not None else self.config.get_config_att('timeout', None)
        self.transforms = self.config.get_config_att('transforms')

        # Intialize objects
        self.client = self.session.client('cloudformation')
        self.sts = self.session.client('sts')

        # Load values from methods
        self.origin = self.get_repository_origin(self.repository) if self.repository else 'null'
        self.identity_arn = self.sts.get_caller_identity().get('Arn', '')
        if bucket:
            self.template_url = self.bucket.construct_template_url(self.config, self.stack, self.release, self.template) # self.construct_template_url()
            self.template_file = self.bucket.get_template_file(self.config, self.stack)
            self.template_body = self.bucket.get_template_body(self.config, self.template)

        # Set state values
        self._timed_out = False

        self.validate_account(self.session, self.config)
        self.reload_stack_status()


    def reload_change_set_status(self, change_set_name): 
        try:
            resp = self.client.describe_change_set(
                ChangeSetName=change_set_name,
                StackName=self.stack_name
            )
            self.change_set_status = resp['Status']
        except Exception:
            self.change_set_status = 'False'
        return self.change_set_status

    def construct_tags(self): 
        tags = self.config.get_config_att('tags')
        if tags:
            tags = [ { 'Key': key, 'Value': value } for key, value in tags.items() ] 
            if len(tags) > 47:
                raise ValueError('Resources tag limit is 50, you have provided more than 47 tags. Please limit your tagging, save room for name and deployer tags.')
        else:
            tags = []
        if self.config.get_config_att('meta_tags') != False:
            tags.append({'Key': 'deployer:stack', 'Value': self.stack})
            tags.append({'Key': 'deployer:caller', 'Value': self.identity_arn})
            tags.append({'Key': 'deployer:git:commit', 'Value': self.commit})
            tags.append({'Key': 'deployer:git:origin', 'Value': self.origin})
            tags.append({'Key': 'deployer:config', 'Value': self.config.file_name.replace('\\', '/')})
        return tags
        

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
                waiter.wait(StackName=self.stack_name)
            except WaiterError as e:
                status = self.reload_stack_status()
                logger.info(status)
                self.output_events(start_time, 'create')
        logger.info(self.reload_stack_status())

    def update_waiter(self, start_time):
        waiter = self.client.get_waiter('stack_update_complete')
        logger.info("Update Started")
        sleep(5)
        logger.info(self.reload_stack_status())
        if self.print_events:
            try:
                self.output_events(start_time, 'update')
            except RuntimeError as e:
                if self.timed_out:
                    logger.error('Stack creation exceeded timeout of {} minutes and was aborted.'.format(self.timeout))
                    exit(2)
                else:
                    raise e
        else:
            try:
                waiter.wait(StackName=self.stack_name)
            except WaiterError:
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
        sleep_interval = 15
        while self.stack_status != END_STATUS:
            status = self.reload_stack_status()
            table = []
            sleep(sleep_interval)
            #Check interval and exit if this is an update
            if action == 'update' and self.timeout is not None:
                if (sleep_interval * count) > (self.timeout * 60):
                    self.timed_out = True
                    raise RuntimeError("Update stack Failed")
            events = self.client.describe_stack_events(StackName=self.stack_name)
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
        self.client.delete_stack(StackName=self.stack_name)
        logger.info(self.colors['error'] + "Sent delete request to stack" + self.colors['reset'])
        return True

    def get_latest_change_set_name(self):
        resp = {}
        latest = None
        while 'NextToken' in resp or latest == None:
            if 'NextToken' in resp:
                resp = self.client.list_change_sets(
                    StackName=self.stack_name,
                    NextToken=resp['NextToken']
                )
            else:
                resp = self.client.list_change_sets(
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
                StackName=self.stack_name,
                TemplateURL=self.template_url,
                Parameters=self.config.build_params(self.session, self.stack, self.release, self.params, self.template_file),
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
        self.client.execute_change_set(
            ChangeSetName=change_set_name,
            StackName=self.stack_name
        )
    
    def print_change_set(self, change_set_name, change_set_description):    
        resp = self.client.describe_change_set(
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

    def exists(self):
        try:
            self.client.describe_stacks(StackName=self.stack_name)
            return True
        except ClientError:
            return False

    def describe(self):
        try:
            return self.client.describe_stacks(StackName=self.stack_name)['Stacks'][0]
        except ClientError:
            return {}

    def upsert_stack(self):
        self.update_stack() if self.exists() else self.create_stack()

    def create_stack(self):
        signal.signal(signal.SIGINT, self.cancel_create)
        if not self.transforms:
            # create the stack 
            start_time = datetime.now(pytz.utc)
            args = {
                "StackName": self.stack_name,
                "Parameters": self.config.build_params(self.session, self.stack, self.release, self.params, self.template_file),
                "DisableRollback": self.disable_rollback,
                "Tags": self.construct_tags(),
                "Capabilities": [
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM',
                    'CAPABILITY_AUTO_EXPAND'
                ]
            }
            args.update({'TemplateBody': self.template_body} if self.template_body else {"TemplateURL": self.template_url})
            args.update({'TimeoutInMinutes': self.timeout} if self.timeout else {})
            if self.template_body:
                logger.info("Using local template due to null template bucket")
            self.client.create_stack(**args)
            self.create_waiter(start_time)
        else:
            start_time = datetime.now(pytz.utc)
            change_set_name = "{0}-1".format(self.config.get_config_att('change_prefix'))
            self.get_change_set(change_set_name, "Deployer Automated", 'CREATE')
            self.execute_change_set(change_set_name)
            self.create_waiter(start_time)

    def update_stack(self):
        signal.signal(signal.SIGINT, self.cancel_update)
        if not self.transforms:
            start_time = datetime.now(pytz.utc)
            args = {
                "StackName": self.stack_name,
                "Parameters": self.config.build_params(self.session, self.stack, self.release, self.params, self.template_file),
                "Tags": self.construct_tags(),
                "Capabilities": [
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM',
                    'CAPABILITY_AUTO_EXPAND'
                ]
            }
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
        else:
            latest_change = self.get_latest_change_set_name()
            if latest_change:
                change_number = int(latest_change.strip(self.config.get_config_att('change_prefix') + '-'))
                change_number += 1
            else:
                change_number = 1
            start_time = datetime.now(pytz.utc)
            change_set_name = "{0}-{1}".format(self.config.get_config_att('change_prefix'),change_number)
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
        self.client.cancel_update_stack(StackName=self.stack_name)
        exit(1)

    @retry(ClientError,logger=logger)
    def get_outputs(self):
        resp = self.client.describe_stacks(
                   StackName=self.stack_name)
        self.outputs = resp['Stacks'][0]['Outputs']
        return self.outputs

    @property
    def status(self):
        return self.reload_stack_status()

    @retry(ClientError,tries=6,logger=logger)
    def reload_stack_status(self): 
        try:
            resp = self.client.describe_stacks(
                StackName=self.stack_name)
            self.stack_status = resp['Stacks'][0]['StackStatus']
        except Exception:
            self.stack_status = 'False'
        return self.stack_status
