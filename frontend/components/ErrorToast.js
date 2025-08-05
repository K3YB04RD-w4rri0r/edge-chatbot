import React from 'react';
import { AlertCircle } from 'lucide-react';

const ErrorToast = ({ error, onClose }) => {
  if (!error) return null;

  return (
    <div className="fixed bottom-4 right-4 bg-red-600 text-white p-4 rounded-lg shadow-lg">
      <div className="flex items-center gap-2">
        <AlertCircle className="w-5 h-5" />
        <p>{error}</p>
        <button
          onClick={onClose}
          className="ml-4 hover:text-gray-200"
        >
          ×
        </button>
      </div>
    </div>
  );
};

export default ErrorToast;