from google.adk.agents import LlmAgent
from google.adk.tools.bigquery import BigQueryCredentialsConfig
from google.adk.tools.bigquery import BigQueryToolset
from google.adk.tools.bigquery.config import BigQueryToolConfig
from google.adk.tools.bigquery.config import WriteMode
from instructions.sql_writer_agent_instructions import SQL_WRITER_AGENT_DYNAMIC_INSTRUCTION, SQL_WRITER_AGENT_STATIC_INSTRUCTION
from google.adk.planners import BuiltInPlanner
import google.auth
from google.genai import types
from constants import *
from google.genai import types
import warnings
from dotenv import load_dotenv
from vertexai import init as vertex_init
from google.cloud.aiplatform import initializer as aiplatform_init
import os

load_dotenv(override=True)
warnings.filterwarnings("ignore")

tool_config = BigQueryToolConfig(write_mode=WriteMode.PROTECTED,
                                 location='EU')

application_default_credentials, _ = google.auth.default()
credentials_config = BigQueryCredentialsConfig(
    credentials=application_default_credentials
)

bigquery_toolset = BigQueryToolset(
    credentials_config=credentials_config, bigquery_tool_config=tool_config,
    tool_filter=['execute_sql'] 
)
    
sql_writer_agent = LlmAgent(
    name='sql_writer_agent',
    model=SQL_WRITER_AGENT_MODEL,
    description="Analyzes data schema and executes SQL queries via BigQuery.",
    global_instruction=GLOBAL_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=SQL_WRITER_AGENT_STATIC_INSTRUCTION)]),
    instruction = SQL_WRITER_AGENT_DYNAMIC_INSTRUCTION,
    tools=[bigquery_toolset],        
    generate_content_config=types.GenerateContentConfig(
        temperature=0, # deterministic for SQL generation
        max_output_tokens=1500, # reduce default output size
        top_p=0.5
    ),  
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    # Do not automatically include the full conversation/tool outputs in every call
    include_contents='none',
    output_key='latest_sql_output_reasoning'
)