#use python 3.9
import json
import logging
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
 
# Read all the environment variables
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T05J/B90i9o8/11111111111111111111"
SLACK_USER = "sample-user"
SLACK_CHANNEL = "#code-lambda-alerts"
 
# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)
 
def lambda_handler(event, context):
    logger.info("Event: " + str(event))
    # Extract details from the event
    detail = event.get('detail', {})
    pipeline_name = detail.get('pipeline', '')
    state = detail.get('state', '')
 
    # Construct a new Slack message based on the event details
    slack_message = {
        'channel': SLACK_CHANNEL,
        'username': SLACK_USER,
        'text': f'Pipeline {pipeline_name} has {state.lower()}'
    }
 
    # Post message to Slack
    req = Request(SLACK_WEBHOOK_URL, data=json.dumps(slack_message).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(req)
        response.read()
        logger.info("Message posted to %s", slack_message['channel'])
    except HTTPError as e:
        logger.error("Request failed: %d %s", e.code, e.reason)
    except URLError as e:
        logger.error("Server connection failed: %s", e.reason)
 
    return {
        'statusCode': 200,
        'body': json.dumps('Event processed successfully')
    }
