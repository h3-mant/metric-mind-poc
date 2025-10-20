from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from constants import *
from google.genai import types
from pydantic import BaseModel, Field
from callbacks import store_results_in_context

load_dotenv(override=True)

class StarterAgentResponse(BaseModel):
  """Structured response from the starter agent for query classification."""
  greeting: str = Field(
        description="A brief, contextual response to the user's query"
    )
  sql_required: bool = Field(
        description="True if the query requires writing and executing SQL queries against BigQuery"
    )
  python_required: bool = Field(
      description="True if the query requires writing and executing Python code for visualizations or data processing"
  )

starter_agent = LlmAgent(
  name='starter_agent',
  model=STARTER_AGENT_MODEL,
  description="Initiater Agent that decides if downstream agents are required or not.",
  instruction="""You are a data analysis orchestrator agent. Your role is to analyze user queries about data in BigQuery and determine the appropriate downstream processing requirements.
  
  You have access to the data schema:
  - GCP Projects available: {projects}
  - GCP Datasets available: {datasets}
  - GCP Tables available: {tables}

  ## Your Responsibilities

  1. **Understand the Query**: Carefully analyze what the user is asking for
  2. **Classify Requirements**: Determine if the query needs:
    - SQL execution (data retrieval, aggregation, filtering, joins)
    - Both SQL and Python (data retrieval followed by visualization)
    - Neither (simple informational responses)
  
  3.**Provide Structured Output**: Return your analysis in the JSON format specified:
    `greeting` - Simple exchange based on user query
    `sql_required` - whether or not writing and executing SQL is required to solve user query. (True/False)
    `python_required` - whether or not writing and executing Python is required to solve user query. (True/False)

  NOTE: IF VISUALIZATION IS REQUIRED, SQL IS ALWAYS REQUIRED!
""",
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=1500,
    ),  
    output_schema=StarterAgentResponse,
    include_contents='none',
    after_agent_callback=store_results_in_context,
    output_key='starter_agent_response'
)

