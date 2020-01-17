#!/usr/bin/env python
import git
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
    def build_params(self):
        # Method to build parameters file
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
    def wait_for_state(self, state):
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

    def get_repository(self, base):
        try:
            return git.Repo(base, search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            return None

    # Pass a GIT repository object
    def get_repository_origin(self, repository):
        try:
            origin = repository.remotes.origin.url
            return origin.split('@', 1)[-1] if origin else None
        except (StopIteration, ValueError):
            return None
        return None

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