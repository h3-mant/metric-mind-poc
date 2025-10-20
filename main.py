import uuid
from google.adk.sessions import InMemorySessionService
from utils.helper import json_to_dict
from constants import *
from utils.logger import get_logger
from utils.helper import save_img
from sequences.sql_sequence import sql_agent_sequence
from sequences.python_sequence import python_agent_sequence
from sequences.starter_sequence import starter_agent_sequence
import asyncio

logger = get_logger(__name__)

async def main_async(user_query=None, session_id=None):
  if session_id is None:
    session_id = str(uuid.uuid4())
  if user_query is None:
    user_query = """Is there an association between payment method and time to delivery since shipping?"""
  try:
    #Define APP NAME AND USER NAME
    app_name = APP_NAME
    user_id = USER_ID

    #Define Session Service
    session_service = InMemorySessionService()

    #Define Artifact Service
    # artifact_service = InMemoryArtifactService()

    #Define data schema to be passed as initial_state
    initial_state = json_to_dict(DATA_SCHEMA_PATH)
    initial_state_formatted = {
      'projects': initial_state.get('project_id'),
      'datasets': initial_state.get('dataset_id'),
      'tables': initial_state.get('tables')
    }

    #Create Session
    session = await session_service.create_session(
              app_name=app_name,
              user_id=user_id,
              session_id=session_id,
              state=initial_state_formatted,
          )
    
    logger.info(f"Created new session: {session.id}")

    #Call Starter Agent Sequence 
    await starter_agent_sequence(app_name,user_id,session_service,session_id,user_query)

    #decide if SQL sequence is required
    if session.state.get('sql_required'):       
      #Call SQL Sequence
      await sql_agent_sequence(app_name,user_id,session_service,session_id,user_query)

      #update session
      session = await session_service.get_session(
        app_name=app_name,user_id=user_id,session_id=session_id
      )

    if session.state.get('python_required'):
      #if SQL sequence was successful, run Python sequence  
      if session.state.get('latest_sql_criticism') == OUTCOME_OK_PHRASE and \
        session.state.get('latest_bq_execution_status').upper() == 'SUCCESS':     

          #declare SQL sequence outcome successful
          session.state['sql_sequence_outcome'] = 'SUCCESS'

          #Call Python Sequence
          await python_agent_sequence(app_name,user_id,session_service,session_id,user_query)

          #update session
          session = await session_service.get_session(
            app_name=app_name,user_id=user_id,session_id=session_id
          )

          #save image artifact from Python sequence
          img_bytes = session.state.get('latest_img_bytes')
          result = save_img(img_bytes)

          print('Python Sequence completed successfully')
          session.state['python_sequence_outcome'] = result

          # print('----- Final Outputs -----')
          # print(session.state.get('latest_sql_output'),end='\n\n')
          # print(session.state.get('latest_sql_response'),end='\n\n')
          # print(session.state.get('latest_python_code_output'),end='\n\n')
          # print(session.state.get('app:total_token_count'),end='\n\n')

      else:
        print('SQL Sequence failed')
        session.state['sql_sequence_outcome'] = 'FAILURE'

      return session
    
  except Exception as e:
    logger.error(f"Error in main_async: {e}")

if __name__ == "__main__":
    asyncio.run(main_async())