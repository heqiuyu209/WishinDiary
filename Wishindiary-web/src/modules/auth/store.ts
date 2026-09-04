import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getSessionApi } from './api';

export interface UserProfile {
  email?: string;
}

export const useAuthStore = defineStore('auth', () => {
  const currentUsername = ref('');
  const currentEmail = ref('');
  const isLoggedIn = ref(false);

  const login = (username: string, profile: UserProfile = {}) => {
    currentUsername.value = username;
    currentEmail.value = profile.email || '';
    isLoggedIn.value = true;
  };

  const logout = () => {
    currentUsername.value = '';
    currentEmail.value = '';
    isLoggedIn.value = false;
  };

  const refreshSession = async (): Promise<boolean> => {
    if (isLoggedIn.value) return true;

    try {
      const response = await getSessionApi();
      currentUsername.value = response.data.username ?? '';
      currentEmail.value = '';
      isLoggedIn.value = true;
      return true;
    } catch {
      logout();
      return false;
    }
  };

  return { currentUsername, currentEmail, isLoggedIn, login, logout, refreshSession };
});
