from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.genai import types
from dotenv import load_dotenv
from constants import *
from google.genai import types
from google.adk.planners import BuiltInPlanner
from instructions.python_writer_agent_instructions import *
import warnings
from callbacks import store_image_artifact
from dotenv import load_dotenv

load_dotenv(override=True)

warnings.filterwarnings("ignore")

python_writer_agent = LlmAgent(
    name='python_writer_agent',
    model=PYTHON_WRITER_AGENT_MODEL,
    description="Writes Python Code to generate visuals from BigQuery SQL output",
    global_instruction=GLOBAL_INSTRUCTION,
    instruction=PYTHON_WRITER_AGENT_DYNAMIC_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=PYTHON_WRITER_AGENT_STATIC_INSTRUCTION)]),
    code_executor=BuiltInCodeExecutor(
        error_retry_attempts=1, #let agents handle code failure, avoid retries
        stateful=True #retain code execution results
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        top_p=0.5,
        max_output_tokens=5000,
        seed=1
    ),
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    include_contents='default',
    output_key='latest_python_code_output_reasoning',
    after_tool_callback=store_image_artifact
)