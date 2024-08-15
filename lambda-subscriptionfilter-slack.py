#https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntax.html

import zlib
import json
import base64
import re
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Environment variables for Slack webhook URL and other settings
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/ZZZZZZZZZZ/B################"
SLACK_USER = "sarthak"
SLACK_CHANNEL = "#code-commit-alerts"

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def extract_codebuild_id(log_messages, default_message="Same as previous build"):
    """Extract CodeBuild ID from log messages. Use default message if not found."""
    # Define a regex pattern to match the full CodeBuild ID
    pattern = re.compile(r'codebuild:([a-zA-Z0-9\-]+)')
    matches = pattern.findall(log_messages)
    if matches:
        return f"codebuild:{matches[0]}"  # Return the first match with "codebuild:" prefix
    return default_message

def post_to_slack(message, codebuild_id):
    """Post the aggregated log message to Slack with enhanced formatting."""
    # If a CodeBuild ID is extracted, include it in the Slack message
    slack_message = {
        'channel': SLACK_CHANNEL,
        'username': SLACK_USER,
        'blocks': [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Aggregated Log Messages"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*CodeBuild ID:* {codebuild_id}\n*Log Summary:*\n" + message
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Logs were aggregated and sent by AWS Lambda."
                    }
                ]
            }
        ]
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
    try:
        # Base64 decode the payload
        base64_payload = event['awslogs']['data']
        compressed_payload = base64.b64decode(base64_payload)
        
        # Decompress the GZIP compressed payload
        decompressed_data = zlib.decompress(compressed_payload, zlib.MAX_WBITS | 16)
        
        # Parse the decompressed data as JSON
        event_data = json.loads(decompressed_data.decode('utf-8'))
        
        # Aggregate all log messages
        if 'logEvents' in event_data and isinstance(event_data['logEvents'], list):
            aggregated_logs = "\n".join(log_event['message'] for log_event in event_data['logEvents'])
        else:
            aggregated_logs = "No log events found."
        
        # Extract CodeBuild ID from the aggregated logs, or use a default message
        codebuild_id = extract_codebuild_id(aggregated_logs)
        
        # Print all aggregated log messages
        print("Aggregated Log Messages:\n", aggregated_logs)
        
        # Send the aggregated logs to Slack
        post_to_slack(aggregated_logs, codebuild_id)
        
        # Indicate successful processing
        return {
            'statusCode': 200,
            'body': json.dumps('Success')
        }
    except Exception as e:
        # Handle errors and log them
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'body': json.dumps('Error occurred')
        }
