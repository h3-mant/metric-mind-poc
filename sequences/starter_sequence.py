from constants import *
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from utils.agent_utils import call_agent_async
from agents.starter_agent import starter_agent
from utils.logger import get_logger
from google.adk.sessions import Session 
logger = get_logger(__name__)

async def starter_agent_sequence(
    app_name: str,
    user_id: str,
    session_service: InMemorySessionService,
    artifact_service: InMemoryArtifactService,
    session_id: str,
    user_query: str,
    starter_agent_runner:Runner,
    current_session: Session
    ) -> None:
  """Sequence to run Starter Agent"""


  #Call Starter Agent
  starter_agent_response = await call_agent_async(
    runner=starter_agent_runner, 
    app_name=app_name, 
    user_id=user_id, 
    session_service=session_service, 
    artifact_service=artifact_service,
    session_id=session_id, 
    user_query=user_query,
    current_session=current_session
    )
  
  logger.info(starter_agent_response)
