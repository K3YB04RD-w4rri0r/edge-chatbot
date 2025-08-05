// TokenManager.js - Manages token lifecycle and proactive refresh
import apiClient from './apiClient';

class TokenManager {
  constructor() {
    this.refreshTimer = null;
    this.tokenExpiryTime = null;
  }

  // Parse JWT token to get expiry time
  parseJwtToken(token) {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(
        atob(base64)
          .split('')
          .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );
      return JSON.parse(jsonPayload);
    } catch (error) {
      console.error('Error parsing JWT token:', error);
      return null;
    }
  }

  // Get token from cookie (for checking expiry)
  getTokenFromCookie() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'access_token') {
        return value;
      }
    }
    return null;
  }

  // Start monitoring token expiry
  startTokenMonitoring() {
    // Clear any existing timer
    this.stopTokenMonitoring();

    // Check token expiry every minute
    this.checkTokenExpiry();
    this.refreshTimer = setInterval(() => {
      this.checkTokenExpiry();
    }, 60000); // Check every minute
  }

  // Stop monitoring token expiry
  stopTokenMonitoring() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  // Check if token is about to expire and refresh if needed
  async checkTokenExpiry() {
    const token = this.getTokenFromCookie();
    if (!token) {
      console.log('No token found, stopping monitoring');
      this.stopTokenMonitoring();
      return;
    }

    const payload = this.parseJwtToken(token);
    if (!payload || !payload.exp) {
      console.error('Invalid token payload');
      return;
    }

    // Convert exp to milliseconds
    const expiryTime = payload.exp * 1000;
    const currentTime = Date.now();
    const timeUntilExpiry = expiryTime - currentTime;

    console.log(`Token expires in ${Math.floor(timeUntilExpiry / 60000)} minutes`);

    // Refresh token if it expires in less than 5 minutes
    if (timeUntilExpiry < 5 * 60 * 1000) {
      console.log('Token expiring soon, refreshing...');
      try {
        await apiClient.refreshToken();
        console.log('Token refreshed successfully');
      } catch (error) {
        console.error('Failed to refresh token:', error);
      }
    }
  }

  // Initialize token monitoring when user logs in
  init() {
    this.startTokenMonitoring();
    
    // Also monitor when the page gains focus (in case user returns after being away)
    window.addEventListener('focus', () => {
      console.log('Page gained focus, checking token...');
      this.checkTokenExpiry();
    });
  }

  // Clean up when user logs out
  cleanup() {
    this.stopTokenMonitoring();
  }
}

// Create singleton instance
const tokenManager = new TokenManager();

export default tokenManager;