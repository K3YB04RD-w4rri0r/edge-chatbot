import os
from openai import AzureOpenAI
from shared_variables import settings

# For Azure OpenAI
client = AzureOpenAI(
    api_key=settings.azure_openai_key,  # Azure key from Terraform
    api_version=settings.api_version,      # Azure API version
    azure_endpoint=settings.azure_endpoint  # Your Azure endpoint
)

# The correct way to call Azure OpenAI
response = client.chat.completions.create(
    model="gpt-4.1",  # Your Azure deployment name
    messages=[
        {
            "role": "system", 
            "content": "You are a coding assistant that talks like a pirate."
        },
        {
            "role": "user",
            "content": "How do I check if a Python object is an instance of a class?"
        }
    ],
    temperature=0.7,
    max_tokens=500
)


print(response.choices[0].message.content)

