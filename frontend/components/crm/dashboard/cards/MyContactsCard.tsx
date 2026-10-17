'use client';

import { BookUser, Plus } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import DashboardCardBody from '@/components/crm/dashboard/DashboardCardBody';
import DashboardListRow from '@/components/crm/dashboard/DashboardListRow';
import DashboardAvatar from '@/components/crm/dashboard/DashboardAvatar';
import { useOwnedCardList } from '@/features/crm/dashboard';
import { listContacts, type Contact } from '@/features/crm/contacts';

interface MyContactsCardProps {
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

export default function MyContactsCard({ isCustomizing, onRemove, dragHandleProps }: MyContactsCardProps) {
  const { status, items, error, fetchedAt, search, setSearch } = useOwnedCardList((params) =>
    listContacts({ owner_id: params.ownerId, search: params.search || undefined, page_size: 5 }),
  );

  return (
    <DashboardCard
      icon={BookUser}
      title="My Contacts"
      fetchedAt={fetchedAt}
      footerHref="/contacts"
      footerLabel="View all"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        <Link
          href="/contacts"
          aria-label="New contact"
          className="flex h-[26px] w-[26px] items-center justify-center rounded-lg transition hover:bg-[var(--surface-2)]"
          style={{ color: 'var(--muted)' }}
        >
          <Plus className="h-[14px] w-[14px]" />
        </Link>
      }
      toolbar={
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search this list…"
          className="input w-full py-1.5 text-[11.5px]"
        />
      }
    >
      <DashboardCardBody<Contact>
        status={status}
        items={items}
        error={error}
        emptyIcon={BookUser}
        emptyTitle={search ? 'No contacts match your search' : 'No contacts yet'}
        emptyDescription={
          search
            ? 'Try a different name.'
            : 'Add your first contact to start building relationships.'
        }
        renderRow={(contact) => (
          <DashboardListRow
            key={contact.id}
            href={`/contacts/${contact.id}`}
            leading={<DashboardAvatar label={contact.full_name} />}
            title={contact.full_name}
            subtitle={contact.job_title ?? contact.email ?? undefined}
          />
        )}
      />
    </DashboardCard>
  );
}
