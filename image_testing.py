"""
Goal of this file is to test out alternative image generation options 
to reduce latency and token cost 
"""

#1

# from google import genai

# # TODO(developer): Update below line
# # API_KEY = "AIzaSyAQzfSmKEY-678Igt-mRj1stii2WblPkmQ"

# client = genai.Client(vertexai=True, 
#                       project="uk-dta-gsmanalytics-poc",
#                       location="europe-west2")

# response = client.models.generate_content(
#     model="gemini-2.5-flash-image",
#     contents="Explain bubble sort to me.",
# )

# print(response.text)
# # Example response:
# Bubble Sort is a simple sorting algorithm that repeatedly steps through the list


#2

from google import genai
from google.genai.types import GenerateContentConfig
import base64

client = genai.Client(
    vertexai=True,
    project="uk-dta-gsmanalytics-poc",
    location="europe-west2"
)

response = client.models.generate_content(
    model="gemini-2.5-pro",
    contents="Create a detailed technical diagram explaining bubble sort",
    config=GenerateContentConfig(
        response_modalities=["IMAGE"]
    )
)

image_part = response.candidates[0].content.parts[0]
image_bytes = base64.b64decode(image_part.inline_data.data)

with open("bubble_sort_gemini3.png", "wb") as f:
    f.write(image_bytes)

print("Image saved as bubble_sort_gemini.png")

# raise ClientError(status_code, response_json, response)
# google.genai.errors.ClientError: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'Publisher Model `projects/uk-dta-gsmanalytics-poc/locations/europe-west2/publishers/google/models/gemini-3-pro-image-preview` not found.', 'status': 'NOT_FOUND'}}



# from google import genai
# from google.genai.types import GenerateContentConfig
# import base64
# import hashlib

# client = genai.Client(
#     vertexai=True,
#     project="uk-dta-gsmanalytics-poc",
#     location="europe-west2"
# )


#Try Imagen

# response = client.models.generate_images(
#     model="imagen-4.0-ultra-generate-001",
#     prompt="Simple flat illustration explaining bubble sort algorithm",
# )

# image_bytes = base64.b64decode(
#     response.generated_images[0].image.image_bytes
# )

# with open("bubble_sort_imagen.png", "wb") as f:
#     f.write(image_bytes)

# google.genai.errors.ClientError: 400 FAILED_PRECONDITION. {'error': {'code': 400, 'message': 'Organization Policy constraint constraints/vertexai.allowedModels violated for `projects/368826218035` attempting to use a disallowed Gen AI model imagen-3.0-generate-001. Please contact your organization administrator to fix this violation by adding `publishers/google/models/imagen-3.0-generate-001:predict` to the allowed values. For more info, see https://cloud.google.com/vertex-ai/generative-ai/docs/control-model-access.', 'status': 'FAILED_PRECONDITION'}}