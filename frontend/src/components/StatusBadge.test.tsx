import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';
import type { ApplicationStatus } from '@/types';

describe('StatusBadge', () => {
  it('renders the human-readable label for each status', () => {
    const cases: Array<{ status: ApplicationStatus; label: string }> = [
      { status: 'NOT_APPLIED', label: 'Not Applied' },
      { status: 'APPLIED', label: 'Applied' },
      { status: 'RECRUITER_INTERVIEW', label: 'Recruiter Interview' },
      { status: 'TECHNICAL_INTERVIEW', label: 'Technical Interview' },
      { status: 'OFFER_RECEIVED', label: 'Offer Received' },
      { status: 'OFFER_ACCEPTED', label: 'Offer Accepted' },
      { status: 'NOT_INTERESTED', label: 'Not Interested' },
    ];

    for (const { status, label } of cases) {
      const { unmount } = render(
        <StatusBadge status={status} />
      );
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it('renders nothing when status is undefined', () => {
    const { container } = render(<StatusBadge status={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it('applies the correct color classes for APPLIED', () => {
    render(<StatusBadge status="APPLIED" />);
    const badge = screen.getByText('Applied');
    expect(badge.className).toContain('bg-blue-100');
  });

  it('applies the correct color classes for OFFER_ACCEPTED', () => {
    render(<StatusBadge status="OFFER_ACCEPTED" />);
    const badge = screen.getByText('Offer Accepted');
    expect(badge.className).toContain('bg-green-100');
  });
});
