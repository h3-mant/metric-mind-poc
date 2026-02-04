from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from constants import *
from google.genai import types
from google.adk.planners import BuiltInPlanner
from pydantic import BaseModel, Field
from callbacks import store_results_in_context
from google import genai
from utils.helper import json_to_dict
# from agents import cache 
from instructions.starter_agent_instructions import STARTER_AGENT_STATIC_INSTRUCTION, STARTER_AGENT_DYNAMIC_INSTRUCTION


load_dotenv(override=True)

class StarterAgentResponse(BaseModel):
  """Structured response from the starter agent for query classification."""
  greeting: str = Field(
        description="A brief, contextual response to the user's query"
    )
  user_intent: str = Field(
        description="Summary of the user's intent in conversation so far"
    )
  sql_required: bool = Field(
        description="True if the query requires writing and executing SQL queries against BigQuery"
    )
  python_required: bool = Field(
      description="True if the query requires writing and executing Python code for visualizations or data processing"
  )

starter_agent = LlmAgent(
  name='starter_agent',
  model=STARTER_AGENT_MODEL,
  description="Initiater Agent that decides if downstream agents are required or not.",
  global_instruction=GLOBAL_INSTRUCTION,
  static_instruction=types.Content(role='system',parts=[types.Part(text=STARTER_AGENT_STATIC_INSTRUCTION)]),
  instruction=STARTER_AGENT_DYNAMIC_INSTRUCTION,
  generate_content_config=types.GenerateContentConfig(
        temperature=0.5,
        max_output_tokens=500,
        top_p=0.95,
        seed=1,
        candidate_count=None
    ),  
  planner=BuiltInPlanner(
      thinking_config=types.ThinkingConfig(
          include_thoughts=False,
          thinking_budget=-1
          )
    ),
  output_schema=StarterAgentResponse,
  include_contents='default',
  after_agent_callback=store_results_in_context,
  output_key='starter_agent_response',
)
