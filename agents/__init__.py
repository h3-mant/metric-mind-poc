from dotenv import load_dotenv
from constants import DATA_SCHEMA_PATH
from utils.helper import json_to_dict
from google.genai import types

load_dotenv(override=True)  # take environment variables from .env file

# # Create data schema to be explicitly cached with a 10 minute TTL
# cache_content = json_to_dict(DATA_SCHEMA_PATH)

# #attempt at explicit caching
# cache = types.CreateCachedContentConfig(
#   ttl="10m",
#   display_name='data_schema_cache',
#   contents=cache_content,
# )