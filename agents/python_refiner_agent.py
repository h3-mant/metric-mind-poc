from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.planners import BuiltInPlanner
from instructions.python_refiner_agent_instructions import *
from google.genai import types
from dotenv import load_dotenv
from constants import *
from google.genai import types
import warnings
from callbacks import python_refiner_agent_callback
from dotenv import load_dotenv

load_dotenv(override=True)

warnings.filterwarnings("ignore")

#Python Refiner Agent
python_refiner_agent = LlmAgent(
    name="python_refiner_agent",
    model=PYTHON_REFINER_AGENT_MODEL,
    # Relies solely on state via placeholders
    include_contents='none',
    global_instruction=GLOBAL_INSTRUCTION,
   #  static_instruction=PYTHON_REFINER_AGENT_STATIC_INSTRUCTION,
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

    4. After executing code, your final response must be 
       a string explaining code changes and implementation

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
        max_output_tokens=5000,
        top_p=0.5,
    ),
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    before_agent_callback=python_refiner_agent_callback,
    output_key='latest_python_code_output_reasoning'
)