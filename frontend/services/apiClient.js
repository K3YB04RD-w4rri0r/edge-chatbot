// apiClient.js - Centralized API client with automatic token refresh
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

class ApiClient {
  constructor() {
    this.baseURL = API_BASE_URL;
    this.isRefreshing = false;
    this.refreshSubscribers = [];
  }

  // Subscribe to token refresh completion
  subscribeTokenRefresh(callback) {
    this.refreshSubscribers.push(callback);
  }

  // Notify all subscribers when token is refreshed
  onTokenRefreshed() {
    this.refreshSubscribers.forEach(callback => callback());
    this.refreshSubscribers = [];
  }

  // Refresh the access token
  async refreshToken() {
    if (this.isRefreshing) {
      // If already refreshing, wait for it to complete
      return new Promise((resolve) => {
        this.subscribeTokenRefresh(() => resolve());
      });
    }

    this.isRefreshing = true;

    try {
      const response = await fetch(`${this.baseURL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include'
      });

      if (!response.ok) {
        throw new Error('Token refresh failed');
      }

      // Token refreshed successfully (new token is set in cookies by the server)
      this.isRefreshing = false;
      this.onTokenRefreshed();
      return true;
    } catch (error) {
      this.isRefreshing = false;
      this.refreshSubscribers = [];
      
      // Redirect to login if refresh fails
      window.location.href = `${this.baseURL}/auth/microsoft`;
      return false;
    }
  }

  // Main fetch wrapper with automatic retry on 401
  async fetch(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${this.baseURL}${url}`;
    
    // Always include credentials for cookie-based auth
    const fetchOptions = {
      ...options,
      credentials: 'include'
    };

    try {
      let response = await fetch(fullUrl, fetchOptions);

      // If unauthorized, try to refresh token and retry
      if (response.status === 401) {
        const refreshSuccess = await this.refreshToken();
        
        if (refreshSuccess) {
          // Retry the original request with new token
          response = await fetch(fullUrl, fetchOptions);
        }
      }

      return response;
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  // Convenience methods
  async get(url, options = {}) {
    return this.fetch(url, { ...options, method: 'GET' });
  }

  async post(url, data, options = {}) {
    return this.fetch(url, {
      ...options,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      body: JSON.stringify(data)
    });
  }

  async postForm(url, formData, options = {}) {
    return this.fetch(url, {
      ...options,
      method: 'POST',
      body: formData
    });
  }

  async delete(url, options = {}) {
    return this.fetch(url, { ...options, method: 'DELETE' });
  }
}

// Create singleton instance
const apiClient = new ApiClient();

export default apiClient;