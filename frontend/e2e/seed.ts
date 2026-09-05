/**
 * Seeding the tenant the end-to-end suite runs against.
 *
 * Everything here goes through the public API rather than SQL, for two
 * reasons. The obvious one is that the suite then works against any
 * environment that accepts a signup, with no database credentials. The less
 * obvious one matters more: seeding through SQL would let the tests pass while
 * the real signup and provisioning paths were broken, which is precisely the
 * class of failure an end-to-end suite exists to catch.
 */

export interface SeededPerson {
  email: string;
  password: string;
  fullName: string;
}

export interface SeedResult {
  organizationName: string;
  admin: SeededPerson;
  /** Holds the Manager role: VIEW_ALL across the CRM. */
  manager: SeededPerson;
  /** Holds the User role: sees only records they own. */
  rep: SeededPerson;
  /** Owned by the manager, so the rep must not see it in a list or a total. */
  managerAccountName: string;
  managerDealName: string;
  managerDealValue: string;
}

/** Meets the default policy: 12+ characters, mixed case, a digit. */
export const E2E_PASSWORD = 'E2ePassphrase!7';

const API_URL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8100';
const PREFIX = process.env.E2E_API_PREFIX ?? '/api/v1';

/** A run-scoped suffix, so repeated runs never collide on a unique index. */
export const RUN_ID = Math.random().toString(36).slice(2, 8);

class ApiError extends Error {
  constructor(method: string, path: string, status: number, body: string) {
    super(`${method} ${path} → ${status}\n${body}`);
    this.name = 'ApiError';
  }
}

/** A thin API client that fails loudly — a silent seed failure is a mystery later. */
export class SeedClient {
  private token: string | null = null;

  async request<T>(
    method: 'GET' | 'POST',
    path: string,
    body?: unknown,
  ): Promise<T> {
    const response = await fetch(`${API_URL}${PREFIX}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!response.ok) {
      throw new ApiError(method, path, response.status, await response.text());
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async signup(person: SeededPerson): Promise<void> {
    const [first, ...rest] = person.fullName.split(' ');
    const { access_token } = await this.request<{ access_token: string }>(
      'POST',
      '/auth/signup',
      {
        email: person.email,
        password: person.password,
        first_name: first,
        last_name: rest.join(' ') || 'Tester',
      },
    );
    this.token = access_token;
  }

  async login(person: SeededPerson): Promise<void> {
    const { access_token } = await this.request<{ access_token: string }>(
      'POST',
      '/auth/login',
      { email: person.email, password: person.password },
    );
    this.token = access_token;
  }
}

function person(role: string, name: string): SeededPerson {
  return {
    email: `e2e-${role}-${RUN_ID}@example.com`,
    password: E2E_PASSWORD,
    fullName: name,
  };
}

/**
 * Create an organization with three people, one account and one deal.
 *
 * The deal is owned by the manager and is what the visibility test asserts on:
 * the manager must see it, the rep must not.
 */
export async function seedTenant(): Promise<SeedResult> {
  const admin = person('admin', 'Ada Admin');
  const manager = person('manager', 'Morgan Manager');
  const rep = person('rep', 'Rory Rep');

  const organizationName = `E2E Industries ${RUN_ID}`;
  const managerAccountName = `Northwind ${RUN_ID}`;
  const managerDealName = `Managed renewal ${RUN_ID}`;
  const managerDealValue = '75000.00';

  const api = new SeedClient();
  await api.signup(admin);
  await api.request('POST', '/organizations', {
    name: organizationName,
    app_codes: ['s3k-crm'],
  });
  // The signup token names no organization — by design, since the caller had
  // none when it was issued. Everything below is tenant-scoped, so a fresh
  // token that resolves the organization just created is required first.
  await api.login(admin);

  // Role ids are per organization, so they have to be read back rather than
  // guessed. Names come from `authorization/catalog.SYSTEM_ROLES`.
  const roles = await api.request<{ id: string; name: string }[]>('GET', '/roles');
  const roleId = (name: string): string => {
    const match = roles.find(role => role.name === name);
    if (!match) throw new Error(`Seed expected a '${name}' role; got ${roles.map(r => r.name).join(', ')}`);
    return match.id;
  };

  await api.request('POST', '/organizations/current/users', {
    email: manager.email,
    first_name: 'Morgan',
    last_name: 'Manager',
    password: manager.password,
    role_id: roleId('Manager'),
  });
  await api.request('POST', '/organizations/current/users', {
    email: rep.email,
    first_name: 'Rory',
    last_name: 'Rep',
    password: rep.password,
    role_id: roleId('User'),
  });

  // Created *as the manager* so the records are owned by them — ownership is
  // what the rep's visibility narrows against, and an admin-owned record would
  // make the assertion meaningless.
  const asManager = new SeedClient();
  await asManager.login(manager);

  const account = await asManager.request<{ id: string }>('POST', '/crm/accounts', {
    name: managerAccountName,
  });
  const stages = await asManager.request<{ id: string; name: string }[]>(
    'GET',
    '/crm/opportunities/stages',
  );
  const qualification = stages.find(stage => stage.name === 'Qualification') ?? stages[0];

  await asManager.request('POST', '/crm/opportunities', {
    name: managerDealName,
    account_id: account.id,
    stage_id: qualification.id,
    deal_value: managerDealValue,
  });

  return {
    organizationName,
    admin,
    manager,
    rep,
    managerAccountName,
    managerDealName,
    managerDealValue,
  };
}
