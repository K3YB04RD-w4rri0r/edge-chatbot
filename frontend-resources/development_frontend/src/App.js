import React, { useState, useEffect } from 'react';
import { Plus } from 'lucide-react';
import LoginScreen from './components/LoginScreen';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import ConversationHeader from './components/ConversationHeader';
import AttachmentPanel from './components/AttachmentPanel';
import ErrorToast from './components/ErrorToast';
import apiClient from './services/apiClient';
import tokenManager from './services/TokenManager';
import './App.css';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [activeAttachments, setActiveAttachments] = useState(new Set());
  const [newMessage, setNewMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [healthStatus, setHealthStatus] = useState(null);
  const [error, setError] = useState(null);
  const [isAttachmentPanelOpen, setIsAttachmentPanelOpen] = useState(false);
  
  // State for conversation creation dialog
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newConversationData, setNewConversationData] = useState({
    title: '',
    model: 'gpt-4.1-nano',
    instructions: 'You are a helpful, harmless, and honest assistant.'
  });
  
  // Available options
  const modelOptions = [
    { value: 'gpt-4.1-nano', label: 'GPT 4.1 nano' },
    { value: 'gpt-4.1', label: 'GPT 4.1' },
    { value: 'gemini-2.0-flash-exp', label: 'Gemini 2.0 flash' }
    
  ];
  
  const instructionOptions = [
    { value: 'You are a helpful, harmless, and honest assistant.', label: 'General Assistant' },
    { value: 'You are an expert programming assistant.', label: 'Programming Assistant' },
    { value: 'You are an expert at creating and improving resumes and CVs.', label: 'Resume/CV Expert' }
  ];

  useEffect(() => {
    checkAuth();
    checkHealth();
    const healthInterval = setInterval(checkHealth, 30000);
    
    // Add escape key handler
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isAttachmentPanelOpen) {
        setIsAttachmentPanelOpen(false);
      }
    };
    
    document.addEventListener('keydown', handleEscape);
    
    return () => {
      clearInterval(healthInterval);
      document.removeEventListener('keydown', handleEscape);
      tokenManager.cleanup();
    };
  }, [isAttachmentPanelOpen]);

  const checkAuth = async () => {
    try {
      const response = await apiClient.get('/api/user/profile');
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        setIsAuthenticated(true);
        
        // Start token monitoring
        tokenManager.init();
        
        fetchConversations();
      } else if (response.status === 401) {
        // apiClient will automatically try to refresh, but if we're here it failed
        setIsAuthenticated(false);
        tokenManager.cleanup();
      } else {
        setIsAuthenticated(false);
        tokenManager.cleanup();
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setIsAuthenticated(false);
      tokenManager.cleanup();
    }
  };

  const checkHealth = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      const data = await response.json();
      setHealthStatus(data);
    } catch (err) {
      setHealthStatus({ status: 'error', error: err.message });
    }
  };

  const login = () => {
    window.location.href = `${API_BASE_URL}/auth/microsoft`;
  };

  const logout = async () => {
    try {
      await apiClient.post('/auth/logout', {});
      setIsAuthenticated(false);
      setUser(null);
      setConversations([]);
      setSelectedConversation(null);
      
      // Clean up token monitoring
      tokenManager.cleanup();
    } catch (err) {
      setError('Logout failed');
    }
  };

  const fetchConversations = async () => {
    try {
      const response = await apiClient.get('/api/conversations');
      if (response.ok) {
        const data = await response.json();
        setConversations(data);
      }
    } catch (err) {
      setError('Failed to fetch conversations');
    }
  };

  const createConversation = async () => {
    try {
      const payload = {
        conversation_title: newConversationData.title || `Conversation ${new Date().toLocaleString()}`,
        model_choice: newConversationData.model,
        model_instructions: newConversationData.instructions
      };
      
      const response = await apiClient.post('/api/conversations', payload);
      
      if (response.ok) {
        const newConv = await response.json();
        setConversations([newConv, ...conversations]);
        selectConversation(newConv.id);
        setShowCreateDialog(false);
        setNewConversationData({
          title: '',
          model: 'gpt-4.1-nano',
          instructions: 'You are a helpful, harmless, and honest assistant.'
        });
      } else {
        const errorData = await response.json();
        let errorMessage = 'Failed to create conversation';
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          errorMessage = errorData.detail.map(err => {
            const field = err.loc ? err.loc.join(' -> ') : 'unknown field';
            return `${field}: ${err.msg || err.message}`;
          }).join('; ');
        }
        setError(errorMessage);
      }
    } catch (err) {
      setError('Failed to create conversation: ' + err.message);
    }
  };
  
  const openCreateDialog = () => {
    setNewConversationData({
      title: `Conversation ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString()}`,
      model: 'gpt-4.1-nano',
      instructions: 'You are a helpful, harmless, and honest assistant.'
    });
    setShowCreateDialog(true);
  };

  const selectConversation = async (conversationId) => {
    try {
      setIsLoading(true);
      const response = await apiClient.get(`/api/conversations/${conversationId}`);
      
      if (response.ok) {
        const data = await response.json();
        setSelectedConversation(data);
        setMessages(data.messages || []);
        await fetchAttachments(conversationId);
      }
    } catch (err) {
      setError('Failed to load conversation');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchAttachments = async (conversationId) => {
    try {
      const response = await apiClient.get(`/api/conversations/${conversationId}/attachments`);
      
      if (response.ok) {
        const data = await response.json();
        setAttachments(data);
        const active = new Set(
          data.filter(att => att.activity_status === 'active').map(att => att.uuid)
        );
        setActiveAttachments(active);
      }
    } catch (err) {
      console.error('Failed to fetch attachments:', err);
    }
  };

  const sendMessage = async () => {
    if (!newMessage.trim() || !selectedConversation) return;
    
    try {
      setIsLoading(true);
      const response = await apiClient.post(
        `/api/conversations/${selectedConversation.id}/messages`,
        {
          content: newMessage,
          role: 'user',
          active_attachment_uuids: Array.from(activeAttachments)
        }
      );
      
      if (response.ok) {
        const data = await response.json();
        setMessages([...messages, data.user_message, data.assistant_reply].filter(Boolean));
        setNewMessage('');
      } else {
        const errorData = await response.json();
        let errorMessage = 'Failed to send message';
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          errorMessage = errorData.detail.map(err => err.msg || err.message).join(', ');
        }
        setError(errorMessage);
      }
    } catch (err) {
      setError('Failed to send message');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file || !selectedConversation) return;
    
    try {
      setIsLoading(true);
      
      // Step 1: Initiate upload
      const initiateResponse = await apiClient.post(
        `/api/conversations/${selectedConversation.id}/attachments/initiate`,
        {
          filename: file.name,
          content_type: file.type,
          file_size: file.size
        }
      );
      
      if (!initiateResponse.ok) {
        const errorData = await initiateResponse.json();
        throw new Error(errorData.detail || 'Failed to initiate upload');
      }
      
      const { attachment_id, uuid, upload_url, upload_method } = await initiateResponse.json();
      
      // Step 2: Always use API upload to avoid CORS issues
      const formData = new FormData();
      formData.append('file', file);
      
      const uploadResponse = await apiClient.postForm(
        `/api/conversations/${selectedConversation.id}/attachments/${uuid}/upload`,
        formData
      );
      
      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json();
        throw new Error(errorData.detail || 'Failed to upload file');
      }
      
      // Step 3: Refresh attachments list
      await fetchAttachments(selectedConversation.id);
      setError(null);
      
      // Reset file input
      event.target.value = '';
      
    } catch (err) {
      console.error('Upload error:', err);
      setError('Failed to upload file: ' + err.message);
      // Reset file input on error
      event.target.value = '';
    } finally {
      setIsLoading(false);
    }
  };

  const toggleAttachment = (uuid) => {
    const newActive = new Set(activeAttachments);
    if (newActive.has(uuid)) {
      newActive.delete(uuid);
    } else {
      newActive.add(uuid);
    }
    setActiveAttachments(newActive);
  };

  const deleteAttachment = async (uuid) => {
    if (!selectedConversation) return;
    
    try {
      const response = await apiClient.delete(
        `/api/conversations/${selectedConversation.id}/attachments/${uuid}`
      );
      
      if (response.ok) {
        await fetchAttachments(selectedConversation.id);
      }
    } catch (err) {
      setError('Failed to delete attachment');
    }
  };

  const downloadAttachment = (uuid, filename) => {
    const url = `${API_BASE_URL}/api/conversations/${selectedConversation.id}/attachments/${uuid}/download`;
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.credentials = 'include';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!isAuthenticated) {
    return <LoginScreen onLogin={login} healthStatus={healthStatus} />;
  }

  return (
    <div className="h-screen bg-gray-50 flex overflow-hidden">
      <Sidebar
        user={user}
        conversations={conversations}
        selectedConversation={selectedConversation}
        healthStatus={healthStatus}
        onLogout={logout}
        onCreateConversation={openCreateDialog}
        onSelectConversation={selectConversation}
      />
      
      <div className="flex-1 flex flex-col">
        <ConversationHeader conversation={selectedConversation} />
        
        <div className="flex-1 flex overflow-hidden">
          <ChatInterface
            selectedConversation={selectedConversation}
            messages={messages}
            newMessage={newMessage}
            isLoading={isLoading}
            onNewMessageChange={setNewMessage}
            onSendMessage={sendMessage}
            onFileUpload={handleFileUpload}
          />
        </div>
      </div>
      
      {selectedConversation && (
        <AttachmentPanel
          isOpen={isAttachmentPanelOpen}
          attachments={attachments}
          activeAttachments={activeAttachments}
          onTogglePanel={() => {
            console.log('Toggle panel clicked, current state:', isAttachmentPanelOpen);
            setIsAttachmentPanelOpen(!isAttachmentPanelOpen);
          }}
          onToggleAttachment={toggleAttachment}
          onDownloadAttachment={downloadAttachment}
          onDeleteAttachment={deleteAttachment}
        />
      )}
      
      {/* Create Conversation Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96 max-w-full mx-4">
            <h2 className="text-xl font-bold mb-4">Create New Conversation</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Title
                </label>
                <input
                  type="text"
                  value={newConversationData.title}
                  onChange={(e) => setNewConversationData({...newConversationData, title: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Enter conversation title"
                  autoFocus
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Model
                </label>
                <select
                  value={newConversationData.model}
                  onChange={(e) => setNewConversationData({...newConversationData, model: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {modelOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Assistant Type
                </label>
                <select
                  value={newConversationData.instructions}
                  onChange={(e) => setNewConversationData({...newConversationData, instructions: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {instructionOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
            
            <div className="flex gap-2 mt-6">
              <button
                onClick={createConversation}
                disabled={!newConversationData.title.trim()}
                className="flex-1 bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Create
              </button>
              <button
                onClick={() => setShowCreateDialog(false)}
                className="flex-1 bg-gray-300 text-gray-700 py-2 rounded hover:bg-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      
      <ErrorToast error={error} onClose={() => setError(null)} />
    </div>
  );
}

export default App;