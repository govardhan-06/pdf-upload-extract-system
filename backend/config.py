import dramatiq
from dramatiq.brokers.redis import RedisBroker
import os
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Redis connection settings
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "695011")

# Configure Redis broker
redis_broker = RedisBroker(
    host="127.0.0.1",
    port=6379,
    password="695011",
    namespace="pdf_processor"
)

# Set the broker as the default broker
dramatiq.set_broker(redis_broker)

# Configure Dramatiq middleware
redis_broker.add_middleware(
    dramatiq.middleware.TimeLimit(time_limit=3600000)  # 1 hour in ms
)