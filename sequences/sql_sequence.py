from constants import *
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from utils.agent_utils import call_agent_async
from utils.logger import get_logger
from google.adk.sessions import Session 
logger = get_logger(__name__)

async def sql_agent_sequence(
    app_name: str,
    user_id: str,
    session_service: InMemorySessionService,
    artifact_service: InMemoryArtifactService,
    session_id: str,
    user_query: str,
    sql_writer_agent_runner: Runner,
    sql_critic_agent_runner: Runner,
    sql_refiner_agent_runner: Runner,
    session: Session
    ) -> None:
  """Sequence to run SQL Writer, Critic and Refiner Agents"""



  #Call SQL Writer Agent
  sql_writer_response = await call_agent_async(
    runner=sql_writer_agent_runner, 
    app_name=app_name, 
    user_id=user_id, 
    session_service=session_service, 
    artifact_service=artifact_service,
    session_id=session_id, 
    user_query=user_query,
    current_session=session
    )
  
  logger.info(sql_writer_response)



  #Retry loop for SQL Critic and Refiner Agents
  retries = 0
  while retries < MAX_RETRIES:
    
    #Result of code_execution tool is either SUCCESS/ERROR/PENDING
    #If code_execution result is SUCCESS and latest_sql_criticism is OUTCOME OK, break the loop
    if session.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE and \
      session.state.get('latest_bq_execution_status').upper() == 'SUCCESS':
       break
    
    #call SQL Critic Agent
    sql_critic_response = await call_agent_async(
      runner=sql_critic_agent_runner,
      app_name=app_name, 
      session_service=session_service,
      artifact_service=artifact_service,
      session_id=session_id, 
      user_id=user_id, 
      user_query=user_query,
      current_session=session
      )
    
    logger.info(sql_critic_response)

    #Call SQL Refiner Agent
    sql_refiner_response = await call_agent_async(
      runner=sql_refiner_agent_runner,
      app_name=app_name, 
      user_id=user_id, 
      session_service=session_service,
      artifact_service=artifact_service,
      session_id=session_id, 
      user_query=user_query,
      current_session=session
      )

    logger.info(sql_refiner_response)

    retries += 1