# Copyright 2016-2024, Pulumi Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import pulumi
import json
import subprocess
import shutil
import sys
import pulumi_aws as aws
import pulumi_docker as docker
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

config = pulumi.Config()

environment = os.environ.get("ENVIRONMENT")
if environment:
    environment = environment.lower()
else:
    environment = "dev"  # Provide a default value or handle the case appropriately

domain_name = f"{environment}.brighthive.net"

# TODO retrieve dynamically or add to config file:
acm_certificate_arn = "arn:aws:acm:us-west-1:531731217746:certificate/5f4e3233-b886-49a5-9574-045bbca26bc3"

vpc_cidr = config.get("vpc-cidr")
if vpc_cidr is None:
    vpc_cidr = "10.0.0.0/16"
subnet1_cidr = config.get("subnet-1-cidr")
if subnet1_cidr is None:
    subnet1_cidr = "10.0.0.0/24"
subnet2_cidr = config.get("subnet-2-cidr")
if subnet2_cidr is None:
    subnet2_cidr = "10.0.1.0/24"
container_context = config.get("container-context")
if container_context is None:
    container_context = "."
container_file = config.get("container-file")
if container_file is None:
    container_file = "./Dockerfile"
open_api_key = config.get("open-api-key")
if open_api_key is None:
    open_api_key = os.environ.get("OPENAI_API_KEY")
availability_zones = [
    "us-west-1a",
    "us-west-1b",
]
#set region to a region without VPC limit. atempt 

current = aws.get_caller_identity_output()
pulumi_project = pulumi.get_project()
pulumi_stack = pulumi.get_stack()
langserve_ecr_repository = aws.ecr.Repository("langserve-ecr-repository",
    name=f"{pulumi_project}-{pulumi_stack}",
    force_delete=True)
token = aws.ecr.get_authorization_token_output(registry_id=langserve_ecr_repository.registry_id)
account_id = current.account_id
langserve_ecr_life_cycle_policy = aws.ecr.LifecyclePolicy("langserve-ecr-life-cycle-policy",
    repository=langserve_ecr_repository.name,
    policy=json.dumps({
        "rules": [{
            "rulePriority": 1,
            "description": "Expire images when they are more than 10 available",
            "selection": {
                "tagStatus": "any",
                "countType": "imageCountMoreThan",
                "countNumber": 10,
            },
            "action": {
                "type": "expire",
            },
        }],
    }))
langserve_ecr_image = docker.Image("langserve-ecr-image",
    build=docker.DockerBuildArgs(
        platform="linux/amd64",
        context=container_context,
        dockerfile=container_file,
    ),
    image_name=langserve_ecr_repository.repository_url,
    registry=docker.RegistryArgs(
        server=langserve_ecr_repository.repository_url,
        username=token.user_name,
        password=pulumi.Output.secret(token.password),
    ))
langserve_vpc = aws.ec2.Vpc("langserve-vpc",
    cidr_block=vpc_cidr,
    enable_dns_hostnames=True,
    enable_dns_support=True,
    instance_tenancy="default",
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}",
    })
langserve_rt = aws.ec2.RouteTable("langserve-rt",
    vpc_id=langserve_vpc.id,
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}",
    })
langserve_igw = aws.ec2.InternetGateway("langserve-igw",
    vpc_id=langserve_vpc.id,
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}",
    })
langserve_route = aws.ec2.Route("langserve-route",
    route_table_id=langserve_rt.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=langserve_igw.id)
langserve_subnet1 = aws.ec2.Subnet("langserve-subnet1",
    vpc_id=langserve_vpc.id,
    cidr_block=subnet1_cidr,
    availability_zone=availability_zones[0],
    map_public_ip_on_launch=True,
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}-1",
    })
langserve_subnet2 = aws.ec2.Subnet("langserve-subnet2",
    vpc_id=langserve_vpc.id,
    cidr_block=subnet2_cidr,
    availability_zone=availability_zones[1],
    map_public_ip_on_launch=True,
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}-2",
    })
langserve_subnet1_rt_assoc = aws.ec2.RouteTableAssociation("langserve-subnet1-rt-assoc",
    subnet_id=langserve_subnet1.id,
    route_table_id=langserve_rt.id)
langserve_subnet2_rt_assoc = aws.ec2.RouteTableAssociation("langserve-subnet2-rt-assoc",
    subnet_id=langserve_subnet2.id,
    route_table_id=langserve_rt.id)
langserve_ecs_cluster = aws.ecs.Cluster("langserve-ecs-cluster",
    configuration=aws.ecs.ClusterConfigurationArgs(
        execute_command_configuration=aws.ecs.ClusterConfigurationExecuteCommandConfigurationArgs(
            logging="DEFAULT",
        ),
    ),
    settings=[aws.ecs.ClusterSettingArgs(
        name="containerInsights",
        value="disabled",
    )],
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}",
    })
