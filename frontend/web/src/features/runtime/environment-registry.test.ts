import { describe, expect, it } from 'vitest';
import { ENVIRONMENTS, availabilityLabel, environmentForPath } from './environment-registry';

describe('JARVIS environment registry', () => {
  it('resolves existing capability routes to their shared runtime environment', () => {
    expect(environmentForPath('/')).toMatchObject({ id: 'conversation' });
    expect(environmentForPath('/dashboard/geography')).toMatchObject({ id: 'world' });
    expect(environmentForPath('/image-generation')).toMatchObject({ id: 'visual' });
    expect(environmentForPath('/voice')).toMatchObject({ id: 'voice' });
    expect(environmentForPath('/dashboard/agents')).toMatchObject({ id: 'tasks' });
    expect(environmentForPath('/dashboard/connections')).toMatchObject({ id: 'communications' });
    expect(environmentForPath('/dashboard/bio-growth')).toMatchObject({ id: 'learning' });
    expect(environmentForPath('/dashboard/memory')).toMatchObject({ id: 'operations' });
  });

  it('does not expose device control as a navigable route until its connector is available', () => {
    for (const id of ['devices']) {
      const environment = ENVIRONMENTS.find((entry) => entry.id === id);
      expect(environment?.route).toBeNull();
    }
    expect(availabilityLabel('requires_connector')).toBe('Connector required');
    expect(availabilityLabel('coming_later')).toBe('Not connected');
  });
});
