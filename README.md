# Deployer

## Import
Import into your project repository with the following command in the base of the repository.
`git submodule add ssh://git-codecommit.us-east-1.amazonaws.com/v1/repos/deployer`

Deployer is used to create | update | delete CloudFormation Stacks

##### Flags
* -c <config file> (REQUIRED) -- Yaml configuration file to run against.
* -e <environment name> (REQUIRED) -- Environment Name corresponding to a block in the config file.
* -x <execute command> (REQUIRED) -- create|update|delete Action you wish to take on the stack.
* -p <profile> (REQUIRED) -- AWS CLI Profile to use for AWS commands [CLI Getting Started](http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html)


##### Example
`./deployer.py -c config.yml -e Environment -x create -p profileName -s`

`./deployer.py -c config.yml -e DevDerek -x create -p profileName`


# The Config

The config is a large dictionary. First keys within the dictionary are Environment Names. The global Environment Parameters is a common ground to deduplicate parameter entries that are used in each Environment. Environment parameters overwrite global parameters. 

## All Environments
* All environments need a environment name like a logical name in CFN, it's the top level key in the dictionary.
* All environments need a stack_name 
* All environments need to construct the stacks template, you can either specify full_template_url or template_bucket, release, and template combined.

## Sync
Command line takes a optional -s for sync to s3. Walks {sync_base} for {sync_dirs} recursively for files to upload. S3 path of object based on concatenation of Environment Keys: {sync_dest_bucet}/{release}/{sync_dir}/{recursive_file_path}
* sync_base: base of repository to sync to s3
* sync_dirs: directories from sync_base to sync to s3
* sync_dest_bucket: bucket to sync to 

## Zipping Lambda Functions
Optional parameters `-z` or `--zip-lambdas` will set a flag to True to indicate the zipping of lambda packages within the project. These lambdas will be zipped and moved into the base directory to be synced.
Lambda directories are specified in the yaml configuration. These directories are stored in a yaml list like so:
```yaml
global:
  region: us-east-1
  release: development
  ...
  ...
  lambda_dirs: [
    'lambdas/ECR-Cleanup',
    'your/lambda/directory'
  ]
  ...
  ...
```
or can similarly be tied to a specific stack configuration like so:
```yaml
Network:
  release: development
  ...
  ...
  lambda_dirs: [
    'lambdas/NAT-Function'
  ]
  ...
  ...
```
If there are no `lambda_dirs` for the specified Stack when running `deployer`, any globally configured `lambda_dirs` will be the fallback for this operation. If a particular lambda directory does not exist, this operation will raise a `ValueError` with the specific directory that does not exist, which caused the error.

##### Parameters
These parameters correspond to parameters that need to be passed to the Top.json template.

These parameters provide identity to the Services like what AMI to use or what bootstrap file to pull even the size of the instance.
```
    parameters:
      Monitoring: 'True'
      # Bootstrap and CloudFormation bucket infered by CloudToolsBucket/{release | branch}/{bootstrap | cloudformation}
      BootstrapBucket: aws-tools-us-east-1/1.1/bootstrap
      CloudFormationBucket: aws-tools-us-east-1/1.1/cloudformation
      NginxAMI: ami-cbb9ecae
      NginxInstanceType: t2.medium
...
      UploadAMI: ami-3069145a
      UploadInstanceType: t2.medium
```

##### Lookup Parameters

These are parameters that can be pulled from another stack's output. 
* The key in this key value pair is the ParameterKey being passed to this Stack. 
* The Value is a custom structure that requires a Stack and OutputKey. 
.. * The stack is the Environment name and the OutputKey is the name of the output from the stack being targeted. The script will fetch the stack output and retrieve the output key, using it's value for the parameter value. 

These are mainly used for pulling data from the Network Stacks like SNS topics or Subnets
```
    lookup_parameters:
      VPC: { Stack: Network, OutputKey: VPC }
      VPCCIDR: { Stack: Network, OutputKey: VPCCIDR }
      PublicSubnets: { Stack: Network, OutputKey: DevPublicSubnets }
      PrivateSubnets: { Stack: Network, OutputKey: DevPrivateSubnets }
```



## Updates
When running updates to environments you'll be running updates to the CloudFormation Stack specified by Environement. 

Making updates to CloudFormation there are a lot of considerations to be had. See the [Running Updates](/cloudformation/) section of the CloudFormation [README.md](/cloudformation/README.md).
Updates to CloudFormation will change the living Infrastructure based on your current configuration. 
Updates using this script will not update the objects in s3. If you're making alterations to the cloudformation or bootstrap directory you'll need to first sync with S3. See [s3_sync.sh](../)
After syncing with S3 or if there are no changes other than your yaml configuration file you're ready to run an update.  

To run an update follow the following structure:
```
./deployer.py -c sandbox-us-east-1.yml -p profileName -e <Environment Name> -x update
```

## Deletes
When using this script to delete it simply looks up the environment variable you've provied to the command in the configuration file and issues a delete to that CloudFormation Stack name.

When deleting the Network environment the script will issue a command to remove the S3 Endpoint associated with the Network.

To issue a delete command follow the following structure:
```
./deployer.py -c sandbox-us-east-1.yml -p profileName -e <Environment Name> -x update
```

## Starting From Scratch

1. Build a configuration file
2. Create a Environment in configuration
  * Environments require stackname, full_template_url or release, stack_name, template, and optionally parameters
  * release corresponds to a tag or branch which is a prefix to the S3 object keys stored in s3.
..  * To sync with S3 see [s3_sync.sh](/scripts/)
  * stack_name can be any name so long as it's unique to this region, this will be used for the name of the nested stack in cloudformation
  * template is a relative path to the <CloudToolsBucket>/<release>/<path to cloudformation template>. This will typically point to 'cloudformation/project/Environment.json'
  * parameters are used to pass values to the template parameters. See Parameters section above.
  * Environment also allows for lookup_parameters. See Lookup Parameters section above.
3. Boot the Environment
  * `./deployer.py -c prototype-us-east-1.yml -p profileName -e Dev -x create`
4. Follow up by watching the CloudFormation console. 


## Code
deployer.py is the main script. This contains the arguments and options for the scirpt and a main method. This file imports cloudformation.py.

#### cloudformation.py
Abstract class for wrapping the CloudFormation Stack 
~~Network and~~ Environment Stack Classes. 

**Note** 
.. Network Class has been removed, it's irrelivant now. It was in place because of a work around in cloudformation limitations. The abstract class may not be relivant, all of the methods are simmular enough but starting this way provides flexablility if the need arise to model the class in a different way. 
