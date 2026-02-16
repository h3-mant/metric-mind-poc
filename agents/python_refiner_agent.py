from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.planners import BuiltInPlanner
from instructions.python_refiner_agent_instructions import *
from google.genai import types
from dotenv import load_dotenv
from constants import *
from callbacks import get_sequence_outcome, store_image_artifact, python_refiner_agent_callback
from utils.sandbox_manager import get_sandbox_resources
import warnings

load_dotenv(override=True)

warnings.filterwarnings("ignore")

# Get the sandbox resources created by python_writer_agent
# agent_engine_name, sandbox_name = get_sandbox_resources()

#Python Refiner Agent
python_refiner_agent = LlmAgent(
    name="python_refiner_agent",
    model=PYTHON_REFINER_AGENT_MODEL,
    # Relies solely on state via placeholders
    include_contents='none',
    global_instruction=GLOBAL_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=PYTHON_REFINER_AGENT_STATIC_INSTRUCTION)]),
    instruction=PYTHON_REFINER_AGENT_DYNAMIC_INSTRUCTION,
    description="refines Python code to align with critique/suggestions and generates visuals.",
    code_executor = BuiltInCodeExecutor(),
    # code_executor=AgentEngineSandboxCodeExecutor(
    #     sandbox_resource_name=sandbox_name,
    #     agent_engine_resource_name=agent_engine_name
    # ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        # max_output_tokens=5000,
        top_p=0.5,
        seed=1,
        candidate_count=None
    ),
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    before_agent_callback=python_refiner_agent_callback,
    after_tool_callback=store_image_artifact,
    after_agent_callback=get_sequence_outcome,
    output_key='latest_python_code_output_reasoning'
)