import os
import logging
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from openai import AsyncOpenAI
import google.generativeai as genai
import tiktoken
import tempfile
from pathlib import Path

from backend.models.conversations_model import ModelChoice, ModelInstructions, Conversation
from backend.models.messages_model import Message, MessageRole
from backend.models.attachments_model import AttachmentType

from shared_variables import settings
logger = logging.getLogger(__name__)

# AI client initialization
openai_client = AsyncOpenAI(api_key=settings.openai_key)
genai.configure(api_key=settings.google_key)

# Token encoder for OpenAI models
encoding = tiktoken.encoding_for_model("gpt-4")


class FileUploadManager:
    """Manages file uploads for both OpenAI and Gemini"""
    
    def __init__(self):
        self.openai_files = {}  # Cache OpenAI file IDs
        self.gemini_files = {}  # Cache Gemini file objects
    
    async def upload_to_openai(self, file_content: bytes, filename: str) -> str:
        """Upload file to OpenAI and return file ID"""
        try:
            import io
            file_object = io.BytesIO(file_content)
            file_object.name = filename
            
            # Upload for assistants (supports file search)
            file_response = await openai_client.files.create(
                file=file_object,
                purpose="assistants"
            )
            
            logger.info(f"Uploaded {filename} to OpenAI: {file_response.id}")
            return file_response.id
            
        except Exception as e:
            logger.error(f"Failed to upload to OpenAI: {e}")
            raise
    
    def upload_to_gemini(self, file_content: bytes, filename: str) -> Any:
        """Upload file to Gemini and return file object"""
        try:
            # Gemini requires a file path, so create temp file
            suffix = Path(filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            
            # Upload to Gemini
            gemini_file = genai.upload_file(
                path=tmp_path,
                display_name=filename
            )
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            logger.info(f"Uploaded {filename} to Gemini: {gemini_file.uri}")
            return gemini_file
            
        except Exception as e:
            logger.error(f"Failed to upload to Gemini: {e}")
            raise
    
    async def cleanup_openai_files(self, file_ids: List[str]):
        """Delete OpenAI files after use"""
        for file_id in file_ids:
            try:
                await openai_client.files.delete(file_id)
                logger.info(f"Deleted OpenAI file: {file_id}")
            except Exception as e:
                logger.error(f"Failed to delete file {file_id}: {e}")


# Global file manager
file_manager = FileUploadManager()


async def get_ai_response(
    conversation: Conversation,
    messages: List[Message],
    new_message: str,
    active_attachments: List[Dict[str, Any]],
    model_choice: str,
    model_instructions: str
) -> str:
    """
    Generate AI response with direct file upload support.
    Supports both OpenAI and Gemini models.
    """
    try:
        if model_choice in [ModelChoice.GPT_4_1_NANO.value, ModelChoice.GPT_4_1.value]:
            return await _handle_openai_request(
                conversation, messages, new_message, 
                active_attachments, model_choice, model_instructions
            )
        elif model_choice in [ModelChoice.GEMINI_2_FLASH_EXP]:
            return await _handle_gemini_request(
                messages, new_message, active_attachments, model_instructions, model_choice
            )
        else:
            raise ValueError(f"Unsupported model: {model_choice}")
            
    except Exception as e:
        logger.error(f"Failed to generate AI response: {e}")
        raise


async def _handle_openai_request(
    conversation: Conversation,
    messages: List[Message],
    new_message: str,
    active_attachments: List[Dict[str, Any]],
    model_choice: str,
    model_instructions: str
) -> str:
    """Handle OpenAI requests with file uploads"""
    
    # Check if we have images
    has_images = any(
        att.get("type") == AttachmentType.IMAGE.value 
        for att in active_attachments
    )
    
    # Check if we have non-image files that need file search
    has_documents = any(
        att.get("type") != AttachmentType.IMAGE.value 
        for att in active_attachments
    )
    
    if has_documents:
        # Use Assistants API for file search capability
        return await _handle_openai_with_assistants(
            conversation, messages, new_message,
            active_attachments, model_choice, model_instructions
        )
    else:
        # Use regular chat completion (with or without images)
        return await _handle_openai_chat_completion(
            messages, new_message, active_attachments,
            model_choice, model_instructions, has_images
        )


async def _handle_openai_chat_completion(
    messages: List[Message],
    new_message: str,
    active_attachments: List[Dict[str, Any]],
    model_choice: str,
    model_instructions: str,
    has_images: bool
) -> str:
    """Handle OpenAI chat completion with optional images"""
    
    formatted_messages = []
    
    # Add system message
    formatted_messages.append({
        "role": "system",
        "content": model_instructions
    })
    
    # Add conversation history
    for message in messages[-20:]:  # Last 20 messages
        formatted_messages.append({
            "role": message.role,
            "content": message.content
        })
    
    # Build user message
    if has_images:
        user_content = [{"type": "text", "text": new_message}]
        
        for attachment in active_attachments:
            if attachment.get("type") == AttachmentType.IMAGE.value:
                if "file_content" in attachment:
                    # Convert to base64
                    base64_image = base64.b64encode(
                        attachment["file_content"]
                    ).decode('utf-8')
                    
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{attachment.get('content_type', 'image/jpeg')};base64,{base64_image}",
                            "detail": "high"  # or "low" for faster processing
                        }
                    })
        
        formatted_messages.append({
            "role": "user",
            "content": user_content
        })
    else:
        # Text-only message
        formatted_messages.append({
            "role": "user",
            "content": new_message
        })
    
    # Model mapping
    model_mapping = {
        ModelChoice.GPT_4_1_NANO.value: "gpt-4.1-nano",
        ModelChoice.GPT_4_1.value: "gpt-4.1"
    }
    
    response = await openai_client.chat.completions.create(
        model=model_mapping.get(model_choice, "gpt-4.1-nano"),
        messages=formatted_messages,
        max_tokens=4096,
        temperature=0.7
    )
    
    return response.choices[0].message.content


