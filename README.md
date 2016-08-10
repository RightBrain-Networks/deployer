# Deployer

Deployer is used to create | update | delete CloudFormation Stacks

## Clone and use
Clone Deployer into a directory of your choice. Edit your ~/.bashrc and add an alias like this `alias deployer='/my/path/to/deployer.py'`

## Client Use
When you use Deployer in a project we should give it to the client. Clone or copy a particular release of deployer into the aws-tools repo for the client to use. 

##### Flags
* -c <config file> (REQUIRED) -- Yaml configuration file to run against.
* -s <stack name>  (REQUIRED) -- Stack Name corresponding to a block in the config file.
* -x <execute command> (REQUIRED) -- create|update|delete|sync|change Action you wish to take on the stack.
* -p <profile>     (REQUIRED) -- AWS CLI Profile to use for AWS commands [CLI Getting Started](http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html).
* -y <copy>        -- Copy directory structures specified in the configuration file under the sync_dirs configuration.
* -A <All>         -- Create or Update all stacks in the configuration file, Note you do not have to specify a stack when using this option.
* -r <disable rollback> -- Disable rollback on failure, useful when trying to debug a failing stack.
* -e <display events> -- Display events of the CloudFormation stack at regular intervals.
* -z <zip>         -- Pip install requirements, and zip up lambda's for builds.
* -t <change set name> (REQUIRED Change Sets Only) -- Used when creating a change set to name the change set.
* -d <change set description> (REQUIRED Change Sets Only) -- Used when creating a change set to describe the change set.


##### Examples
Create a stack and copy specified directories to S3.
`./deployer.py -c config.yml -s MyStack -x create -p profileName -y`

Update a stack and display the events. 
`./deployer.py -c config.yml -s DevDerek -x update -p profileName -e`

Copy to S3, and create a change set and display what will change during an update.
`./deployer.py -c config.yml -s MyStack -x change -t MyChangeSetName -d 'This is a description of my change' -y -p profileName`

Copy to S3, and create a new stack and disable CloudFormation from rolling back so you can debug.
`./deployer.py -c config.yml -s MyStack -x create -p profileName -y -r`

Just copy to s3.
`./deployer.py -c config.yml -s MyStack -x sync -p profileName`

Zip up lambdas, copy to s3, and update.
`./deployer.py -c config.yml -s MyStack -x update -p profileName -y -z`

# The Config

*Note* See [example_configs/dev-us-east-1.yml](./example_configs/dev-us-east-1.yml) for an example configuration file.

The config is a large dictionary. First keys within the dictionary are Stack Names. The global Environment Parameters is a common ground to deduplicate parameter entries that are used in each Stack. Stack parameters overwrite global parameters. 

## Required
The following are required for each stack, they can be specified specifically to the stack or in the global config.
* All stacks need a stack_name.
* All stacks need to construct the stacks template, you can either specify full_template_url or template_bucket, release, and template combined.
* All stacks need a release. 
* All stacks need a region. 


## Sync
Command line takes a optional -y to copy files to s3. The code will walk {sync_base} for {sync_dirs} recursively for files to upload. S3 path of object based on concatenation of Stack Keys: {sync_dest_bucet}/{release}/{sync_dir}/{recursive_file_path}
* sync_base: Base of repository to sync to s3.
* sync_dirs: Directories from sync_base to sync to s3.
* sync_dest_bucket: S3 bucket to sync to.
* sync_exclude: A list of expressions to exclude from the copy, example might be .swp or .git.

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

## Parameters
These parameters correspond to parameters that need to be passed to the Top.json template.

These parameters provide identity to the Services like what AMI to use or what bootstrap file to pull even the size of the instance.
```
    parameters:
      Monitoring: 'True'
      NginxAMI: ami-cbb9ecae
      NginxInstanceType: t2.medium
...
      UploadAMI: ami-3069145a
      UploadInstanceType: t2.medium
```

## Lookup Parameters

These are parameters that can be pulled from another stack's output. 
* The key in this key value pair is the ParameterKey being passed to this Stack. 
* The Value is a custom structure that requires a Stack and OutputKey. 
* The stack is the Stack name and the OutputKey is the name of the output from the stack being targeted. The script will fetch the stack output and retrieve the output key, using it's value for the parameter value. 

These are mainly used for pulling data from the Network Stacks like SNS topics or Subnets
```
    lookup_parameters:
      VPC: { Stack: Network, OutputKey: VPC }
      VPCCIDR: { Stack: Network, OutputKey: VPCCIDR }
      PublicSubnets: { Stack: Network, OutputKey: DevPublicSubnets }
      PrivateSubnets: { Stack: Network, OutputKey: DevPrivateSubnets }
```
In this case, VPC is a parameter to this stack, the code will pull output data from the Network Stack and look for the OutputKey of VPC. The Value of the OutputKey VPC in the Network Stack will be used for the parameter VPC of this stack. 

## Tags
Tags are key value pairs of tags to be applied to the Top level stack. This will tag every resouce within the stack with these tags as well as all resouces in child stacks. Use this for things like Environment, Release, Project, etc tags. 
```
  tags:
    MyKey1: MyValue1
    Project: Alt-Lab
    Environment: Dev
    Release : development
```

## Updates
When running updates to a stack you'll be running updates to the CloudFormation Stack specified by Stack. 

Updates to CloudFormation will change the living Infrastructure based on your current configuration. 
```
./deployer.py -c sandbox-us-east-1.yml -p profileName -s <Environment Name> -x update
```


## Deletes
When using this script to delete it simply looks up the stack variable you've provied to the command in the configuration file and issues a delete to that CloudFormation Stack name.

To issue a delete command follow the following structure:
```
./deployer.py -c sandbox-us-east-1.yml -p profileName -s <Environment Name> -x delete
```

## Starting From Scratch

1. Build a configuration file
2. Create a Stack in the configuration
  * Environments require stack_name, full_template_url or release, stack_name, template, and optionally parameters
  * release corresponds to a tag or branch which is a prefix to the S3 object keys stored in s3.
  * To sync with S3 add sync_base, sync_dirs, sync_dest_bucket, and optionally sync_exclude and use the -y flag when running deployer.
  * Stack_name can be any name so long as it's unique to this region and account, this will be used for the name of the nested stack in cloudformation
  * Template is a relative path to the <CloudToolsBucket>/<release>/<path to cloudformation template>. This will typically point to 'cloudformation/project/top.json'
  * Parameters are used to pass values to the template parameters. See Parameters section above.
  * Stack also allows for lookup_parameters. See Lookup Parameters section above.
3. Boot the Environment
  * `./deployer.py -c prototype-us-east-1.yml -p profileName -s Dev -x create`
4. Follow up by watching the CloudFormation console. 


## Code
deployer.py is the main script. This contains the arguments and options for the scirpt and a main method. This file imports cloudformation.py and s3_sync.py.

### cloudformation.py
Abstract class for wrapping the CloudFormation Stack.
Currenly there is only the Stack class, Network and Environment classes are now obsolete.

### s3_sync.py
This is the class that builds zip archives for lambdas and copies directories to s3 given the configuration in the config file.

**Note** 
Network Class has been removed, it's irrelivant now. It was in place because of a work around in cloudformation limitations. The abstract class may not be relivant, all of the methods are simmular enough but starting this way provides flexablility if the need arise to model the class in a different way. 
