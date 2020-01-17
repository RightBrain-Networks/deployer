
from deployer.logger import logger
from deployer.stack import Stack
import ruamel.yaml, json, re

class Config(object):
    def __init__(self, file_name, master_stack):
        self.file_name = file_name
        self.config = self.get_config()
        self.stack = master_stack

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

    def get_config(self): 
        with open(self.file_name) as f:
            data = ruamel.yaml.safe_load(f)
        return data

    def get_config_att(self, key, default=None, required=False):
        base = self.config.get('global', {}).get(key, None)
        base = self.config.get(self.stack).get(key, base)
        if required and base is None:
            logger.error("Required attribute '{}' not found in config '{}'.".format(key, self.file_name))
            exit(3)
        return base if base is not None else default