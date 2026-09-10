/**
 * User settings CRUD operations on the Dexie database.
 *
 * Single-row table (id='default') for application-wide settings.
 */

import { db, type DBSettings } from './index';

const DEFAULT_SETTINGS_ID = 'default';

export interface UserSettings {
  country: string;
  defaultMethod: string;
  currentYear: number;
}

const DEFAULT_USER_SETTINGS: UserSettings = {
  country: 'US',
  defaultMethod: 'FIFO',
  currentYear: new Date().getFullYear(),
};

/**
 * Get user settings. Returns defaults if not yet configured.
 */
export async function getSettings(): Promise<UserSettings> {
  const row = await db.settings.get(DEFAULT_SETTINGS_ID);
  if (!row) {
    return { ...DEFAULT_USER_SETTINGS };
  }
  return {
    country: row.country,
    defaultMethod: row.defaultMethod,
    currentYear: row.currentYear,
  };
}

/**
 * Update user settings (partial update).
 */
export async function updateSettings(
  partial: Partial<UserSettings>,
): Promise<void> {
  const existing = await db.settings.get(DEFAULT_SETTINGS_ID);
  const now = new Date().toISOString();

  if (existing) {
    await db.settings.update(DEFAULT_SETTINGS_ID, {
      ...partial,
      updatedAt: now,
    });
  } else {
    await db.settings.put({
      id: DEFAULT_SETTINGS_ID,
      country: partial.country ?? DEFAULT_USER_SETTINGS.country,
      defaultMethod: partial.defaultMethod ?? DEFAULT_USER_SETTINGS.defaultMethod,
      currentYear: partial.currentYear ?? DEFAULT_USER_SETTINGS.currentYear,
      updatedAt: now,
    });
  }
}

/**
 * Reset settings to defaults.
 */
export async function resetSettings(): Promise<void> {
  await db.settings.put({
    id: DEFAULT_SETTINGS_ID,
    ...DEFAULT_USER_SETTINGS,
    updatedAt: new Date().toISOString(),
  });
}
