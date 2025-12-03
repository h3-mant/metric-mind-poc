import os
import logging
from datetime import datetime

LOGS_DIR = 'logs'

os.makedirs(LOGS_DIR,exist_ok=True)

LOGS_FILE = os.path.join(LOGS_DIR,f'log_{datetime.now().strftime("%Y-%m-%d")}.log')

# Configure root logger only once
if not logging.root.handlers:
    logging.basicConfig(
        filename=LOGS_FILE,
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

def get_logger(name):
  logger = logging.getLogger(name)
  logger.setLevel(logging.INFO)
  # Only add handler if it doesn't already exist to avoid duplicate logs
  if not logger.handlers:
    handler = logging.FileHandler(LOGS_FILE)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
  return logger