langserve_cluster_capacity_providers = aws.ecs.ClusterCapacityProviders("langserve-cluster-capacity-providers",
    cluster_name=langserve_ecs_cluster.name,
    capacity_providers=[
        "FARGATE",
        "FARGATE_SPOT",
    ])
langserve_security_group = aws.ec2.SecurityGroup("langserve-security-group",
    vpc_id=langserve_vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        protocol="tcp",
        from_port=5432,
        to_port=5432,
        cidr_blocks=["0.0.0.0/0"],
    ),
    aws.ec2.SecurityGroupIngressArgs(
        protocol="tcp",
        from_port=80,
        to_port=80,
        cidr_blocks=["0.0.0.0/0"],
    ),
    aws.ec2.SecurityGroupIngressArgs(
        protocol="tcp",
        from_port=8000,
        to_port=8000,
        cidr_blocks=["0.0.0.0/0"],
    ),
    aws.ec2.SecurityGroupIngressArgs(
        protocol="tcp",
        from_port=443,
        to_port=443,
        cidr_blocks=["0.0.0.0/0"],
    ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        protocol="-1",
        from_port=0,
        to_port=0,
        cidr_blocks=["0.0.0.0/0"],
    )])
langserve_load_balancer = aws.lb.LoadBalancer("langserve-load-balancer",
    load_balancer_type="application",
    security_groups=[langserve_security_group.id],
    subnets=[
        langserve_subnet1.id,
        langserve_subnet2.id,
    ])
langserve_target_group = aws.lb.TargetGroup("langserve-target-group",
    port=8000,
    protocol="HTTP",
    target_type="ip",
    vpc_id=langserve_vpc.id)
langserve_listener = aws.lb.Listener("langserve-listener",
    load_balancer_arn=langserve_load_balancer.arn,
    port=8000,
    protocol="HTTP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=langserve_target_group.arn,
    )])
langserve_listener_https = aws.lb.Listener("langserve-listener-https",
    load_balancer_arn=langserve_load_balancer.arn,
    port=443,
    protocol="HTTPS",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=langserve_target_group.arn,
    )],
    certificate_arn=acm_certificate_arn,
)
langserve_log_group = aws.cloudwatch.LogGroup("langserve-log-group", retention_in_days=7)
langserve_key = aws.kms.Key("langserve-key",
    description="Key for encrypting secrets",
    enable_key_rotation=True,
    policy=account_id.apply(lambda account_id: json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{account_id}:root",
                },
                "Action": [
                    "kms:Create*",
                    "kms:Describe*",
                    "kms:Enable*",
                    "kms:List*",
                    "kms:Put*",
                    "kms:Update*",
                    "kms:Revoke*",
                    "kms:Disable*",
                    "kms:Get*",
                    "kms:Delete*",
                    "kms:ScheduleKeyDeletion",
                    "kms:CancelKeyDeletion",
                    "kms:Tag*",
                    "kms:UntagResource",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{account_id}:root",
                },
                "Action": [
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                "Resource": "*",
            },
        ],
    })),
    tags={
        "pulumi-application": pulumi_project,
        "pulumi-environment": pulumi_stack,
    })
langserve_ssm_parameter = aws.ssm.Parameter("langserve-ssm-parameter",
    type="SecureString",
    value=open_api_key,
    key_id=langserve_key.key_id,
    name=f"/pulumi/{pulumi_project}/{pulumi_stack}/OPENAI_API_KEY",
    tags={
        "pulumi-application": pulumi_project,
        "pulumi-environment": pulumi_stack,
    })

langserve_execution_role = aws.iam.Role("langserve-execution-role",
    assume_role_policy=json.dumps({
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com",
            },
        }],
        "Version": "2012-10-17",
    }),
    inline_policies=[aws.iam.RoleInlinePolicyArgs(
        name=f"{pulumi_project}-{pulumi_stack}-service-secrets-policy",
        policy=pulumi.Output.all(langserve_ssm_parameter.arn, langserve_key.arn).apply(lambda args: json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": ["ssm:GetParameters"],
                    "Condition": {
                        "StringEquals": {
                            "ssm:ResourceTag/pulumi-application": pulumi_project,
                            "ssm:ResourceTag/pulumi-environment": pulumi_stack,
                        },
                    },
                    "Effect": "Allow",
                    "Resource": [args[0]],
                },
                {
                    "Action": ["kms:Decrypt"],
                    "Condition": {
                        "StringEquals": {
                            "aws:ResourceTag/pulumi-application": pulumi_project,
                            "aws:ResourceTag/pulumi-environment": pulumi_stack,
                        },
                    },
                    "Effect": "Allow",
                    "Resource": [args[1]],
                    "Sid": "DecryptTaggedKMSKey",
                },
            ],
        })),
    )],
    managed_policy_arns=["arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"])

