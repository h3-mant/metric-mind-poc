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

load_dotenv()

warnings.filterwarnings("ignore")

#Python Refiner Agent
python_refiner_agent = LlmAgent(
    name="python_refiner_agent",
    model=PYTHON_REFINER_AGENT_MODEL,
    # Relies solely on state via placeholders
    include_contents='none',
    instruction=f"""You are a Python code refining AI Agent tasked with making changes to existing Python code to answer user's query.

    **Latest Python code:**
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

    **Critique/Suggestions:**
    {{latest_python_code_criticism}}

    **Task:**
    Analyze the 'Critique/Suggestions' and follow these steps:

    1. For visualization code:
       - Use BytesIO to capture plot in memory
       - Return image as base64 encoded bytes
       - Clean up resources (plt.close()) after saving
       - Remove any plt.show() calls
       - Use proper image format (PNG)
       - Handle memory and resource management correctly

    2. Generate NEW PYTHON CODE that:
       - Creates the visualization
       - Uses BytesIO to capture plot in memory
       - Returns base64 encoded image bytes
       - Includes proper error handling
       - Manages memory and resources effectively

    3. EXECUTE PYTHON CODE to generate the visualization.

    4. After executing code, your final response must be a dictionary containing:
       - 'reasoning': String explaining code changes and implementation
       - 'image_bytes': Base64 encoded string of the image bytes

    IMPORTANT:
    - You must execute python code before returning final response
    - Ensure all matplotlib resources are properly closed
    - Return image as base64 encoded bytes
    - Do not save to filesystem
    - Handle memory and resource management safely
    """,
    description="refines Python code to align with critique/suggestions and generates visuals.",
    code_executor=BuiltInCodeExecutor(),
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=1500        
    ),
    before_agent_callback=python_refiner_agent_callback,
    output_key='latest_python_code_output_reasoning'
)