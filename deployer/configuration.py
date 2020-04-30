
from deployer.logger import logger
from deployer.stack import Stack
import ruamel.yaml, json, re
from collections import MutableMapping
from time import sleep
from boto3.session import Session

class Config(object):
    def __init__(self, profile, file_name=None):
        self.region = "us-east-1"
        self.table_name = "CFN-Deployer"
        self.profile = profile
        self.file_name = file_name
        
        #Create boto3 session and dynamo client
        self.session = Session(profile_name=self.profile, region_name=self.region)
        self.dynamo = self.session.client('dynamodb')
        
        self.config = self._get_config(file_name)
        
    def _get_config(self, file_name=None): 
        
        #Create session
        try:
            
            #Check for Dynamo state table
            if not self._table_exists():
                #Since it doesn't exist, create it
                self._create_state_table()
            
            #Retrieve data from table and format it
            scan_resp = self.dynamo.scan(TableName=self.table_name)
            
            data = {}
            for item in scan_resp['Items']:
                #Each item represents a stack
                stackname = item['stackname']['S']
                stackconfig = item['stackconfig']['M']
                data[stackname] = stackconfig
            
        except Exception as e:
            msg = str(e)
            logger.error("Failed to retrieve data from dynamo state table {}: {}".format(self.table_name,msg))
            exit(3)
        
        #Check for file_name
        if file_name:
            try:
                with open(file_name) as f:
                    file_data = ruamel.yaml.safe_load(f)
            except Exception as e:
                msg = str(e)
                logger.error("Failed to retrieve data from config file {}: {}".format(file_name,msg))
                exit(3)
            
            #Compare data from state table and file, update state table data with file data if different
            finalstate = self._dict_merge(data, file_data)
            data = finalstate
            
            #Update Dynamo table
            self._update_state_table(data)
        
        return data

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
                }
            ],
            'TableName': self.table_name,
            'KeySchema':[
                {
                    'AttributeName': 'stackname',
                    'KeyType': 'HASH'
                },
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }
        
        #Create Dynamo DB state table
        try:
            logger.info("Attempting to create table")
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
        
    def _update_state_table(self, data):
        
        #Loop over stacks
        for stackname in data.keys():
            logger.info("Updating stack: {}".format(stackname))
            #stackconfig = data[stackname]
            stackconfig = self._recursive_dynamo_conversion(data[stackname])
            logger.info(stackconfig)
        
            #Set up the arguments
            kwargs = {
                "TableName": self.table_name,
                "Key": {
                    "stackname": {
                        "S": stackname
                    }
                },
                "UpdateExpression": "set stackconfig = :val",
                "ExpressionAttributeValues": {
                    #":val": {"M": stackconfig}
                    ":val": stackconfig
                }
            }
            
            try:
                response = self.dynamo.update_item(**kwargs)
            except Exception as e:
                msg = str(e)
                logger.error("Failed to update data to dynamo state table {}: {}".format(self.table_name,msg))
                exit(3)
        
        return
        
    def _recursive_dynamo_conversion(self, param):
        
        if isinstance(param, dict):
            paramdict = {}
            for key in param.keys():
                paramdict[key] = self._recursive_dynamo_conversion(param[key])
            return {'M': paramdict}
        elif isinstance(param, list):
            #paramlist = self._recursive_dynamo_conversion(item) for item in param 
            return {'L': [ self._recursive_dynamo_conversion(item) for item in param ] }
        
        #For everything else, force it to be a string type for Dynamo
        
        return {'S': param}
        
    def list_stacks(self):
        #This includes global settings as a stack
        return self.config.keys()
        
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

    def get_config_att(self, key, default=None, required=False):
        base = self.config.get('global', {}).get(key, None)
        base = self.config.get(self.stack).get(key, base)
        if required and base is None:
            logger.error("Required attribute '{}' not found in config.".format(key))
            exit(3)
        return base if base is not None else default

    def get_config(self):
        return self.config
        
    def set_master_stack(self, master_stack):
        self.stack = master_stack
        return 
