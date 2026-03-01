import axios from "axios";
import { getStoredToken } from "#/api/auth";

// Create axios instance with auth interceptor
const api = axios.create({
  baseURL: "",
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = getStoredToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid, clear storage
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_user");
      
      // Optionally redirect to login
      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
