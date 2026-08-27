'use client';

/**
 * Reading browser-only state without a setState-in-effect.
 *
 * A value that exists only on the client — `localStorage`, a class the
 * no-FOUC script already put on `<html>` — cannot be read during SSR. The
 * habit is to render a default, then correct it from `useEffect`. That
 * produces a guaranteed second render on every mount, and React 19's
 * `react-hooks/set-state-in-effect` rule rejects it.
 *
 * `useSyncExternalStore` is the sanctioned answer: it takes a server snapshot
 * and a client snapshot, so "this value does not exist on the server" is
 * expressed directly instead of being patched up afterwards. The dashboard
 * already uses the read-only form of this for the viewer's clock; this module
 * generalises it to values that are also *written*.
 *
 * The one rule `useSyncExternalStore` imposes: `getSnapshot` must return a
 * value that is `Object.is`-stable between renders, or React re-renders
 * forever. Every store here caches its snapshot in a module variable and only
 * replaces it inside a write, which is also what makes the write notify.
 */

import { useSyncExternalStore } from 'react';

type Listener = () => void;

/** A value owned by the browser, readable during SSR as a stated default. */
export interface ClientStore<T> {
  subscribe: (listener: Listener) => () => void;
  get: () => T;
  getServer: () => T;
  set: (value: T) => void;
}

/**
 * Build a store over a value only the browser can supply.
 *
 * @param read       Reads the live value. Called once, then cached until a write.
 * @param write      Persists a new value. Failures are swallowed: a browser
 *                   with storage disabled must still render, and a rejected
 *                   `localStorage` write is not worth a crash.
 * @param serverValue What SSR renders, before any browser value is known.
 */
export function createClientStore<T>(
  read: () => T,
  write: (value: T) => void,
  serverValue: T,
): ClientStore<T> {
  const listeners = new Set<Listener>();
  let snapshot: { value: T } | null = null;

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    get() {
      // Cached so the reference is stable across renders — the contract
      // `useSyncExternalStore` relies on to know nothing changed.
      snapshot ??= { value: read() };
      return snapshot.value;
    },
    getServer() {
      return serverValue;
    },
    set(value) {
      snapshot = { value };
      try {
        write(value);
      } catch {
        /* Storage unavailable (private mode, blocked cookies) — in-memory is enough. */
      }
      for (const listener of listeners) listener();
    },
  };
}

/** Subscribe a component to a {@link ClientStore}. */
export function useClientStore<T>(store: ClientStore<T>): T {
  return useSyncExternalStore(store.subscribe, store.get, store.getServer);
}

const subscribeToNothing = () => () => {};
const onClient = () => true;
const onServer = () => false;

/**
 * `false` during SSR and the hydrating render, `true` afterwards.
 *
 * For markup that must not differ between server and client on the first
 * paint — an icon whose choice depends on the stored theme, say.
 */
export function useHasHydrated(): boolean {
  return useSyncExternalStore(subscribeToNothing, onClient, onServer);
}