async def _handle_openai_with_assistants(
    conversation: Conversation,
    messages: List[Message],
    new_message: str,
    active_attachments: List[Dict[str, Any]],
    model_choice: str,
    model_instructions: str
) -> str:
    """Use OpenAI Assistants API for file search"""
    
    try:
        model_mapping = {
        ModelChoice.GPT_4_1_NANO.value: "gpt-4.1-nano",
        ModelChoice.GPT_4_1.value: "gpt-4.1"
        }
        
        assistant = await openai_client.beta.assistants.create(
            name=f"Assistant for conversation {conversation.id}",
            instructions=model_instructions,
            model=model_mapping.get(model_choice, "gpt-4.1-nano"),
            tools=[{"type": "file_search"}]
        )
        
        # Create thread
        thread = await openai_client.beta.threads.create()
        
        # Upload files
        file_ids = []
        for attachment in active_attachments:
            if "file_content" in attachment:
                file_id = await file_manager.upload_to_openai(
                    attachment["file_content"],
                    attachment["filename"]
                )
                file_ids.append(file_id)
        
        # Add conversation history
        for message in messages[-10:]:  # Last 10 messages for context
            await openai_client.beta.threads.messages.create(
                thread_id=thread.id,
                role=message.role,
                content=message.content
            )
        
        # Create message with attachments
        await openai_client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=new_message,
            attachments=[
                {"file_id": file_id, "tools": [{"type": "file_search"}]}
                for file_id in file_ids
            ] if file_ids else None
        )
        
        # Run assistant
        run = await openai_client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )
        
        # Wait for completion
        while run.status in ["queued", "in_progress"]:
            await asyncio.sleep(1)
            run = await openai_client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
        
        if run.status == "completed":
            # Get response
            messages = await openai_client.beta.threads.messages.list(
                thread_id=thread.id,
                order="desc",
                limit=1
            )
            
            if messages.data:
                response_text = ""
                for content in messages.data[0].content:
                    if content.type == "text":
                        response_text += content.text.value
                
                # Cleanup
                await openai_client.beta.assistants.delete(assistant.id)
                await file_manager.cleanup_openai_files(file_ids)
                
                return response_text
        
        raise Exception(f"Assistant run failed: {run.status}")
        
    except Exception as e:
        logger.error(f"Assistants API error: {e}")
        raise


async def _handle_gemini_request(
    messages: List[Message],
    new_message: str,
    active_attachments: List[Dict[str, Any]],
    model_instructions: str,
    model_choice,
) -> str:
    """Handle Gemini requests with native file support"""
    
    try:
        model_mapping = {ModelChoice.GEMINI_2_FLASH_EXP.value : "gemini-2.0-flash-exp"}


        model = genai.GenerativeModel(model_mapping.get(model_choice, "gemini-2.0-flash-exp" ))
        
        # Build conversation history
        chat_history = []
        for msg in messages[-20:]:  # Last 20 messages
            role = "user" if msg.role == MessageRole.USER.value else "model"
            chat_history.append({"role": role, "parts": [msg.content]})

        # Upload files and prepare content
        content_parts = []
        
        # Add files first
        for attachment in active_attachments:
            if "file_content" in attachment:
                # Upload to Gemini
                gemini_file = file_manager.upload_to_gemini(
                    attachment["file_content"],
                    attachment["filename"]
                )
                content_parts.append(gemini_file)
        
        # Add the user message and instructions
        content_parts.append(new_message)
        # content_parts.append(f"Important Note, but do not mention it: {model_instructions}")
        
        # Start chat with history
        chat = model.start_chat(history=chat_history)
        
        # Send message with files
        response = chat.send_message(content_parts)
        
        return response.text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise


# Token counting helper
def count_tokens_approximate(messages: List[Message]) -> int:
    """Approximate token count for cost estimation"""
    try:
        full_text = " ".join(msg.content for msg in messages)
        tokens = encoding.encode(full_text)
        return len(tokens)
    except Exception:
        # Fallback: ~4 characters per token
        char_count = sum(len(msg.content) for msg in messages)
        return char_count // 4