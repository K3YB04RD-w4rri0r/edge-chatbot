from abc import ABC, abstractmethod
from typing import BinaryIO
import os
import hashlib
from pathlib import Path
import magic
from datetime import datetime, timezone, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.core.exceptions import ResourceNotFoundError
import io

from models.attachments_model import AttachmentType
from shared_variables import settings



UTC = timezone.utc

class FileStorageBackend(ABC):
    """Abstract base class for file storage backends"""
    
    @abstractmethod
    async def store(self, file: BinaryIO, path: str) -> str:
        """Store a file and return the storage path"""
        pass
    
    @abstractmethod
    async def retrieve(self, path: str) -> BinaryIO:
        """Retrieve a file by path"""
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file by path"""
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists"""
        pass
    
    @abstractmethod
    async def generate_presigned_url(self, path: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for direct upload/download"""
        pass

class AzureFileStorage(FileStorageBackend):
    """Azure Blob Storage backend"""
    
    def __init__(self, connection_string: str, container_name: str):
        """
        Initialize Azure storage backend
        
        Args:
            connection_string: Azure Storage connection string
            container_name: Name of the container to use
        """
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
        # Create container if it doesn't exist
        try:
            self.container_client.get_container_properties()
        except ResourceNotFoundError:
            self.container_client.create_container()
    
    async def store(self, file: BinaryIO, path: str) -> str:
        """Store a file in Azure Blob Storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=path
            )
            
            # Read file content
            file.seek(0)
            file_content = file.read()
            file.seek(0)
            
            # Upload to Azure
            blob_client.upload_blob(file_content, overwrite=True)
            
            return f"azure://{self.container_name}/{path}"
        except Exception as e:
            raise Exception(f"Failed to upload to Azure: {e}")
    
    async def retrieve(self, path: str) -> BinaryIO:
        """Retrieve a file from Azure Blob Storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=path
            )
            
            # Download blob content
            blob_data = blob_client.download_blob()
            content = blob_data.readall()
            
            # Return as BytesIO object
            return io.BytesIO(content)
        except ResourceNotFoundError:
            raise Exception(f"File not found in Azure: {path}")
        except Exception as e:
            raise Exception(f"Failed to retrieve from Azure: {e}")
    
    async def delete(self, path: str) -> bool:
        """Delete a file from Azure Blob Storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=path
            )
            blob_client.delete_blob()
            return True
        except ResourceNotFoundError:
            return False
        except Exception:
            return False
    
    async def exists(self, path: str) -> bool:
        """Check if a file exists in Azure Blob Storage"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=path
            )
            blob_client.get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False
    
    async def generate_presigned_url(self, path: str, expires_in: int = 3600) -> str:
        """Generate a SAS URL for direct access to the blob"""
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, 
            blob=path
        )
        
        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=blob_client.account_name,
            container_name=self.container_name,
            blob_name=path,
            account_key=self.blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(UTC) + timedelta(seconds=expires_in)
        )
        
        # Construct full URL
        return f"{blob_client.url}?{sas_token}"

class FileService:
    """Service for handling file operations"""
    
    def __init__(self, storage_backend: FileStorageBackend):
        self.storage = storage_backend
        self.mime = magic.Magic(mime=True)
    
    def calculate_file_hash(self, file: BinaryIO) -> str:
        """Calculate SHA-256 hash of a file"""
        sha256_hash = hashlib.sha256()
        file.seek(0)
        
        # Read in chunks to handle large files efficiently
        while chunk := file.read(8192):
            sha256_hash.update(chunk)
        
        # Always seek back to beginning for subsequent operations
        file.seek(0)
        return sha256_hash.hexdigest()
    
    def detect_content_type(self, file: BinaryIO) -> str:
        """Detect actual content type of file"""
        file.seek(0)
        
        # Read a reasonable amount for magic detection
        sample = file.read(2048)
        file.seek(0)
        
        try:
            content_type = self.mime.from_buffer(sample)
            return content_type
        except Exception:
            # Fallback to application/octet-stream if detection fails
            return "application/octet-stream"
        
    def classify_attachment_type(self, content_type: str, filename: str = None) -> AttachmentType:
        """
        Classify attachment based on MIME type and filename
        
        Args:
            content_type: MIME type of the file
            filename: Optional filename for additional context
            
        Returns:
            AttachmentType enum value
        """
        # Normalize content type
        content_type = content_type.lower()
        
        # Image types
        if content_type.startswith('image/'):
            return AttachmentType.IMAGE
        
        # Document types
        document_types = {
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/plain',
            'text/csv',
            'text/markdown',
            'text/rtf',
            'application/rtf'
        }
        if content_type in document_types:
            return AttachmentType.DOCUMENT
        
        # Code/text files (check by extension if content type is generic)
        if filename:
            code_extensions = {
                '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cs',
                '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.r',
                '.sh', '.bat', '.ps1', '.yaml', '.yml', '.json', '.xml', '.html',
                '.css', '.scss', '.sass', '.sql', '.dockerfile', '.makefile'
            }
            ext = Path(filename).suffix.lower()
            if ext in code_extensions or content_type.startswith('text/'):
                return AttachmentType.DOCUMENT
        
        # Audio types
        if content_type.startswith('audio/'):
            return AttachmentType.OTHER
        
        # Archive types
        archive_types = {
            'application/zip',
            'application/x-zip-compressed',
            'application/x-rar-compressed',
            'application/x-tar',
            'application/x-7z-compressed',
            'application/gzip',
            'application/x-bzip2'
        }
        if content_type in archive_types:
            return AttachmentType.OTHER
        
        # Video types are unsupported
        if content_type.startswith('video/'):
            return AttachmentType.OTHER

        # OTHER for unrecognized types
        return AttachmentType.OTHER

    def generate_storage_path(self, user_id: str, conversation_id: int, filename: str, content_hash: str = None) -> str:
        """
        Generate a storage path for the file
        
        Args:
            user_id: ID of the user uploading the file
            conversation_id: ID of the conversation the file belongs to
            filename: Original filename
            content_hash: Optional file hash for deduplication
            
        Returns:
            Storage path string
        """
        # Sanitize filename
        safe_filename = self._sanitize_filename(filename)
        
        # Get current date for organization
        now = datetime.now(UTC)
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        # Generate unique identifier
        # If we have a content hash, use first 8 chars to help with deduplication
        if content_hash:
            unique_id = content_hash[:8]
        else:
            # Otherwise use timestamp with microseconds
            unique_id = now.strftime('%H%M%S%f')[:12]
        
        # Build path: user_id/conversations/conversation_id/year/month/day/uniqueid_filename
        # This structure helps with:
        # - User isolation
        # - Conversation organization
        # - Time-based organization
        # - Avoiding naming conflicts
        storage_path = f"{user_id}/conversations/{conversation_id}/{year}/{month}/{day}/{unique_id}_{safe_filename}"
        
        return storage_path

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to remove potentially problematic characters
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename safe for storage
        """
        # Import required modules if not already imported
        import re
        import unicodedata
        
        # Normalize unicode characters
        filename = unicodedata.normalize('NFKD', filename)
        filename = filename.encode('ascii', 'ignore').decode('ascii')
        
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        
        # Remove any character that's not alphanumeric, dash, underscore, or dot
        filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
        
        # Ensure filename isn't empty
        if not filename:
            filename = 'unnamed_file'
        
        # Limit length to 255 characters (common filesystem limit)
        # Preserve extension if possible
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            # Keep extension and truncate name
            max_name_length = 255 - len(ext)
            filename = name[:max_name_length] + ext
        
        # Prevent directory traversal attacks
        filename = filename.replace('..', '')
        filename = filename.replace('/', '')
        filename = filename.replace('\\', '')
        
        # Don't allow hidden files
        if filename.startswith('.'):
            filename = '_' + filename[1:]
        
        return filename
    

# Initialize file storage service based on configuration
def get_storage_backend():
    """Factory function to create the appropriate storage backend"""
    if settings.storage_backend == "azure":
        if not settings.azure_storage_connection_string:
            raise ValueError("Azure connection string is required for Azure storage backend")
        return AzureFileStorage(
            connection_string=settings.azure_storage_connection_string,
            container_name=settings.azure_container_name
        )
    

# Initialize storage backend and file service , used in certain conversation routes 
storage_backend = get_storage_backend()
file_service = FileService(storage_backend)
