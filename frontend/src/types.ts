export type PayloadType = 'json' | 'image' | 'both';
export type MessageMode = 'raw' | 'template' | 'simple';
export type NotificationChannel = 'mqtt' | 'telegram' | 'http' | 'script' | 'nvr' | 'evalex';

export interface MqttSettings {
  broker: string;
  port: number;
  username: string;
  password: string;
  publishQos: number;
  subscribeQos: number;
  enabled: boolean;
  listenerEnabled: boolean;
  listenerTopicPrefix: string;
  commandListenerEnabled: boolean;
  commandListenerTopicPrefix: string;
}

export interface MqttNotification {
  id: string;
  name: string;
  enabled: boolean;
  topic: string;
  payload: PayloadType;
  messageMode: MessageMode;
  jsonFields: string[];
  template: string;
  omitCorrelationIdFromTopic?: boolean;
}

export interface TelegramNotification {
  id: string;
  name: string;
  enabled: boolean;
  chatId: string;
  payload: PayloadType;
  messageMode: MessageMode;
  jsonFields: string[];
  template: string;
}

export type HttpMethod = 'GET' | 'POST' | 'PUT';
export type HttpAuthType = 'none' | 'basic' | 'digest' | 'bearer';
export type HttpBodyEncoding = 'json' | 'raw';

export interface HttpHeaderEntry {
  name: string;
  value: string;
}

export interface HttpNotification {
  id: string;
  name: string;
  enabled: boolean;
  url: string;
  getQueryTemplate?: string;
  method: HttpMethod;
  payload: PayloadType;
  messageMode: MessageMode;
  jsonFields: string[];
  template: string;
  authType: HttpAuthType;
  httpUsername: string;
  httpPassword: string;
  httpBearerToken: string;
  httpExtraHeaders: HttpHeaderEntry[];
  httpBodyEncoding: HttpBodyEncoding;
  httpContentType: string;
}

export interface ScriptNotification {
  id: string;
  name: string;
  enabled: boolean;
  scriptPath: string;
  argumentTemplates: string[];
  timeoutSeconds: number;
}

export type NvrBrand = 'dahua' | 'ezviz' | 'hikvision' | 'reolink' | 'blueiris';

export interface NvrNotification {
  id: string;
  name: string;
  enabled: boolean;
  brand: NvrBrand;
  baseUrl: string;
  httpUsername: string;
  httpPassword: string;
  verifySsl: boolean;
  channel: number;
  reolinkUseV20Api: boolean;
  hikvisionTrackId: number;
  blueIrisCameraShortName: string;
  blueIrisMemoTemplate: string;
}

export type EvalexApp = 'vizmux' | 'piyoai' | 'vizrec';
export type EvalexAction = 'enable' | 'disable';

export interface EvalexNotification {
  id: string;
  name: string;
  enabled: boolean;
  app: EvalexApp;
  serverAddress: string;
  cameraIds: string[];
  cameraLabels?: Record<string, string>;
  action: EvalexAction;
}

export interface TelegramSettings {
  token: string;
  enabled: boolean;
  botEnabled: boolean;
  botAllowedChatIds: string[];
  botCommands: unknown[];
  botBlacklistPatterns: string[];
}

export interface Profile {
  id: string;
  name: string;
  timezone: string;
  enabled: boolean;
  color: string;
  created_at: string;
}

export interface ScheduledAction {
  id: string;
  profile_id: string;
  label: string;
  day_of_week: number;
  time: string;
  channel: NotificationChannel;
  enabled: boolean;
  notification_config: Record<string, unknown>;
}

export interface ExecutionRun {
  id: string;
  scheduled_action_id: string | null;
  profile_id: string | null;
  scheduled_for: string;
  fired_at: string;
  status: string;
  error: string | null;
  channel: string;
  label: string;
  detail: Record<string, unknown> | null;
}

export interface CalendarEvent {
  action_id: string;
  profile_id: string;
  profile_name: string;
  profile_color: string;
  label: string;
  channel: string;
  day_of_week: number;
  time: string;
  occurrence_utc: string;
}

export interface AppSettings {
  mqtt: MqttSettings;
  telegram: TelegramSettings;
  upgradeToken?: string;
  allowedIps?: string[];
  serverPort?: number;
}

export interface UpdateCheckResponse {
  currentVersion: string;
  latestVersion: string;
  updateAvailable: boolean;
  changeSummary: string;
  tokenExpiresAt?: string;
  error?: string;
}
