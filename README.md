# Deployer

Deployer is used to create | update | delete CloudFormation Stacks

# Install using docker
Running deployer via docker avoids some homebrew python headaches on MacOS.

When you want to install a new version of deployer:

``` shell
ver=x.x.x
git fetch --all --tags
git checkout tags/$ver -b $ver
git checkout master  -- Dockerfile
cat Dockerfile  | docker build -t deployer:$ver --build-arg VER=$ver -f- $PWD
git checkout -
git branch -D $ver
```


## deployer bash function
This function allows you to run `deployer -c config/us-east...`
``` 
deployer () {
  docker run --rm --init -it -v $PWD:/workspace -v $HOME/.aws:/deployerUser/.aws deployer:0.4.4 deployer "$@"
}
```

# Install
Deployer is now a pip installable package and comes with two command line entry scripts, `deployer` and `config_updater`
To install, simply:
```
pip install path/to/deployer-<version>.tar.gz
```

# Use
Deployer is free for use by RightBrain Networks Clients however comes as is with out any guarantees.

##### Flags
* -c --config <config file> (REQUIRED) : Yaml configuration file to run against.
* -s --stack <stack name>  (REQUIRED) : Stack Name corresponding to a block in the config file.
* -x --execute <execute command> (REQUIRED) : create|update|delete|sync|change Action you wish to take on the stack.
* -p --profile <profile>     : AWS CLI Profile to use for AWS commands [CLI Getting Started](http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html).
* -P --param <PARAM>, --param PARAM An override for a parameter
* -y --copy <copy>        : Copy directory structures specified in the configuration file under the sync_dirs configuration.
* -A --all         : Create or Update all stacks in the configuration file, Note you do not have to specify a stack when using this option.
* -r --disable-roleback : Disable rollback on failure, useful when trying to debug a failing stack.
* -t --timeout : Sets Stack create timeout
* -e --events : Display events of the CloudFormation stack at regular intervals.
* -z --zip         : Pip install requirements, and zip up lambda's for builds.
* -t --change-set-name <change set name> (REQUIRED Change Sets Only) : Used when creating a change set to name the change set.
* -d --change-set-description <change set description> (REQUIRED Change Sets Only) : Used when creating a change set to describe the change set.
* -j, --assume-valid    Assumes templates are valid and does not do upstream validation (good for preventing rate limiting)
* -D, --debug           Sets logging level to DEBUG & enables traceback
* -v, --version         Print version number
* --init [INIT]         Initialize a skeleton directory
* --disable-color       Disables color output



##### Examples
Create a stack and copy specified directories to S3.
`./deployer -c config.yml -s MyStack -x create -p profileName -y`

Update a stack and display the events. 
`./deployer -c config.yml -s DevDerek -x update -p profileName -e`

Copy to S3, and create a change set and display what will change during an update.
`./deployer -c config.yml -s MyStack -x change -t MyChangeSetName -d 'This is a description of my change' -y -p profileName`

Copy to S3, and create a new stack and disable CloudFormation from rolling back so you can debug.
`./deployer -c config.yml -s MyStack -x create -p profileName -y -r`

Just copy to s3.
`./deployer -c config.yml -s MyStack -x sync -p profileName`

