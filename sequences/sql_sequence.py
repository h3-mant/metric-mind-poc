from constants import *
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from utils.agent_utils import call_agent_async
from agents.sql_writer_agent import sql_writer_agent
from agents.sql_critic_agent import sql_critic_agent
from agents.sql_refiner_agent import sql_refiner_agent
from utils.logger import get_logger

logger = get_logger(__name__)

async def sql_agent_sequence(
    app_name: str,
    user_id: str,
    session_service: InMemorySessionService,
    session_id: str,
    user_query: str) -> None:
  """Sequence to run SQL Writer, Critic and Refiner Agents"""

  #Create Runner for SQL Writer Agent
  sql_writer_agent_runner = Runner(
        agent=sql_writer_agent,
        app_name=app_name,
        session_service=session_service,
        # artifact_service=artifact_service
    )

  #Call SQL Writer Agent
  sql_writer_response = await call_agent_async(
    runner=sql_writer_agent_runner, 
    app_name=app_name, 
    user_id=user_id, 
    session_service=session_service, 
    session_id=session_id, 
    user_query=user_query
    )
  
  logger.info(sql_writer_response)

  #Create Runners for SQL Critic and Refiner Agents
  sql_critic_agent_runner = Runner(
          agent=sql_critic_agent,
          app_name=APP_NAME,
          session_service=session_service,
          # artifact_service=artifact_service
      )
  sql_refiner_agent_runner = Runner(
          agent=sql_refiner_agent,
          app_name=APP_NAME,
          session_service=session_service,
          # artifact_service=artifact_service
      )

  #Retry loop for SQL Critic and Refiner Agents
  retries = 0
  while retries < MAX_RETRIES:
    
    #update session
    session = await session_service.get_session(
       app_name=APP_NAME,user_id=USER_ID,session_id=session_id
    )

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
      session_id=session_id, 
      user_id=user_id, 
      user_query=user_query
      )
    
    logger.info(sql_critic_response)

    #Call SQL Refiner Agent
    sql_refiner_response = await call_agent_async(
      runner=sql_refiner_agent_runner,
      app_name=app_name, 
      user_id=user_id, 
      session_service=session_service,
      session_id=session_id, 
      user_query=user_query, 
      )

    logger.info(sql_refiner_response)

    retries += 1