from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.genai import types
from google.adk.planners import BuiltInPlanner
from dotenv import load_dotenv
from constants import *
from instructions.python_writer_agent_instructions import *
import warnings
from callbacks import store_image_artifact
from utils.sandbox_manager import initialize_sandbox, get_sandbox_resources

load_dotenv(override=True)

warnings.filterwarnings("ignore")

#initialize custom sandbox environment for code execution
# agent_engine_name, sandbox_name = initialize_sandbox(
#     project_id='uk-dta-gsmanalytics-poc',
#     location='europe-west1'
# )

python_writer_agent = LlmAgent(
    name='python_writer_agent',
    model=PYTHON_WRITER_AGENT_MODEL,
    description="Writes Python Code to generate visuals from BigQuery SQL output",
    global_instruction=GLOBAL_INSTRUCTION,
    instruction=PYTHON_WRITER_AGENT_DYNAMIC_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=PYTHON_WRITER_AGENT_STATIC_INSTRUCTION)]),
    code_executor = BuiltInCodeExecutor(),
    # code_executor=AgentEngineSandboxCodeExecutor(
    #     sandbox_resource_name=sandbox_name,
    #     agent_engine_resource_name=agent_engine_name
    # ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        top_p=0.5,
        # max_output_tokens=5000,
        seed=1, #reproduce answers for identical question
        candidate_count=None
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