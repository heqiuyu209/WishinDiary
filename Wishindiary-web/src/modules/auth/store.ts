import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getSessionApi } from './api';

export interface UserProfile {
  email?: string;
  is_admin?: boolean;
}

export const useAuthStore = defineStore('auth', () => {
  const currentUsername = ref('');
  const currentEmail = ref('');
  const isLoggedIn = ref(false);
  const isAdmin = ref(false);

  const login = (username: string, profile: UserProfile = {}) => {
    currentUsername.value = username;
    currentEmail.value = profile.email || '';
    isLoggedIn.value = true;
    isAdmin.value = profile.is_admin ?? false;
  };

  const logout = () => {
    currentUsername.value = '';
    currentEmail.value = '';
    isLoggedIn.value = false;
    isAdmin.value = false;
  };

  const refreshSession = async (): Promise<boolean> => {
    if (isLoggedIn.value) return true;

    try {
      const response = await getSessionApi();
      currentUsername.value = response.data.username ?? '';
      currentEmail.value = response.data.email ?? '';
      isAdmin.value = response.data.is_admin ?? false;
      isLoggedIn.value = true;
      return true;
    } catch {
      logout();
      return false;
    }
  };

  return { currentUsername, currentEmail, isLoggedIn, isAdmin, login, logout, refreshSession };
});
