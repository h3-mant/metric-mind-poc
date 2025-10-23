from google.adk.agents import LlmAgent
from google.adk.planners import BuiltInPlanner
from google.genai import types
from dotenv import load_dotenv
from instructions.sql_critic_agent_instructions import *
from constants import *
from google.genai import types
from callbacks import get_sequence_outcome
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
    global_instruction=GLOBAL_INSTRUCTION,
    static_instruction=types.Content(role='system',parts=[types.Part(text=SQL_CRITIC_AGENT_STATIC_INSTRUCTION)]),
    instruction=SQL_CRITIC_AGENT_DYNAMIC_INSTRUCTION,
    description="SQL Critic AI reviewing SQL code",
    output_key='latest_sql_criticism',
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
        top_p=0.5,
        max_output_tokens=5000,
    ),
    planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
    after_agent_callback=get_sequence_outcome
)
