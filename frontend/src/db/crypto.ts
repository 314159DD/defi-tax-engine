/**
 * Encryption utilities for client-side data backup.
 *
 * Uses AES-256-GCM via the Web Crypto API.
 * Key derivation: PBKDF2 with 100K iterations.
 */

const PBKDF2_ITERATIONS = 100_000;
const SALT_BYTES = 16;
const IV_BYTES = 12; // recommended for AES-GCM
const KEY_LENGTH = 256; // AES-256

/**
 * Derive an AES-256-GCM CryptoKey from a user identifier and salt.
 *
 * Uses PBKDF2 with SHA-256 and 100K iterations.
 */
export async function deriveKey(
  userId: string,
  salt: Uint8Array,
): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(userId) as unknown as BufferSource,
    'PBKDF2',
    false,
    ['deriveKey'],
  );

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt as unknown as BufferSource,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    keyMaterial,
    {
      name: 'AES-GCM',
      length: KEY_LENGTH,
    },
    false, // not extractable
    ['encrypt', 'decrypt'],
  );
}

/**
 * Encrypt a string using AES-256-GCM.
 *
 * Returns an ArrayBuffer containing: IV (12 bytes) + ciphertext.
 */
export async function encrypt(
  data: string,
  key: CryptoKey,
): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));

  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv as unknown as BufferSource },
    key,
    encoder.encode(data) as unknown as BufferSource,
  );

  // Prepend IV to ciphertext for self-contained decryption
  const result = new Uint8Array(iv.byteLength + ciphertext.byteLength);
  result.set(iv, 0);
  result.set(new Uint8Array(ciphertext), iv.byteLength);

  return result.buffer;
}

/**
 * Decrypt an ArrayBuffer (IV + ciphertext) using AES-256-GCM.
 *
 * Returns the decrypted plaintext string.
 */
export async function decrypt(
  encrypted: ArrayBuffer,
  key: CryptoKey,
): Promise<string> {
  const data = new Uint8Array(encrypted);
  const iv = data.slice(0, IV_BYTES);
  const ciphertext = data.slice(IV_BYTES);

  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as unknown as BufferSource },
    key,
    ciphertext as unknown as BufferSource,
  );

  const decoder = new TextDecoder();
  return decoder.decode(decrypted);
}

/**
 * Generate a random salt for key derivation.
 */
export function generateSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(SALT_BYTES));
}
