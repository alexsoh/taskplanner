import { describe, it, expect, beforeEach } from 'vitest';
import { getApiBase } from './client';

describe('TaskPlanner API Client - Configuration', () => {
  beforeEach(() => {
    // Clear window config before each test
    delete (window as any).__TASKPLANNER_CONFIG__;
  });

  describe('getApiBase()', () => {
    it('should return empty string when config is not set (standalone mode)', () => {
      expect(getApiBase()).toBe('');
    });

    it('should return configured apiBaseUrl when __TASKPLANNER_CONFIG__ is set', () => {
      (window as any).__TASKPLANNER_CONFIG__ = {
        apiBaseUrl: '/apps/taskplanner/proxy',
      };
      expect(getApiBase()).toBe('/apps/taskplanner/proxy');
    });

    it('should return empty string when apiBaseUrl is not defined in config', () => {
      (window as any).__TASKPLANNER_CONFIG__ = {};
      expect(getApiBase()).toBe('');
    });

    it('should return empty string when config is null', () => {
      (window as any).__TASKPLANNER_CONFIG__ = null;
      expect(getApiBase()).toBe('');
    });

    it('should handle different apiBaseUrl formats', () => {
      const testCases = [
        { url: '', expected: '' },
        { url: 'http://localhost:8200', expected: 'http://localhost:8200' },
        { url: '/proxy', expected: '/proxy' },
        { url: '/apps/taskplanner/proxy', expected: '/apps/taskplanner/proxy' },
      ];

      testCases.forEach(({ url, expected }) => {
        (window as any).__TASKPLANNER_CONFIG__ = { apiBaseUrl: url };
        expect(getApiBase()).toBe(expected);
      });
    });
  });

  describe('API URL Construction', () => {
    it('should construct correct URLs in standalone mode (empty base)', () => {
      (window as any).__TASKPLANNER_CONFIG__ = { apiBaseUrl: '' };
      const base = getApiBase();
      expect(`${base}/api/profiles`).toBe('/api/profiles');
      expect(`${base}/api/calendar`).toBe('/api/calendar');
    });

    it('should construct correct URLs in embedded mode (/apps/taskplanner/proxy)', () => {
      (window as any).__TASKPLANNER_CONFIG__ = {
        apiBaseUrl: '/apps/taskplanner/proxy',
      };
      const base = getApiBase();
      expect(`${base}/api/profiles`).toBe('/apps/taskplanner/proxy/api/profiles');
      expect(`${base}/api/calendar`).toBe('/apps/taskplanner/proxy/api/calendar');
    });

    it('should construct correct URLs with full backend URL', () => {
      (window as any).__TASKPLANNER_CONFIG__ = {
        apiBaseUrl: 'http://localhost:8200',
      };
      const base = getApiBase();
      expect(`${base}/api/profiles`).toBe('http://localhost:8200/api/profiles');
      expect(`${base}/api/executions`).toBe('http://localhost:8200/api/executions');
    });
  });

  describe('eVaultex Integration Compatibility', () => {
    it('should match PiyoAI/VizMux config pattern', () => {
      // eVaultex injects config like: window.__TASKPLANNER_CONFIG__ = { apiBaseUrl: '/apps/taskplanner/proxy' }
      (window as any).__TASKPLANNER_CONFIG__ = {
        apiBaseUrl: '/apps/taskplanner/proxy',
      };

      // Should read at call time (not hardcoded)
      expect(getApiBase()).toBe('/apps/taskplanner/proxy');

      // Should allow runtime changes (for testing/switching backends)
      (window as any).__TASKPLANNER_CONFIG__.apiBaseUrl = 'http://localhost:8200';
      expect(getApiBase()).toBe('http://localhost:8200');
    });

    it('should support multiple instances with different configs', () => {
      // First instance: taskplanner
      (window as any).__TASKPLANNER_CONFIG__ = { apiBaseUrl: '/apps/taskplanner/proxy' };
      expect(getApiBase()).toBe('/apps/taskplanner/proxy');

      // Simulate switching to another instance would require changing the config
      // (This would happen through navigation or iframe switching in real usage)
      (window as any).__TASKPLANNER_CONFIG__ = { apiBaseUrl: '/apps/taskplanner-2/proxy' };
      expect(getApiBase()).toBe('/apps/taskplanner-2/proxy');
    });
  });
});
