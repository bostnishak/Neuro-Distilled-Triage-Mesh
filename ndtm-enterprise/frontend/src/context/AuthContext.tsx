import React, { createContext, useContext, useEffect, useState } from "react";
import { UserRole } from "../types/api";
import { apiClient } from "../services/apiClient";

interface AuthContextType {
  token: string | null;
  role: UserRole;
  email: string;
  setRole: (role: UserRole) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  token: null,
  role: "ARCHITECT",
  email: "architect@ndtm.enterprise",
  setRole: () => {},
  logout: () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setTokenState] = useState<string | null>(() => {
    return localStorage.getItem("ndtm_auth_token") || null;
  });
  const [role, setRole] = useState<UserRole>("ARCHITECT");
  const [email, setEmail] = useState<string>("architect@ndtm.enterprise");

  useEffect(() => {
    apiClient.setToken(token);
    if (token) {
      localStorage.setItem("ndtm_auth_token", token);
    } else {
      localStorage.removeItem("ndtm_auth_token");
    }
  }, [token]);

  const logout = () => {
    setTokenState(null);
    localStorage.removeItem("ndtm_auth_token");
    apiClient.setToken(null);
  };

  return (
    <AuthContext.Provider value={{ token, role, email, setRole, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
