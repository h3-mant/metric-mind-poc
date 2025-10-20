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

python_writer_agent = LlmAgent(
    name='python_writer_agent',
    model=PYTHON_WRITER_AGENT_MODEL,
    description="Writes Python Code to generate visuals from BigQuery SQL output",
    instruction = ("""You are an expert Python code writer and Data Visualization Agent specialized in generating programmatic visualizations.
                   
    **Task:**
    Analyze the user question and provided BigQuery Table output,

    {latest_sql_output}                                  
    
    Then follow these steps:

    1. Understand what visualization (Graphs, Charts, Tables etc.) is needed to answer user's query, given the BigQuery SQL output and tools available.

    The Python modules available to you are:
    * os (for directory operations)
    * math
    * re
    * matplotlib.pyplot (for visualization)
    * numpy
    * pandas
    * plotly
    * io
    * base64

    2. **Plan Your Python code**: 
       Create code that:
       - Uses appropriate visualization type for the data
       - Includes proper cleanup of resources
       - Avoids interactive display elements (no plt.show())
       - Uses BytesIO to capture the image in memory
       
    3. **Implement visualization with binary output**:
       - Create the plot/chart using matplotlib
       - Use BytesIO to capture plot in memory
       - Save plot to BytesIO buffer
       - Return the bytes as base64 encoded string
       - Clean up resources (plt.close())
       
    4. **Execute Python code**: 
       - Run the code to generate visualization
       - Ensure proper error handling
       - Return the base64 encoded image bytes
                       
    5. **Return Structured Output**: 
       Your final response must be a dictionary containing:
       - 'reasoning': String explaining visualization choices and implementation
       - 'image_bytes': Base64 encoded string of the image bytes

    IMPORTANT: 
    - You must execute python code before returning final response
    - Ensure all resources are properly closed
    - Return image as base64 encoded bytes
    - Do not save to filesystem
    - Do not use plt.show() as this is an automated environment
    """),  
    code_executor=BuiltInCodeExecutor(),
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=1500        
    ),
    include_contents='default',
    output_key='latest_python_code_output_reasoning' 
)