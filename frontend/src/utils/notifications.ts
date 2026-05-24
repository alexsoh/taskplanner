import type {
  EvalexNotification,
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

export function newEvalexNotification(): EvalexNotification {
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
    case 'evalex':
      return newEvalexNotification();
  }
}

export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const CHANNEL_COLORS: Record<string, string> = {
  mqtt: '#a78bfa',
  telegram: '#38bdf8',
  http: '#4ade80',
  script: '#fbbf24',
  nvr: '#fb923c',
  evalex: '#f472b6',
};