database_security_group = aws.ec2.SecurityGroup(
    "rds-sg",
    vpc_id=langserve_vpc.id,
    ingress=[{
        "protocol": "tcp",
        "from_port": 5432,
        "to_port": 5432,
        "cidr_blocks": ["0.0.0.0/0"]
    }],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }]
)
langserve_database_cluster = aws.rds.Cluster(
    "langserve-database",
    engine=aws.rds.EngineType.AURORA_POSTGRESQL,
    engine_mode=aws.rds.EngineMode.PROVISIONED,
    engine_version="15.6",
    database_name=os.environ["POSTGRES_DB"],
    master_username=os.environ["POSTGRES_USER"],
    master_password=os.environ["POSTGRES_PASSWORD"],
    storage_encrypted=True,
    serverlessv2_scaling_configuration=aws.rds.ClusterServerlessv2ScalingConfigurationArgs(
        max_capacity=1,
        min_capacity=0.5,
    ),
    vpc_security_group_ids=[database_security_group.id],
    db_subnet_group_name=aws.rds.SubnetGroup("langserve-subnet-group",
        subnet_ids=[langserve_subnet1, langserve_subnet2],
        tags={
            "Name": "langserve-subnet-group"
        }).name,
    skip_final_snapshot=True,
)

langserve_cluster_instance = aws.rds.ClusterInstance(
    "langserve-cluster-instance",
    cluster_identifier=langserve_database_cluster.id,
    instance_class="db.serverless",
    engine=langserve_database_cluster.engine,
    engine_version=langserve_database_cluster.engine_version,
)

langserve_task_role = aws.iam.Role("langserve-task-role",
    assume_role_policy=json.dumps({
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com",
            },
        }],
        "Version": "2012-10-17",
    }),
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="ExecuteCommand",
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": [
                            "ssmmessages:CreateControlChannel",
                            "ssmmessages:OpenControlChannel",
                            "ssmmessages:CreateDataChannel",
                            "ssmmessages:OpenDataChannel",
                        ],
                        "Effect": "Allow",
                        "Resource": "*",
                    },
                    {
                        "Action": [
                            "logs:CreateLogStream",
                            "logs:DescribeLogGroups",
                            "logs:DescribeLogStreams",
                            "logs:PutLogEvents",
                        ],
                        "Effect": "Allow",
                        "Resource": "*",
                    },
                ],
            }),
        ),
        aws.iam.RoleInlinePolicyArgs(
            name="DenyIAM",
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": "iam:*",
                    "Effect": "Deny",
                    "Resource": "*",
                }],
            }),
        ),
    ])
langserve_task_definition = aws.ecs.TaskDefinition("langserve-task-definition",
    family=f"{pulumi_project}-{pulumi_stack}",
    cpu="256",
    memory="512",
    network_mode="awsvpc",
    execution_role_arn=langserve_execution_role.arn,
    task_role_arn=langserve_task_role.arn,
    requires_compatibilities=["FARGATE"],
    container_definitions=pulumi.Output.all(
        langserve_ecr_image.repo_digest, 
        langserve_ssm_parameter.name, 
        langserve_log_group.name,
        langserve_cluster_instance.endpoint,
        langserve_cluster_instance.port,
        langserve_database_cluster.database_name,
        langserve_database_cluster.master_username,
        langserve_database_cluster.master_password
    ).apply(lambda args: json.dumps([{
        "name": f"{pulumi_project}-{pulumi_stack}-service",
        "image": args[0],
        "cpu": 0,
        "portMappings": [{
            "name": "target",
            "containerPort": 8000,
            "hostPort": 8000,
            "protocol": "tcp",
        }],
        "essential": True,
        "secrets": [{
            "name": "OPENAI_API_KEY",
            "valueFrom": args[1],
        }],
        "environment": [
            {"name": "POSTGRES_HOST", "value": args[3]},
            {"name": "POSTGRES_PORT", "value": str(args[4])},
            {"name": "POSTGRES_DB", "value": str(args[5])},
            {"name": "POSTGRES_USER", "value": args[6]},
            {"name": "POSTGRES_PASSWORD", "value": args[7]}
        ],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": args[2],
                "awslogs-region": "us-west-1",
                "awslogs-stream-prefix": "pulumi-langserve",
            },
        },
    }])))
langserve_ecs_security_group = aws.ec2.SecurityGroup("langserve-ecs-security-group",
    vpc_id=langserve_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        protocol="-1",
        from_port=0,
        to_port=0,
        cidr_blocks=["0.0.0.0/0"],
    )])
