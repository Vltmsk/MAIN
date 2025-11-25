/**
 * Типы для AdminTab
 */

export type AdminUser = {
  user: string;
  has_telegram: boolean;
  options_json?: string;
  tg_token?: string;
  chat_id?: string;
};

export type AdminUserSettings = {
  user: string;
  tg_token: string;
  chat_id: string;
  options_json?: string;
};

export type ErrorLog = {
  id: number;
  timestamp: string;
  exchange?: string;
  error_type: string;
  error_message: string;
  connection_id?: string;
  market?: string;
  symbol?: string;
  stack_trace?: string;
};

export interface AdminTabProps {
  userLogin: string;
  isAdmin: boolean;
  activeTab: string;
}

