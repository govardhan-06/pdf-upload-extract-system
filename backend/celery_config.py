from celery import Celery
from kombu import Queue, Exchange, Connection
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Celery('pdf_processor')

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Construct broker URL with error checking
if not all([REDIS_HOST, REDIS_PORT]):
    raise ValueError("Missing required Redis configuration")

# Configure broker and backend URLs
broker_url = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0'
logger.info(f"Broker URL: {broker_url}")

print(broker_url)

app.conf.broker_url = broker_url
app.conf.result_backend = broker_url

# Define exchanges
pdf_exchange = Exchange('pdf', type='direct')
ocr_exchange = Exchange('ocr', type='direct')

# Setting up the Celery Configuration
app.conf.update(
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    task_default_queue='pdf_processing',
    task_queues=(
        Queue('pdf_processing', exchange=pdf_exchange, routing_key='pdf.process'),
        Queue('ocr_processing', exchange=ocr_exchange, routing_key='ocr.process'),
    ),
    task_routes={
        'perform_ocr': {'queue': 'ocr_processing', 'routing_key': 'ocr.process'},
    },
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    task_serializer='pickle',
    accept_content=['pickle', 'json'],
    result_serializer='pickle',
)