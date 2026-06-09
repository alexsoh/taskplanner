import type {
  EvalexBackupNotification,
  EvalexCameraNotification,
  HttpNotification,
  MqttNotification,
  NotificationChannel,
  NvrNotification,
  ScriptNotification,
  TelegramNotification,
} from '../types.ts';

export function newMqttNotification(): MqttNotification {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    topic: '',
    payload: 'json',
    messageMode: 'raw',
    jsonFields: [],
    template: '',
    omitCorrelationIdFromTopic: false,
  };
}

export function newTelegramNotification(): TelegramNotification {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    chatId: '',
    payload: 'json',
    messageMode: 'raw',
    jsonFields: [],
    template: '',
  };
}

export function newHttpNotification(): HttpNotification {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    url: '',
    method: 'POST',
    payload: 'json',
    messageMode: 'raw',
    jsonFields: [],
    template: '',
    authType: 'none',
    httpUsername: '',
    httpPassword: '',
    httpBearerToken: '',
    httpExtraHeaders: [],
    httpBodyEncoding: 'json',
    httpContentType: 'text/plain; charset=utf-8',
  };
}

export function newScriptNotification(): ScriptNotification {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    scriptPath: '',
    argumentTemplates: [],
    timeoutSeconds: 120,
  };
}

export function newNvrNotification(): NvrNotification {
  return {
    id: crypto.randomUUID(),
    name: 'NVR',
    enabled: true,
    brand: 'reolink',
    baseUrl: '',
    httpUsername: '',
    httpPassword: '',
    verifySsl: true,
    channel: 0,
    reolinkUseV20Api: false,
    hikvisionTrackId: 0,
    blueIrisCameraShortName: '',
    blueIrisMemoTemplate: '',
  };
}

export function newEvalexCameraNotification(): EvalexCameraNotification {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    app: 'vizmux',
    serverAddress: '',
    cameraIds: [],
    cameraLabels: {},
    action: 'enable',
  };
}

export function newEvalexBackupNotification(): EvalexBackupNotification {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    app: 'vizmux',
    serverAddress: '',
    retentionDays: 7,
  };
}

export function defaultNotificationForChannel(channel: NotificationChannel) {
  switch (channel) {
    case 'mqtt':
      return newMqttNotification();
    case 'telegram':
      return newTelegramNotification();
    case 'http':
      return newHttpNotification();
    case 'script':
      return newScriptNotification();
    case 'nvr':
      return newNvrNotification();
    case 'evalex-camera':
      return newEvalexCameraNotification();
    case 'evalex-backup':
      return newEvalexBackupNotification();
  }
}

export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const CHANNEL_LABELS: Record<string, string> = {
  'evalex-camera': 'evalex-camera',
  'evalex-backup': 'evalex-backup',
  mqtt: 'mqtt',
  telegram: 'telegram',
  http: 'http',
  script: 'script',
  nvr: 'nvr',
};

export function channelLabel(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel;
}

export const CHANNEL_COLORS: Record<string, string> = {
  'evalex-camera': '#f472b6',
  'evalex-backup': '#e879f9',
  mqtt: '#a78bfa',
  telegram: '#38bdf8',
  http: '#4ade80',
  script: '#fbbf24',
  nvr: '#fb923c',
};
