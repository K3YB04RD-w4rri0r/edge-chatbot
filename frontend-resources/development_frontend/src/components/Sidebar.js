import React from 'react';
import { User, LogOut, Plus, MessageSquare, CheckCircle, AlertCircle } from 'lucide-react';

const Sidebar = ({ 
  user, 
  conversations, 
  selectedConversation, 
  healthStatus, 
  onLogout, 
  onCreateConversation, 
  onSelectConversation 
}) => {
  return (
    <div className="w-80 bg-white shadow-lg flex flex-col h-full">
      <div className="p-4 border-b flex-shrink-0">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">Test UI</h1>
          <button
            onClick={onLogout}
            className="p-2 hover:bg-gray-100 rounded"
            title="Logout"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
        
        {user && (
          <div className="flex items-center gap-3 p-3 bg-gray-50 rounded">
            <User className="w-8 h-8 text-gray-400" />
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{user.display_name}</p>
              <p className="text-sm text-gray-500 truncate">{user.email}</p>
            </div>
          </div>
        )}
      </div>
      
      <div className="p-4 border-b flex-shrink-0">
        <button
          onClick={onCreateConversation}
          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Conversation
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto">
        {conversations.map(conv => (
          <div
            key={conv.id}
            onClick={() => onSelectConversation(conv.id)}
            className={`p-4 border-b cursor-pointer hover:bg-gray-50 ${
              selectedConversation?.id === conv.id ? 'bg-blue-50' : ''
            }`}
          >
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-gray-400" />
              <p className="font-medium truncate">{conv.conversation_title}</p>
            </div>
            <p className="text-sm text-gray-500 mt-1">
              {new Date(conv.created_at).toLocaleDateString()}
            </p>
          </div>
        ))}
      </div>
      
      {healthStatus && (
        <div className="p-4 border-t bg-gray-50 flex-shrink-0">
          <div className="flex items-center gap-2">
            {healthStatus.status === 'OK' ? (
              <CheckCircle className="w-4 h-4 text-green-500" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-500" />
            )}
            <span className="text-sm">
              Redis: {healthStatus.redis?.connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default Sidebar;