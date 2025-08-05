import google.generativeai as genai
import requests
import json

def hello(prompt, model="gemini-1.5-flash", api_key="AIzaSyCvn4WY_e_OScJIBZid3rrV57SsxwtqekQ", max_tokens=1000, temperature=0.7):
    """
    Calls Google Gemini Flash model and returns the response as a string.
    
    Args:
        prompt (str): The input prompt to send to the model
        model (str): The model name (e.g., "gemini-1.5-flash", "gemini-1.5-pro")
        api_key (str): Your Google AI API key
        max_tokens (int): Maximum tokens in the response
        temperature (float): Randomness of the response (0.0 to 1.0)
    
    Returns:
        str: The model's response text
    """
    try:
        # Configure the API key
        genai.configure(api_key=api_key)
        
        # Create the model
        model_instance = genai.GenerativeModel(model)
        
        # Configure generation parameters
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        
        # Generate response
        response = model_instance.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        return response.text
        
    except Exception as e:
        return f"Error calling Google Gemini API: {str(e)}"