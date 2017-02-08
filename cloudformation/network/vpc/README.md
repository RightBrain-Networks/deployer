# [CloudFormation](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html)

## Terminology
1. **Template**: The descriptive syntax json files describing the resources to be built. 
2. **Stack**: Collection of resources built from a Template. 
3. **Top-Level Stack**: A stack that contains or controls other stacks. 
4. **Resource**: Any "thing" in aws. 
5. **Parameter**: Input to a Template or Stack. 
6. **Mapping**: Two Level hash map or dictionary containing static information 
7. **Conditional**: Binary logic within the Template. 
8. **Outputs**: Data output by stack after completion, useful for tying outputs from one stack to inputs of another in a nested template. 
9. **Intrinsic Functions**: Functions evaluated by the template, like references to other resources. [Intrinsic Functions Docs](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference.html)
10. **Pseudo Parameters**: Parameters provided from AWS like Environment parameters to the stack these are things like Region being ran in etc. [Pseudo Parameter Docs](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/pseudo-parameter-reference.html)
   [Template Anatomy](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html)

## CloudFormation Layout
The Top.json files are top level nested stacks that allow us to build stacks off different CloudFromation templates. Parameters or input to this stack determine how the template is evaluated and what resources the template creates. 
[Nested Stacks RBN Blog](http://www.rightbrainnetworks.com/blog/cloudformation-zen-nested-stacks/)
The Top stack controls the input output mapping between stacks. For instance, The Security_Groups.json template is referenced within the Top stack, the Top stack will use this template to build a SecurityGroup stack, this SecurityGroup stack will create SecurityGroup with access control according to the template then output the Physical Id's of the Security Groups. These Security Group ID's can be provided to other stacks as parameters and used in other child stacks.

In the SecurityGroup stack is where all of the security groups are configured with ingress and egress rules. All of these resources are built and the ID of that resource returned so that the Top level stack can coordinate passing that ID to a App stack for the application to use as a security group.

In side the Top.json stack you will find all of child stacks that make up the Network. Each of these stacks references a template within your repository. The name of the template is descriptive of what's it will build. This is a modular template that will build like infrastructure for stacks. These templates are used as building blocks for the Top Template to manipulate and build the Network.

Subnets are mearly public and private in each Az.

Keep in mind that a lot of these templates are modular and that making changes to one template may effect multiple stacks.

## [Network](./Top.json)
The Network is deployed as a single atomic unit. 

1. [top.json](./top.json): Top level Stack.
2. [sns.json](./sns.json): for SNS topics.
3. [vpc.json](./vpc.json): Contains a Custom Resource call to a lambda function built in Custom_Logic.json which returns a CIDR that's available given its run time see [README](../README.md) for more info. The template builds the VPC, Internet Gateway, Vitual Private Gatway, VPC Peering and Route Tables, DHCP Options and S3 Endpoint. 
4. [security_groups.json](./security_groups.json): Builds NAT and Bastion security Groups.
5. [subnets.json](./subnets.json): Contains a Custom Resource call to a lambda function built in Custom_Logic.json which dynamically splits the VPC CIDR into 8 equally spaced Subnet CIDR's. The template then builds a public and private subnet in each AZ available and attaches it to the appropriate route table.
6. [nat.json](./nat.json): Builds a VPC NAT Gateway per Availability Zone in the given region in Public Subnets that were built in the Subnet.json
7. [bastion](./amzn_linux_asg.json): Is a generic asg template that boots a bastion host. 

## Making Changes
This Repository follows [GitFlow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow).

**Branch before you make any changes.**

[AWS Resource Reference](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)

