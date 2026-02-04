from google.adk.agents import LlmAgent
from google.adk.planners import BuiltInPlanner
from google.genai import types
from dotenv import load_dotenv
from constants import *
from instructions.python_critic_agent_instructions import *
from google.genai import types
import warnings
from callbacks import get_sequence_outcome
from dotenv import load_dotenv

load_dotenv(override=True)


warnings.filterwarnings("ignore")

# Python Critic Agent
python_critic_agent = LlmAgent(
    name="python_critic_agent",
    model=PYTHON_CRITIC_AGENT_MODEL,
    include_contents='none',
    global_instruction=GLOBAL_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=PYTHON_CRITIC_AGENT_STATIC_INSTRUCTION)]),
    instruction=PYTHON_CRITIC_AGENT_DYNAMIC_INSTRUCTION,
    description="Python Critic AI reviewing Python code",
    output_key='latest_python_code_criticism',
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        top_p=0.5,
        max_output_tokens=5000,
        seed=1,
        candidate_count=None
    ),
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    after_agent_callback=get_sequence_outcome
)