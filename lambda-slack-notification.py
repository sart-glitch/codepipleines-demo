import json
import logging
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

# Configuration
AWS_REGION = "us-east-1"
CODEBUILD_PROJECT_NAME = "test"
LOG_GROUP_NAME = "/aws/codebuild/test"
S3_BUCKET_NAME = "logs-file-ss"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T05J70CV7FZ/B078U/91X7jcRBIutq"
SLACK_USER = "sarthak"
SLACK_CHANNEL = "#code-commit-alerts"

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def create_codebuild_client(region_name):
    return boto3.client('codebuild', region_name=region_name)

def create_logs_client(region_name):
    return boto3.client('logs', region_name=region_name)

def create_s3_client(region_name):
    return boto3.client('s3', region_name=region_name)

def get_latest_build_id(project_name, region_name):
    codebuild_client = create_codebuild_client(region_name)
    try:
        response = codebuild_client.list_builds_for_project(
            projectName=project_name,
            sortOrder='DESCENDING'
        )
        build_ids = response.get('ids', [])
        if build_ids:
            return build_ids[0]
        else:
            logger.warning("No builds found for project: %s", project_name)
            return None
    except ClientError as e:
        logger.error("ClientError fetching build ID: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error fetching build ID: %s", e)
        return None

def extract_log_stream_id(build_id):
    parts = build_id.split(':')
    if len(parts) > 1:
        return parts[1]
    else:
        logger.warning("Invalid build ID format: %s", build_id)
        return None

def get_log_events(log_group_name, log_stream_id, region_name):
    logs_client = create_logs_client(region_name)
    try:
        response = logs_client.get_log_events(
            logGroupName=log_group_name,
            logStreamName=log_stream_id,
            startFromHead=True
        )
        events = response.get('events', [])
        log_messages = [event.get('message', '') for event in events]
        return log_messages
    except ClientError as e:
        logger.error("ClientError fetching log events: %s", e)
        return []
    except Exception as e:
        logger.error("Unexpected error fetching log events: %s", e)
        return []

def upload_to_s3(file_name, bucket_name, region_name):
    s3_client = create_s3_client(region_name)
    try:
        s3_client.upload_file(file_name, bucket_name, file_name)
        logger.info("File %s uploaded to S3 bucket %s.", file_name, bucket_name)
        return True
    except FileNotFoundError:
        logger.error("File %s not found.", file_name)
        return False
    except NoCredentialsError:
        logger.error("Credentials not available.")
        return False
    except PartialCredentialsError:
        logger.error("Incomplete credentials.")
        return False
    except ClientError as e:
        logger.error("ClientError uploading file to S3: %s", e)
        return False
    except Exception as e:
        logger.error("Unexpected error uploading file to S3: %s", e)
        return False

def generate_presigned_url(bucket_name, file_name, region_name, expiration=3600):
    s3_client = create_s3_client(region_name)
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': file_name},
                                                    ExpiresIn=expiration)
        return response
    except ClientError as e:
        logger.error("ClientError generating presigned URL: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error generating presigned URL: %s", e)
        return None

def post_to_slack(message):
    slack_message = {
        'channel': SLACK_CHANNEL,
        'username': SLACK_USER,
        'text': message
    }
    req = Request(SLACK_WEBHOOK_URL, data=json.dumps(slack_message).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(req)
        response.read()
        logger.info("Message posted to %s", slack_message['channel'])
    except HTTPError as e:
        logger.error("Request failed: %d %s", e.code, e.reason)
    except URLError as e:
        logger.error("Server connection failed: %s", e.reason)

def lambda_handler(event, context):
    logger.info("Event: %s", str(event))
    
    detail = event.get('detail', {})
    pipeline_name = detail.get('pipeline', '')
    state = detail.get('state', '')
    
    slack_message = f'Pipeline {pipeline_name} has {state.lower()}'
    
    # Send notification to Slack
    post_to_slack(slack_message)
    
    if state.lower() in ['succeeded', 'failed']:
        build_id = get_latest_build_id(CODEBUILD_PROJECT_NAME, AWS_REGION)
        if build_id:
            logger.info("Latest Build ID: %s", build_id)
            log_stream_id = extract_log_stream_id(build_id)
            if log_stream_id:
                log_messages = get_log_events(LOG_GROUP_NAME, log_stream_id, AWS_REGION)
                filename = f'/tmp/{build_id}.txt'  # Ensure the file is saved in the /tmp directory
                
                logger.info("Writing logs to %s", filename)
                with open(filename, 'w') as logfile:
                    for message in log_messages:
                        logfile.write(message + '\n')
                
                # Verify file existence before attempting to upload
                if os.path.isfile(filename):
                    logger.info("File %s exists, proceeding with upload", filename)
                    
                    if upload_to_s3(filename, S3_BUCKET_NAME, AWS_REGION):
                        presigned_url = generate_presigned_url(S3_BUCKET_NAME, filename, AWS_REGION)
                        if presigned_url:
                            slack_message += f'\nLog file URL: {presigned_url}'
                            post_to_slack(slack_message)
                        else:
                            logger.error("Failed to generate presigned URL.")
                    else:
                        logger.error("Failed to upload the file to S3.")
                else:
                    logger.error("File %s does not exist, cannot upload", filename)
            else:
                logger.warning("Could not extract log stream ID from the build ID.")
        else:
            logger.warning("Could not retrieve the latest build ID.")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Event processed successfully')
    }
