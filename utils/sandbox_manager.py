"""
Sandbox environment manager for code execution.
Centralizes creation and management of Vertex AI Agent Engine sandboxes.
"""

import vertexai

# Global sandbox resources
_agent_engine = None
_agent_engine_name = None
_sandbox_name = None

def initialize_sandbox(project_id: str, location: str):
    """
    Initialize the sandbox environment for code execution.
    
    Args:
        project_id: Google Cloud project ID
        location: Google Cloud region
        
    Returns:
        tuple: (agent_engine_name, sandbox_name)
    """
    global _agent_engine, _agent_engine_name, _sandbox_name
    
    try:
        # Create Vertex AI client
        client = vertexai.Client(project=project_id, location=location)
        
        # Create Agent Engine instance
        _agent_engine = client.agent_engines.create()
        _agent_engine_name = _agent_engine.api_resource.name
        print(f"Agent Engine created: {_agent_engine_name}")
        
        # Create custom sandbox environment with Python code execution
        try:
            sandbox = client.agent_engines.sandboxes.create(
                parent=_agent_engine_name,
                sandbox_spec={
                    "code_execution_environment": {
                        "code_language": "LANGUAGE_PYTHON",
                        "machine_config": "MACHINE_CONFIG_VCPU4_RAM4GIB"  # 4 vCPU and 4GB RAM
                    }
                }
            )
            _sandbox_name = sandbox.name
            print(f"Custom sandbox environment created: {_sandbox_name}")
        except Exception as sandbox_error:
            print(f"Sandbox creation error details: {sandbox_error}")
            #use a name parameter as alternative?
            sandbox = client.agent_engines.sandboxes.create(
                name=_agent_engine_name,
                spec={
                    "code_execution_environment": {
                        "code_language": "LANGUAGE_PYTHON",
                        "machine_config": "MACHINE_CONFIG_VCPU4_RAM4GIB"
                    }
                }
            )
            _sandbox_name = sandbox.name
            print(f"Custom sandbox environment created (alternative): {_sandbox_name}")
        
        return _agent_engine_name, _sandbox_name
        
    except Exception as e:
        print(f"Error creating Agent Engine or sandbox: {e}")
        import traceback
        traceback.print_exc()
        raise


def get_sandbox_resources():
    """
    Get the current sandbox resources.
    
    Returns:
        tuple: (agent_engine_name, sandbox_name)
        
    Raises:
        RuntimeError: If sandbox has not been initialized
    """
    if _sandbox_name is None or _agent_engine_name is None:
        raise RuntimeError("Sandbox environment not initialized. Call initialize_sandbox() first.")
    
    return _agent_engine_name, _sandbox_name


def cleanup_sandbox():
    """
    Clean up and delete the sandbox environment and Agent Engine instance.
    """
    global _agent_engine, _agent_engine_name, _sandbox_name
    
    try:
        client = vertexai.Client(project='uk-dta-gsmanalytics-poc', location='europe-west1')
        
        if _sandbox_name:
            client.agent_engines.sandboxes.delete(name=_sandbox_name)
            print(f"Sandbox deleted: {_sandbox_name}")
        
        if _agent_engine:
            _agent_engine.delete()
            print(f"Agent Engine deleted: {_agent_engine_name}")
            
        _agent_engine = None
        _agent_engine_name = None
        _sandbox_name = None
        
    except Exception as e:
        print(f"Error cleaning up sandbox: {e}")
