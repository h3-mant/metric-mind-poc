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
from callbacks import sql_refiner_agent_callback, python_refiner_agent_callback
from dotenv import load_dotenv

load_dotenv(override=True)


warnings.filterwarnings("ignore")

# Python Critic Agent
python_critic_agent = LlmAgent(
    name="python_critic_agent",
    model=PYTHON_CRITIC_AGENT_MODEL,
    include_contents='none',
    instruction=f"""You are a Python Critic AI reviewing provided Python code
    to answer user's query via visualization.

    **Latest Python code**
    ```
    {{latest_python_code_output}}
    ```

    **Reasoning behind Latest Python code**
    ```
    {{latest_python_code_output_reasoning}}
    ```

    **Execution Result of Latest Python Code**
    ```
    {{latest_python_code_execution_outcome}}
    ```    

    **Task:**
    Review the Python code to check for:
    1. Logical correctness — Does executing the code generate a visual that answer the user's question?
    2. Syntax validity — Are there any syntax or function issues?

    IF you identify any issues, suggest concise, constructive improvements or corrections.

    Output *only* the critique text.
    ELSE IF everything is OK,
    Respond *exactly* with the phrase "{OUTCOME_OK_PHRASE}" and nothing else. 
    Do not add explanations. Output only the critique OR the exact completion phrase.    
""",
    description="Python Critic AI reviewing Python code",
    output_key='latest_python_code_criticism'
)