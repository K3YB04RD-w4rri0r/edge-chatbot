import React from 'react';
import { CheckCircle, AlertCircle } from 'lucide-react';

const LoginScreen = ({ onLogin, healthStatus }) => {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold mb-6 text-center">Backend Test UI</h1>
        <button
          onClick={onLogin}
          className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 transition-colors"
        >
          Login with Microsoft
        </button>
        
        {healthStatus && (
          <div className="mt-4 p-3 rounded bg-gray-100">
            <div className="flex items-center gap-2">
              {healthStatus.status === 'OK' ? (
                <CheckCircle className="w-4 h-4 text-green-500" />
              ) : (
                <AlertCircle className="w-4 h-4 text-red-500" />
              )}
              <span className="text-sm">API Status: {healthStatus.status}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LoginScreen;