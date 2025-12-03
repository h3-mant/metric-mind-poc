from google.adk.agents import LlmAgent
from google.adk.tools.bigquery import BigQueryCredentialsConfig
from google.adk.tools.bigquery import BigQueryToolset
from google.adk.tools.bigquery.config import BigQueryToolConfig
from google.adk.tools.bigquery.config import WriteMode
from google.adk.planners import BuiltInPlanner
import google.auth
from google.genai import types
from dotenv import load_dotenv
from instructions.sql_refiner_agent_instructions import *
from constants import *
from google.genai import types
import warnings
from dotenv import load_dotenv
from callbacks import sql_refiner_agent_callback, get_sequence_outcome
import warnings

warnings.filterwarnings("ignore")

load_dotenv(override=True)

# Define a tool configuration to BLOCK writing into permanent tables, but allow
#creating temp tables 
tool_config = BigQueryToolConfig(write_mode=WriteMode.PROTECTED)

# Define a credentials config - in this example we are using application default
# credentials
# https://cloud.google.com/docs/authentication/provide-credentials-adc
application_default_credentials, _ = google.auth.default()
credentials_config = BigQueryCredentialsConfig(
    credentials=application_default_credentials
)

# Instantiate a BigQuery toolset
bigquery_toolset = BigQueryToolset(
    credentials_config=credentials_config, bigquery_tool_config=tool_config,
    #ONLY ALLOW SQL EXECUTION, SCHEMA TO BE EXTRACTED FROM STATE
    tool_filter=['execute_sql'] 
)
    
#root agent definition
#PRICING URI -- https://ai.google.dev/gemini-api/docs/models 

#SQL Refiner Agent
sql_refiner_agent = LlmAgent(
    name="sql_refiner_agent",
    model=SQL_REFINER_AGENT_MODEL,
    # Relies solely on state via placeholders
    include_contents='none',
    global_instruction=GLOBAL_INSTRUCTION,
    instruction=SQL_REFINER_AGENT_DYNAMIC_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=SQL_REFINER_AGENT_STATIC_INSTRUCTION)]),
    description="refines SQL query to align with critique/suggestions",
    before_agent_callback = sql_refiner_agent_callback,
    tools=[bigquery_toolset],        
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        top_p=0.5,
        # max_output_tokens=5000,  
    ),
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    after_agent_callback=get_sequence_outcome,
    output_key='latest_sql_output_reasoning' # Overwrites state['latest_sql_output_reasoning'] with the refined version
)
