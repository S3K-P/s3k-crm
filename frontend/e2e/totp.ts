/**
 * A minimal RFC 6238 TOTP code generator, using only Node's built-in `crypto`.
 *
 * Deliberately not a dependency: the backend's `pyotp` already gives that
 * side of the pair a well-audited implementation, and one hand-rolled
 * ~30-line function here is a smaller footprint than a new npm package for
 * a single test file. RFC 4226 (HOTP) + RFC 6238 (the time-stepped variant)
 * in full: base32-decode the secret, HMAC-SHA1 the 30-second time counter,
 * dynamically truncate to 6 digits.
 */

import { createHmac } from 'node:crypto';

const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

function base32Decode(secret: string): Buffer {
  const clean = secret.toUpperCase().replace(/=+$/, '');
  let bits = '';
  for (const char of clean) {
    const index = BASE32_ALPHABET.indexOf(char);
    if (index === -1) throw new Error(`Invalid base32 character: ${char}`);
    bits += index.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.slice(i, i + 8), 2));
  }
  return Buffer.from(bytes);
}

/** The current 6-digit TOTP code for a base32 secret, 30-second step. */
export function currentTotpCode(secret: string): string {
  const key = base32Decode(secret);
  const counter = Math.floor(Date.now() / 1000 / 30);

  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));

  const hmac = createHmac('sha1', key).update(counterBuffer).digest();
  const offset = hmac[hmac.length - 1]! & 0x0f;
  const truncated =
    ((hmac[offset]! & 0x7f) << 24) |
    ((hmac[offset + 1]! & 0xff) << 16) |
    ((hmac[offset + 2]! & 0xff) << 8) |
    (hmac[offset + 3]! & 0xff);

  return (truncated % 1_000_000).toString().padStart(6, '0');
}
