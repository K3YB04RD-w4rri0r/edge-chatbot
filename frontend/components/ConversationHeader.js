import React from 'react';
import { Cpu, Bot } from 'lucide-react';

const ConversationHeader = ({ conversation }) => {
  if (!conversation) return null;

  // Model display names
  const modelDisplayNames = {
    'gpt-4.1-nano': 'GPT-4.1 nano',
    'gpt-4.1': 'GPT 4.1',
    'gemini-2.0-flash-exp': 'Gemini 2.0 Flash'
  };

  // Shortened instruction labels
  const instructionLabels = {
    'You are a helpful, harmless, and honest assistant.': 'General Assistant',
    'You are an expert programming assistant.': 'Programming Assistant',
    'You are an expert at creating and improving resumes and CVs.': 'Resume/CV Expert'
  };

  return (
    <div className="bg-white border-b px-6 py-3 flex items-center justify-between">
      <div>
        <h2 className="text-lg font-semibold">{conversation.conversation_title}</h2>
        <div className="flex items-center gap-4 mt-1">
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Cpu className="w-4 h-4" />
            <span>{modelDisplayNames[conversation.model_choice] || conversation.model_choice}</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Bot className="w-4 h-4" />
            <span>{instructionLabels[conversation.model_instructions] || 'Custom Instructions'}</span>
          </div>
        </div>
      </div>
      <div className="text-sm text-gray-500">
        Created: {new Date(conversation.created_at).toLocaleDateString()}
      </div>
    </div>
  );
};

export default ConversationHeader;