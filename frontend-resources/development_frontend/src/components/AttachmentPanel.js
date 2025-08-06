import React from 'react';
import { Eye, EyeOff, Download, Trash2, Paperclip, X, RefreshCw } from 'lucide-react';

const AttachmentPanel = ({ 
  isOpen,
  attachments, 
  activeAttachments, 
  onTogglePanel,
  onToggleAttachment, 
  onDownloadAttachment, 
  onDeleteAttachment 
}) => {
  const getStatusText = (status) => {
    switch(status) {
      case 'uploaded': return 'Ready';
      case 'pending': return 'Uploading...';
      case 'failed': return 'Failed';
      default: return status;
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
      case 'uploaded': return 'text-green-600';
      case 'pending': return 'text-yellow-600';
      case 'failed': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  return (
    <>
      {/* Toggle Button - Always visible */}
      <button
        onClick={onTogglePanel}
        className="fixed right-4 top-1/2 transform -translate-y-1/2 bg-white border border-gray-300 rounded-l-lg p-3 shadow-lg hover:bg-gray-50 z-30"
        title={isOpen ? "Close attachments" : "Open attachments"}
      >
        <div className="flex items-center gap-2">
          <Paperclip className="w-5 h-5" />
          {attachments.length > 0 && (
            <span className="bg-blue-600 text-white text-xs rounded-full px-2 py-0.5">
              {attachments.length}
            </span>
          )}
        </div>
      </button>

      {/* Overlay - Behind panel but above main content */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-20 z-40"
          onClick={onTogglePanel}
        />
      )}

      {/* Side Panel - Above overlay */}
      {isOpen && (
        <div className="fixed right-0 top-0 h-full bg-white shadow-2xl z-50" style={{ width: '320px' }}>
          <div className="h-full flex flex-col">
            {/* Panel Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold flex items-center gap-2">
                <Paperclip className="w-5 h-5" />
                Attachments ({attachments.length})
              </h3>
              <button
                onClick={onTogglePanel}
                className="p-2 hover:bg-gray-200 rounded-lg transition-colors bg-white"
                type="button"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {attachments.length === 0 ? (
                <p className="text-gray-500 text-center mt-8">No attachments yet</p>
              ) : (
                <div className="space-y-3">
                  {attachments.map(att => (
                    <div
                      key={att.uuid}
                      className={`p-3 rounded-lg border transition-colors ${
                        activeAttachments.has(att.uuid)
                          ? 'bg-blue-50 border-blue-300'
                          : 'bg-white border-gray-200'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm truncate" title={att.filename}>
                            {att.filename}
                          </p>
                          <p className="text-xs text-gray-500 mt-1">
                            {(att.file_size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => onToggleAttachment(att.uuid)}
                            className="p-1.5 hover:bg-gray-100 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                            disabled={att.status !== 'uploaded'}
                            title={att.status !== 'uploaded' ? 'Upload must complete first' : (activeAttachments.has(att.uuid) ? "Exclude from AI context" : "Include in AI context")}
                          >
                            {activeAttachments.has(att.uuid) ? (
                              <Eye className="w-4 h-4 text-blue-600" />
                            ) : (
                              <EyeOff className="w-4 h-4 text-gray-400" />
                            )}
                          </button>
                          <button
                            onClick={() => onDownloadAttachment(att.uuid, att.filename)}
                            className="p-1.5 hover:bg-gray-100 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                            disabled={att.status !== 'uploaded'}
                            title={att.status !== 'uploaded' ? 'Upload in progress or failed' : 'Download'}
                          >
                            <Download className="w-4 h-4 text-gray-600" />
                          </button>
                          <button
                            onClick={() => onDeleteAttachment(att.uuid)}
                            className="p-1.5 hover:bg-red-100 rounded"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4 text-red-600" />
                          </button>
                          {(att.status === 'pending' || att.status === 'failed') && (
                            <button
                              onClick={() => onDeleteAttachment(att.uuid)}
                              className="p-1.5 hover:bg-yellow-100 rounded"
                              title="Remove and re-upload"
                            >
                              <RefreshCw className="w-4 h-4 text-yellow-600" />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Active Count */}
            {attachments.length > 0 && (
              <div className="p-4 border-t bg-gray-50">
                <p className="text-sm text-gray-600">
                  <span className="font-medium">{activeAttachments.size}</span> of {attachments.length} active in AI context
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default AttachmentPanel;