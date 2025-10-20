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

load_dotenv(override=True)

warnings.filterwarnings("ignore")

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

sql_writer_agent = LlmAgent(
    name='sql_writer_agent',
    model=SQL_WRITER_AGENT_MODEL,
    description="Analyzes data schema and executes SQL queries via BigQuery.",
    global_instruction=GLOBAL_INSTRUCTION,
    # static_instruction=SQL_WRITER_AGENT_DYNAMIC_INSTRUCTION,
    instruction = ("""You are an expert Data Analyst with access to BigQuery.
    **Your Task:**
    Analyze the provided schema and user question, then follow these steps:

    1. **Analyze the Request**: Understand what analysis, metrics, or insights are needed to answer the question.

    2. **Validate Information**: If the user's question hasn't provided sufficient information to solve user's query given available tools and other information, respond with a clear text message asking for clarification or stating what's missing.

    3. **Plan Your SQL Query**: Determine the appropriate SQL query to answer the question 

    4. **Execute SQL Query**: If information is validated from bullet 2. , EXECUTE SQL QUERY given available tools
                   
    5. **Return Structured Output**: Based on the query results, output ONLY a string EITHER 
        5.1 briefly explaining the reasoning behind query construction (what tables were used, which fields, JOINs etc.)
        5.2 explanation from bullet 2.
                   
    GCP Projects available: {projects}
    GCP Datasets available: {datasets}
    GCP Tables available: {tables}                                      
    """),
    tools=[bigquery_toolset],        
    generate_content_config=types.GenerateContentConfig(
        temperature=0, #for more determinism
        max_output_tokens=5000,
        top_p=0.5 #for more determinism
    ),  
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    include_contents='default',
    output_key='latest_sql_output_reasoning'
)