from constants import *
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from utils.agent_utils import call_agent_async
from agents.python_writer_agent import python_writer_agent
from agents.python_critic_agent import python_critic_agent
from agents.python_refiner_agent import python_refiner_agent
from utils.logger import get_logger

logger = get_logger(__name__)

async def python_agent_sequence(
    app_name: str,
    user_id: str,
    session_service: InMemorySessionService,
    artifact_service: InMemoryArtifactService,
    session_id: str,
    user_query: str) -> None:
    
    #update session
    session = await session_service.get_session(
        app_name=app_name,user_id=user_id,session_id=session_id
    )

    python_writer_agent_runner = Runner(
          agent=python_writer_agent,
          app_name=app_name,
          session_service=session_service,
          artifact_service=artifact_service
      )
    
    python_writer_response = await call_agent_async(
       runner=python_writer_agent_runner, 
       app_name=app_name, 
       user_id=user_id, 
       session_id=session_id, 
       user_query=user_query, 
       session_service=session_service,
       artifact_service=artifact_service
       )

    logger.info(python_writer_response)

    python_critic_agent_runner = Runner(
          agent=python_critic_agent,
          app_name=app_name,
          session_service=session_service,
          artifact_service=artifact_service
      )
  
    python_refiner_agent_runner = Runner(
            agent=python_refiner_agent,
            app_name=app_name,
            session_service=session_service,
            artifact_service = artifact_service
        )
  
    retries = 0
    while retries < MAX_RETRIES:
      
      session = await session_service.get_session(
        app_name=app_name,user_id=user_id,session_id=session_id
      )

      #use session.state only for READS not WRITES
      if session.state.get('latest_python_code_criticism') == OUTCOME_OK_PHRASE and \
         session.state.get('latest_python_code_execution_outcome') == OUTCOME_OK_PHRASE:
        break 
      
      #Call Python Critic Agent
      python_critic_response = await call_agent_async(
        runner=python_critic_agent_runner, 
        app_name=app_name, 
        user_id=user_id, 
        session_id=session_id, 
        user_query=user_query, 
        session_service=session_service,
        artifact_service=artifact_service
      )
      
      logger.info(python_critic_response)

      #Call Python Refiner Agent
      python_refiner_response = await call_agent_async(
        runner=python_refiner_agent_runner, 
        app_name=app_name, 
        user_id=user_id, 
        session_id=session_id, 
        user_query=user_query, 
        session_service=session_service,
        artifact_service=artifact_service
      )

      logger.info(python_refiner_response)

      retries += 1