Zip up lambdas, copy to s3, and update.
`./deployer -c config.yml -s MyStack -x update -p profileName -y -z`

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
* Sync skips files to upload to S3 based on their etag and MD5 hash sums.
* Sync will automatically validate all templates before it sends them to S3. To preserve time and not abuse the CFN API (it's rate limited) sync will only validate if the MD5 hash and etag do not match.

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
These parameters correspond to parameters that need to be passed to the Top.json template. `deployer` tolerates but logs parameters that exist within the configuration but do not exist within the template.

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

These are parameters that can be pulled from another stack's output. `deployer` tolerates but logs parameters that exist within the configuration but do not exist within the template.
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

## Dependencies

Deployer uses a depdency graph to find the depedencies of the `lookup_parameters`. This makes it easy to run stacks with the `--all` flag.

You can also use the `depends_on` value to manually override the dependency graph.

Example:

```yaml
test:
    stack_name: test
    depends_on: [ other_stack ]

other_stack:
    stack_name: test-two
```

## Tags
Tags are key value pairs of tags to be applied to the Top level stack. This will tag every resouce within the stack with these tags as well as all resouces in child stacks. Use this for things like Environment, Release, Project, etc tags. 
```
  tags:
    MyKey1: MyValue1
    Project: Alt-Lab
    Environment: Dev
    Release : development
```

## Transforms
Denote that at tranform is used in a stack and deployer will automatically create change set and execute change set. 
```
  transforms: true
```

## Updates
When running updates to a stack you'll be running updates to the CloudFormation Stack specified by Stack. 

Updates to CloudFormation will change the living Infrastructure based on your current configuration. 
```
./deployer -c sandbox-us-east-1.yml -p profileName -s <Environment Name> -x update
```


## Deletes
When using this script to delete it simply looks up the stack variable you've provied to the command in the configuration file and issues a delete to that CloudFormation Stack name.
  * Environments require stack_name, full_template_url or release, stack_name, template, and optionally parameters
  * release corresponds to a tag or branch which is a prefix to the S3 object keys stored in s3.
  * To sync with S3 add sync_base, sync_dirs, sync_dest_bucket, and optionally sync_exclude and use the -y flag when running deployer.
  * Stack_name can be any name so long as it's unique to this region and account, this will be used for the name of the nested stack in cloudformation
  * Template is a relative path to the <CloudToolsBucket>/<release>/<path to cloudformation template>. This will typically point to 'cloudformation/project/top.json'
  * Parameters are used to pass values to the template parameters. See Parameters section above.
  * Stack also allows for lookup_parameters. See Lookup Parameters section above.
3. Boot the Environment
  * `./deployer -c prototype-us-east-1.yml -p profileName -s Dev -x create`
4. Follow up by watching the CloudFormation console. 

## Working with Stack Sets
To run a stack as a stack set, add `administration_role` and `execution_role` as elements inside of the deployer config file. You will also need to add `accounts` and `regions` as properties of your stack.

Example:
```yaml
global:
    administration_role: StackSetAdminRole
    execution_role: RemoteAccount-DeploymentRole
...

ExampleStackSet:
    accounts:
      - '000000000'
      - '000000000'
    regions:
      - 'us-east-1'
      - 'us-west-2'
...
```

## Code
__init__.py is the main script. This contains the arguments and options for the scirpt and a main method. This file imports cloudformation.py and s3_sync.py.

### cloudformation.py
Abstract class for wrapping the CloudFormation Stack.
Currenly there is only the Stack class, Network and Environment classes are now obsolete.

### s3_sync.py
This is the class that builds zip archives for lambdas and copies directories to s3 given the configuration in the config file.

**Note** 
Network Class has been removed, it's irrelivant now. It was in place because of a work around in cloudformation limitations. The abstract class may not be relivant, all of the methods are simmular enough but starting this way provides flexablility if the need arise to model the class in a different way. 


# Config Updater

The `config_updater` command is meant to help with updating config files in the CI/CD process to allow for automated deploys via deployer. Specify the config file you need to update then a JSON string representing the changes that need to take place. You can update multiple environments or attributes at once. 

## Usage

* -c <config file> (REQUIRED) : Yaml configuration file to run against.
* -u <updates> (REQUIRED) : JSON formated string representing the changes you want to take place

## Example

`./config_updater -c example_configs/dummy.yml -u "{ \"Network\": { \"release\": \"$RELEASE\", \"parameters\":{ \"VirtualPrivateGateway\":\"someotherthing\"} } }"`
`./config_updater -c example_configs/dummy.yml -u '{ "Network": { "release": "1.0.2" }, "Dev-Env": { "release": "1.0.2" } }'`

# Getting Started

You can set up the initial directory structure for deployer by running it with the `--init` flag:

```
deployer --init
```

This will create a directory tree like the following in your current directory:

```
.
├── cloudformation
│   ├── deployer
│   │   └── top.yaml
│   └── vpc
│       ├── az.yaml
│       ├── endpoints.yaml
│       ├── flow-logs.yaml
│       ├── route53.yaml
│       ├── security-groups.yaml
│       ├── ssm.yaml
│       ├── subnets.yaml
│       ├── supernets.yaml
│       ├── top.yaml
│       ├── transit-gateway.yaml
│       └── vpc.yaml
└── config
    └── shared.yaml
```

This initial setup includes two example stacks: `deployer` and `vpc`. It also includes a barebones configuration to let you deploy them.

> WARNING: This guide assumes you are running inside of a git repository. Deployer will use some values from git to set some defaults while deploying. If you are not running in git you will need to add the following line to the `config/shared.yaml` file under the `vpc` top level node:
>
> ```
>   release: develop
> ```

Let's try deploying the `deployer` stack. This stack creates a bucket to store CloudFormation templates and sets an SSM parameter that allows deployer to find the bucket. Once this bucket is created we can use deployer to deploy more complex stacks with nested templates such as the `vpc` stack.

To deploy the `deployer` stack run the command:

```
deployer -x upsert -c config/shared.yaml -s deployer
```

To break down the arguments of this command:

`-x upsert` - This tells deployer to create the stack if it doesn't currently exist. If it does exist it will perform an update.

`-c config/shared.yaml` - This is the deployer configuration file we want to use. This file defines the configuration (sync directories, parameters, etc) for one or more stacks.

`-s deployer` - This is the top level name of a node in the `config/shared.yaml` file that we passed in the previous argument. It tells deployer which stack to deploy.

Once the `deployer` stack is updated we can deploy the `vpc` stack. This stack provides a good starting point for deploying a new VPC and allows for a good amount of customization through parameters alone.

```
deployer -x upsert -c config/shared.yaml -s vpc -y
```

This command works like the command we used to deploy the `deployer` stack. The only difference is the last parameter:

`-y` - This parameter tells deployer to upload all the files related to the stack to the bucket created in the `deployer` stack.

Which files get uploaded is specified in the config file with the `sync_dirs` directive:

```
vpc:
  stack_name: shared-vpc
  template: cloudformation/vpc/top.yaml
  sync_dirs:
    - cloudformation/vpc
```

Deployer will give you a series of updates as the deployment happens to show you the progress of the current deployment. Once it is finished you should have a new vpc with the IP address range of 10.138.0.0/16 if you kept the default configuration.

Now that your stack is deployed lets take a look at a couple of important sections of the `cloudformation/vpc/top.yaml` template that we just deployed:

```
Parameters:
  BucketCloudTools:
    Default: /global/buckets/cloudtools/name
    Description: S3 bucket holding CloudFormation templates
    Type: AWS::SSM::Parameter::Value<String>
  Release:
    Description: Release name
    Type: String
```

This stack contains a couple of special parameters:

`BucketCloudTools` - This is the S3 bucket that deployer synced our files to. It is referenced using the SSM parameter that was created when we deployed the `deployer` stack. This parameter is `/global/buckets/cloudtools/name`. It is a special parameter that deployer checks to know where to upload files to.

`Release` - This parameter is not actually passed as a parameter in the configuration. When deployer uploads files if doesn't put them in the root of the bucket. Instead it prefixes them with a release name so as to not accidentally overwrite files in previous deployments. You can specify the release name in the deployer config with the `release` directive. If this directive isn't set and you are using git the release will be automatically set to the current commit hash. Deployer automatically passes this parameter if it detects it defined in the `Parameters` section of the template.

```
Resources:
  Vpc:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: !Sub 'https://s3.${AWS::Region}.amazonaws.com/${BucketCloudTools}/${Release}/cloudformation/vpc/vpc.yaml'
```

Our top template contains numerous references to child templates. Using a combination of our `BucketCloudTools` parameter and `Release` parameter we can reference these files in s3. The line below references the file `cloudformation/vpc/vpc.yaml` from our local workspace:

```
!Sub 'https://s3.${AWS::Region}.amazonaws.com/${BucketCloudTools}/${Release}/cloudformation/vpc/vpc.yaml'
```

You can add your own templates under the `cloudformation` directory to deploy your own stacks. Each stack will also need an entry in your deployer config file to specify which directories should be uploaded, the name of the stack, and any required parameters.
