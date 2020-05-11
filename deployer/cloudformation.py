#!/usr/bin/env python
from abc import ABCMeta, abstractmethod
from deployer.logger import logger

# Maybe needed
import ruamel.yaml




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
    def create_stack(self):
        pass

    @abstractmethod
    def update_stack(self):
        pass

    @abstractmethod
    def upsert_stack(self):
        pass

    @abstractmethod
    def delete_stack(self):
        pass

    @abstractmethod
    def exists(self):
        pass

    @abstractmethod
    def reload_stack_status(self):
        pass

    @property
    @abstractmethod
    def status(self):
        pass

    def get_template_body(self, bucket, template):
        if not bucket:
            try:
                with open(template, 'r') as f:
                    return f.read()
            except Exception as e:
                logger.warning("Failed to read template file: " + str(e))
                return None
        else:
            return None

    def validate_account(self, session, config):
        # Check if account in config matches the authorized account
        current = session.client('sts').get_caller_identity().get('Account', None)
        configured = config.get_config_att('account', None)
        if configured is not None and current != configured:
            logger.error("Account validation failed. Expected '{}' but received '{}'".format(configured, current))
            exit(1)
