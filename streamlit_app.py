import streamlit as st
import asyncio
import pandas as pd
import matplotlib.pyplot as plt
import base64
import io
from main import main_async

# Define the Streamlit app
def main():
    st.title("Metric Mind")

    # Input for user query
    user_query = st.text_input("Enter your query:", "Is there an association between payment method and time to delivery since shipping?")

    # Button to trigger the process
    if st.button("Run Query"):
        with st.spinner("Processing..."):
            # Run the async function and get the results
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_query(user_query))
            finally:
                loop.close()

# Async function to handle the query
async def run_query(user_query):
    try:
        session = await main_async(user_query=user_query)

        # Layout the app
        col1, col2 = st.columns(2)

        # Left column: SQL Query and Table
        with col1:
            st.subheader("SQL Query")
            st.text_area("SQL Query Output", session.state.get('latest_sql_output'), height=200, key="sql_query")

            st.subheader("SQL Results")
            sql_results = session.state.get('latest_sql_response')
            if sql_results:
                df = pd.DataFrame(sql_results)
                st.dataframe(df)

        # Right column: Python Code and Image
        with col2:
            st.subheader("Python Code")
            st.text_area("Generated Python Code", session.state.get('latest_python_code_output'), height=200, key="python_code")

            st.subheader("Generated Visualization")
            image_path = "images/img.png"
            try:
                with open(image_path, "rb") as img_file:
                    st.image(img_file.read(), caption="Visualization", width='stretch')
            except FileNotFoundError:
                st.error("Image not found at images/img.png")

        # Token Count
        st.write(f"Total Token Count: {session.state.get('app:total_token_count')}")

    except Exception as e:
        st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()