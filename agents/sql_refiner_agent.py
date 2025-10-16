from google.adk.agents import LlmAgent
from google.adk.tools.bigquery import BigQueryCredentialsConfig
from google.adk.tools.bigquery import BigQueryToolset
from google.adk.tools.bigquery.config import BigQueryToolConfig
from google.adk.tools.bigquery.config import WriteMode
from google.adk.code_executors import BuiltInCodeExecutor
import google.auth
from google.genai import types
from dotenv import load_dotenv
from constants import *
from google.genai import types
from utils.agent_utils import call_agent_async
import warnings
from dotenv import load_dotenv
from callbacks import sql_refiner_agent_callback, python_refiner_agent_callback
import warnings

warnings.filterwarnings("ignore")

load_dotenv()

# Define a tool configuration to block any write operations
tool_config = BigQueryToolConfig(write_mode=WriteMode.BLOCKED)

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
    instruction=f"""You are a SQL refining AI Agent tasked with making changes to existing BigQuery SQL to answer user's query.

    **Current SQL Query:**
    ```
    {{latest_sql_output}}
    ```
    **Critique/Suggestions:**
    {{latest_sql_criticism}}

    **Task:**
    Analyze the 'Critique/Suggestions'.
    Carefully apply the suggestions to generate NEW SQL, then EXECUTE SQL given tools available. 

    **Return Structured Output**: Finally, based on the query results, output ONLY a string
      briefly explaining the changes made considering the critique/suggestions.
""",
    description="refines SQL query to align with critique/suggestions",
    before_agent_callback = sql_refiner_agent_callback,
    tools=[bigquery_toolset],        
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=1500        
    ),
    output_key='latest_sql_output_reasoning' # Overwrites state['latest_sql_output_reasoning'] with the refined version
)
