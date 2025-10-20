# models.py
from pydantic import BaseModel, Field

class StarterAgentResponse(BaseModel):
    """Structured response from the starter agent for query classification."""
    
    greeting: str = Field(
        description="A brief, contextual response to the user's query"
    )
    sql_required: bool = Field(
        description="True if the query requires writing and executing SQL queries against BigQuery"
    )
    python_required: bool = Field(
        description="True if the query requires writing and executing Python code for visualizations or data processing"
    )