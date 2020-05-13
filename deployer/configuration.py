
from deployer.logger import logger
from deployer.stack import Stack
import ruamel.yaml, json, re
from collections import MutableMapping
from time import sleep
from boto3.session import Session
from copy import deepcopy
from datetime import datetime
import git

class Config(object):
    def __init__(self, profile, stack_name, file_name=None, override_params=None):
        self.table_name = "CloudFormation-Deployer"
        self.index_name = "VersionIndex"
        self.profile = profile
        self.stack = stack_name
        self.file_name = file_name
        
        self.file_data = self._get_file_data(file_name)
        
        #Create boto3 session and dynamo client
        self.session = Session(profile_name=self.profile)
        self.dynamo = self.session.client('dynamodb')
        
        #Create state table if necessary
        if not self._table_exists():
            
            #We must have a config file to populate the table
            if not self.file_name:
                logger.error("When creating a new state table, --config option is required")
                exit(3)
            
            #Since it doesn't exist, create it
            self._create_state_table()
        
        self.config = {}
        self.version = 0
        self._get_stack_config(override_params)
    
    def _get_file_data(self, file_name=None):
        file_data = None
        
        if file_name:
            try:
                with open(file_name) as f:
                    file_data = ruamel.yaml.safe_load(f)
            except Exception as e:
                msg = str(e)
                logger.error("Failed to retrieve data from config file {}: {}".format(file_name,msg))
                exit(3)
        
        return file_data
    
    def _get_stack_config(self, params=None):
        
        #Get the most recent stack config from Dynamo
        try:
            dynamo_args = {
                'TableName': self.table_name,
                'KeyConditionExpression': "#sn = :sn",
                'ExpressionAttributeNames': {
                    '#sn': 'stackname'
                },
                'ExpressionAttributeValues': {
                    ':sn': {
                        'S': self.stack
                    }
                },
                'ScanIndexForward': False,
                'Limit': 1
            }
            
            query_resp = self.dynamo.query(**dynamo_args)
            
        except Exception as e:
            msg = str(e)
            logger.error("Failed to retrieve data from dynamo state table {} for stack {}: {}".format(self.table_name, stack_context, msg))
            exit(3)
        
        data = {}
        if query_resp['Count'] > 0:
            #Format the stack config data
            item = query_resp['Items'][0]
            data = self._recursive_dynamo_to_data(item)
            if 'version' in data and data['version'].isdigit():
                self.version = int(data['version'])
            data = data['stackconfig']
        
        if self.file_data:
            if self.stack in self.file_data:
                config_copy = self._handle_use_previous_value(data, self.file_data[self.stack])
                
                #Merge the file data for the stack if applicable, global first
                if 'global' in self.file_data:
                    global_copy = self._handle_use_previous_value(data, self.file_data['global'])
                    merged_global = self._dict_merge(global_copy, config_copy)
                    config_copy = merged_global
                
                data = config_copy
                
        if params:
            #Merge the override params for the stack if applicable
            param_data = {
                "parameters": params
            }
            merged_params = self._dict_merge(data, param_data)
            data = merged_params
                        
        sts = self.session.client('sts')
        self.identity_arn = sts.get_caller_identity().get('Arn', '')

        # Load values from methods for config lookup
        self.base = data.get('sync_base', '.')
        self.repository = self.get_repository(self.base)
        self.commit = self.repository.head.object.hexsha if self.repository else 'null'
        self.origin = self.get_repository_origin(self.repository) if self.repository else 'null'
        
        if not data.get('release', False):
            data['release'] = self.commit
        
        if params or self.file_data:
            self._update_state_table(self.stack, data)
            
        self.config[self.stack] = data
                
        return data
        
    def _handle_use_previous_value(self, olddata, paramdict):
        dict_copy = deepcopy(paramdict)
        # First look for indicators to use previous value, remove it from the dict if it is true
        for paramkey in dict_copy['parameters'].keys():
            if isinstance(dict_copy['parameters'][paramkey],dict):
                if "UsePreviousValue" in dict_copy['parameters'][paramkey]:
                    if dict_copy['parameters'][paramkey]["UsePreviousValue"]:
                        if 'parameters' in olddata and paramkey in olddata['parameters']: 
                            dict_copy['parameters'][paramkey] = olddata['parameters'][paramkey]
                        else:
                            dict_copy['parameters'].pop(paramkey)
        return dict_copy
        
    def _table_exists(self):
        resp_tables = self.dynamo.list_tables()
        if self.table_name in resp_tables['TableNames']:
            resp_table = self.dynamo.describe_table(TableName=self.table_name)
            if resp_table['Table']['TableStatus'] == 'ACTIVE': 
                return True
        return False

    def _create_state_table(self):
        
        #Set up the arguments
        kwargs = {
            'AttributeDefinitions':[
                {
                    'AttributeName': 'stackname',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'timestamp',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'version',
                    'AttributeType': 'S'
                }
            ],
            'TableName': self.table_name,
            'KeySchema':[
                {
                    'AttributeName': 'stackname',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'timestamp',
                    'KeyType': 'RANGE'
                }
            ],
            'LocalSecondaryIndexes':[
                {
                    'IndexName': self.index_name,
                    'KeySchema': [
                        {
                            'AttributeName': 'stackname',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'version',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }
        
        #Create Dynamo DB state table
        try:
            logger.info("Attempting to create state table")
            response = self.dynamo.create_table(**kwargs)
            
            #Waiting for the table to exist
            counter = 0
            limit = 10
            while counter < limit:
                sleep(1)
                if self._table_exists():
                    return
                counter+=1
                
            raise Exception("Timeout occurred while waiting for Dynamo table creation")
            
        except Exception as e:
            msg = str(e)
            logger.error("Failed to retrieve data from dynamo state table {}: {}".format(self.table_name,msg))
            exit(3)
        
        return
        
    def _update_state_table(self, stack, data):
        
        #Convert to Dynamo params
        stackdata = deepcopy(data)
        stack_config = self._recursive_data_to_dynamo(stackdata)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H:%M:%S.%f")
        #Increment version
        self.version+=1
        item = {
            "stackname":   { "S": stack },
            "version":     { "S": str(self.version)},
            "timestamp":   { "S": timestamp},
            "stackconfig": stack_config,
            "caller":      { "S": self.identity_arn},
            "commit":      { "S": self.commit},
            "origin":      { "S": self.origin},
        }
        
        #Set up the API arguments
        kwargs = {
            "TableName": self.table_name,
            "Item": item
        }
        
        try:
            response = self.dynamo.put_item(**kwargs)
        except Exception as e:
            msg = str(e)
            logger.error("Failed to update data to dynamo state table {}: {}".format(self.table_name,msg))
            exit(3)
                
        return
        
    def list_versions(self):
        
        try:
            dynamo_args = {
                'TableName': self.table_name,
                'IndexName': self.index_name,
                'ConsistentRead': True,
                'KeyConditionExpression': "#sn = :sn",
                'ExpressionAttributeNames': {
                    '#sn': 'stackname',
                    "#tm": 'timestamp'
                },
                'ExpressionAttributeValues': {
                    ':sn': {
                        'S': self.stack
                    }
                },
                'ProjectionExpression': "version, #tm",
                'ScanIndexForward': False
            }
            
            query_resp = self.dynamo.query(**dynamo_args)
            
        except Exception as e:
            msg = str(e)
            logger.error("Failed to retrieve data from dynamo state table {} for stack {}: {}".format(self.table_name, self.stack, msg))
            exit(3)
        
        if query_resp['Count'] <= 0:
            logger.error("Failed to retrieve versions from dynamo state table {} for stack {}: No versions exist".format(self.table_name, self.stack))
            exit(3)
            
        #Format the data
        items = []
        for item in query_resp['Items']:
            items.append(self._recursive_dynamo_to_data(item))
        
        return items
        
    def get_version(self, version):
        try:
            dynamo_args = {
                'TableName': self.table_name,
                'IndexName': self.index_name,
                'ConsistentRead': True,
                'KeyConditionExpression': "#sn = :sn AND #vn = :vn",
                'ExpressionAttributeNames': {
                    '#sn': 'stackname',
                    '#vn': 'version',
                },
                'ExpressionAttributeValues': {
                    ':sn': {
                        'S': self.stack
                    },
                    ':vn': {
                        'S': version
                    }
                },
                'ScanIndexForward': False,
            }
            
            query_resp = self.dynamo.query(**dynamo_args)
            
        except Exception as e:
            msg = str(e)
            logger.error("Failed to retrieve data from dynamo state table {} for stack {}: {}".format(self.table_name, self.stack, msg))
            exit(3)
        
        if query_resp['Count'] <= 0:
            logger.error("Failed to retrieve versions from dynamo state table {} for stack {}: Version '{}' does not exist".format(self.table_name, self.stack, version))
            exit(3)
            
        #Format the data
        item = self._recursive_dynamo_to_data(query_resp['Items'][0])
        
        return item
        
    def set_version(self, version):
        item = self.get_version(version)
        
        stackconfig = item['stackconfig']
        self._update_state_table(self.stack, stackconfig)
            
        self.config[self.stack] = stackconfig
        
        return
    
    def _recursive_data_to_dynamo(self, param):
        
        if isinstance(param, dict):
            paramdict = {}
            for key in param.keys():
                if param[key] != '':
                    paramdict[key] = self._recursive_data_to_dynamo(param[key])
            return {'M': paramdict}
        elif isinstance(param, list):
            return {'L': [ self._recursive_data_to_dynamo(item) for item in param ] }
        
        #For everything else, force it to be a string type for Dynamo
        
        return {'S': param}
        
    def _recursive_dynamo_to_data(self, param):
        if isinstance(param, dict):
            paramdict = {}
            for key in param.keys():
                if key == 'S':
                    return str(param[key])
                elif key == 'L':
                    newlist = [self._recursive_dynamo_to_data(item) for item in param[key]]
                    return newlist
                elif key == 'M':
                    return self._recursive_dynamo_to_data(param[key])
                else:
                    paramdict[str(key)] = self._recursive_dynamo_to_data(param[key])
            return paramdict        
        
        return param
        
    def _dict_merge(self, old, new):
        #Recursively go through the nested dictionaries, with values in
        # 'new' overwriting the values in 'old' for the same key
        
        for k, v in old.items():
            if k in new:
                if all(isinstance(e, MutableMapping) for e in (v, new[k])):
                    new[k] = self._dict_merge(v, new[k])
        merged = old.copy()
        merged.update(new)
        return merged
        
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
        if self.file_name:
            tags.append({'Key': 'deployer:config', 'Value': self.file_name.replace('\\', '/')})
        return tags
        
    def build_params(self, session, stack_name, release, params, temp_file):
        # create parameters from the config.yml file
        self.parameter_file = "%s-params.json" % stack_name
        expanded_params = []
        expanded_params.append({ "ParameterKey": "Release", "ParameterValue": release })
        # Order of the stacks is priority on overwrites, authoritative is last
        # Here we loop through all of the params in the config file, we need to 
        # create a array of parameter objects, we have to loop through our array 
        # to ensure we dont already have one of that key.
        for env in ['global', stack_name]:
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
                    stack = Stack(session, lookup_struct['Stack'], self)
                    stack.get_outputs()
                    for output in stack.outputs:
                        if output['OutputKey'] == lookup_struct['OutputKey']:
                            expanded_params.append({ "ParameterKey": param_key, "ParameterValue": output['OutputValue'] })

        # Remove overridden parameters and set them based on the override
        # provided. Explicit overrides take priority over anything in the
        # configuration files.
        expanded_params = [x for x in expanded_params if x['ParameterKey'] not in params.keys()]
        expanded_params += [{"ParameterKey": x, "ParameterValue": params[x]} for x in params.keys()]

        # Here we restrict the returned parameters to only the ones that the
        # template accepts by copying expanded_params into return_params and removing
        # the item in question from return_params
        logger.debug("expanded_params: {0}".format(expanded_params))
        return_params = list(expanded_params)
        with open(temp_file, 'r') as template_file:
            if re.match(".*\.json",temp_file):
                parsed_template_file = json.load(template_file)
            elif re.match(".*\.ya?ml",temp_file):
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
    
    def get_repository(self, base):
        try:
            return git.Repo(base, search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            return None

    def get_repository_origin(self, repository):
        try:
            origin = repository.remotes.origin.url
            return origin.split('@', 1)[-1] if origin else None
        except (StopIteration, ValueError):
            return None
        return None

    def get_config_att(self, key, default=None, required=False):
        base = self.config.get('global', {}).get(key, None)
        base = self.config.get(self.stack).get(key, base)
        if required and base is None:
            logger.error("Required attribute '{}' not found in config.".format(key))
            exit(3)
        return base if base is not None else default

    def get_config(self):
        return self.config
        
