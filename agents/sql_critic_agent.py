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
import warnings
from dotenv import load_dotenv

load_dotenv(override=True)

warnings.filterwarnings("ignore")

# SQL Critic Agent
sql_critic_agent = LlmAgent(
    name="sql_critic_agent",
    model=SQL_CRITIC_AGENT_MODEL,
    include_contents='none',
    instruction=f"""You are a SQL Critic AI reviewing provided BigQuery SQL
    to answer user's query.

    Latest SQL Query: {{latest_sql_output}}
    Latest Reasoning behind latest SQL Query: {{latest_sql_output_reasoning}}

    **Task:**
    Review the SQL query to check for:
    1. Logical correctness — Does the SQL actually answer the user's question?
    2. Syntax validity — Are there any BigQuery syntax or function issues?
    3. Table or column mismatches — Are all referenced tables/columns consistent with schema naming?
    4. Aggregation logic — Are GROUP BY, HAVING, and aggregation functions used correctly?
    5. Filtering accuracy — Are WHERE/JOIN conditions appropriate and not excluding needed data?
    6. Performance — Could the query be inefficient due to unnecessary subqueries, joins, or scans?
    7. Edge cases — Does it correctly handle NULLs, empty results, or division by zero?

    IF you identify any issues, suggest concise, constructive improvements or corrections.

    Output *only* the critique text.
    ELSE IF everything is OK,
    Respond *exactly* with the phrase "{OUTCOME_OK_PHRASE}" and nothing else. 
    Do not add explanations. Output only the critique OR the exact completion phrase.

    Use the below schema available for reference.
    GCP Projects available: {{projects}}
    GCP Datasets available: {{datasets}}
    GCP Tables available: {{tables}}
""",
    description="SQL Critic AI reviewing SQL code",
    output_key='latest_sql_criticism'
)