langserve_service_discovery_namespace = aws.servicediscovery.PrivateDnsNamespace("langserve-service-discovery-namespace",
    name=f"{pulumi_stack}.{pulumi_project}.local",
    vpc=langserve_vpc.id)
langserve_service = aws.ecs.Service("langserve-service",
    cluster=langserve_ecs_cluster.arn,
    task_definition=langserve_task_definition.arn,
    desired_count=1,
    launch_type="FARGATE",
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        assign_public_ip=True,
        security_groups=[langserve_ecs_security_group.id],
        subnets=[
            langserve_subnet1.id,
            langserve_subnet2.id,
        ],
    ),
    load_balancers=[aws.ecs.ServiceLoadBalancerArgs(
        target_group_arn=langserve_target_group.arn,
        container_name=f"{pulumi_project}-{pulumi_stack}-service",
        container_port=8000,
    )],
    scheduling_strategy="REPLICA",
    service_connect_configuration=aws.ecs.ServiceServiceConnectConfigurationArgs(
        enabled=True,
        namespace=langserve_service_discovery_namespace.arn,
    ),
    tags={
        "Name": f"{pulumi_project}-{pulumi_stack}",
    })

# Define the IAM role for the Lambda function
sql_migration_lambda_role = aws.iam.Role("langserve-lambda-role",
    assume_role_policy="""{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": "sts:AssumeRole",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Effect": "Allow",
            "Sid": ""
        }
    ]
    }""")

sql_migration_lambda_policy = aws.iam.RolePolicy(
    "langserve-lambda-policy",
    role=sql_migration_lambda_role.id,
    policy="""{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "rds:*",
                "logs:*",
                "cloudwatch:*"
            ],
            "Resource": "*"
        }
    ]
    }""")


aws.iam.RolePolicyAttachment(
    "lambda-vpc-access-execution-role-attachment",
    role=sql_migration_lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
)

FUNCTION_CODE_DIR = "./backend/sql"
LAMBDA_PACKAGE_DIR = "./lambda_package"

# Clean up any existing package directory
if os.path.exists(LAMBDA_PACKAGE_DIR):
    shutil.rmtree(LAMBDA_PACKAGE_DIR)

os.makedirs(LAMBDA_PACKAGE_DIR, exist_ok=True)

# Install psycopg2 into the package directory
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "psycopg2-binary", "-t", LAMBDA_PACKAGE_DIR, "--platform", "manylinux2014_x86_64", "--no-deps", "--only-binary", ":all:"]
)

# Copy the function code to the package directory
shutil.copytree(FUNCTION_CODE_DIR, os.path.join(LAMBDA_PACKAGE_DIR, "code"))

# Package the Lambda function and its dependencies
shutil.make_archive(f"{LAMBDA_PACKAGE_DIR}/lambda_package", 'zip', LAMBDA_PACKAGE_DIR)

sql_migration_lambda_function = aws.lambda_.Function(
    'sql-migrations-lambda-function',
    code=pulumi.FileArchive(f"{LAMBDA_PACKAGE_DIR}/lambda_package.zip"),
    runtime='python3.9',
    role=sql_migration_lambda_role.arn,
    handler='code.sql_migration_lambda_function.lambda_handler',
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            'POSTGRES_HOST': langserve_cluster_instance.endpoint,
            'POSTGRES_PORT': langserve_cluster_instance.port,
            'POSTGRES_DB': langserve_database_cluster.database_name,
            'POSTGRES_USER': langserve_database_cluster.master_username,
            'POSTGRES_PASSWORD': langserve_database_cluster.master_password
        }
    ),
    vpc_config=aws.lambda_.FunctionVpcConfigArgs(
        subnet_ids=[langserve_subnet1.id, langserve_subnet2.id],
        security_group_ids=[database_security_group.id]
    ),
    opts=pulumi.ResourceOptions(depends_on=[langserve_cluster_instance])
)


# Route53
hosted_zone = aws.route53.get_zone(name=domain_name)

if hosted_zone.zone_id is None or len(hosted_zone.zone_id) == 0:
    raise ValueError(f"Could not find hosted zone for domain {domain_name}")
else:
    hosted_zone_id = hosted_zone.zone_id[0]

bbassistantsDomain = f"bbassistants.{environment}.brighthive.net"

a_record = aws.route53.Record("a-record",
    name=bbassistantsDomain,
    zone_id=hosted_zone.zone_id,
    type="A",
    aliases=[aws.route53.RecordAliasArgs(
        name=langserve_load_balancer.dns_name,
        zone_id=langserve_load_balancer.zone_id,
        evaluate_target_health=True,
    )],
)


pulumi.export("url", langserve_load_balancer.dns_name.apply(lambda dns_name: f"http://{dns_name}"))

