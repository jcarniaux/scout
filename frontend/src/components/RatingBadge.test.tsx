import { render, screen } from '@testing-library/react';
import { RatingBadge } from './RatingBadge';

describe('RatingBadge', () => {
  it('displays the rating formatted to one decimal', () => {
    render(<RatingBadge rating={4.2} />);
    expect(screen.getByText('4.2')).toBeInTheDocument();
  });

  it('displays N/A when rating is null', () => {
    render(<RatingBadge rating={null} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('displays N/A when rating is undefined', () => {
    render(<RatingBadge rating={undefined} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('links to Glassdoor when URL and rating are provided', () => {
    render(<RatingBadge rating={4.5} glassdoorUrl="https://glassdoor.com/acme" />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://glassdoor.com/acme');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not link when rating is null even with URL', () => {
    render(<RatingBadge rating={null} glassdoorUrl="https://glassdoor.com/acme" />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('does not link when URL is absent', () => {
    render(<RatingBadge rating={4.0} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('uses green background for high ratings', () => {
    const { container } = render(<RatingBadge rating={4.5} />);
    const badge = container.querySelector('.bg-green-50');
    expect(badge).toBeInTheDocument();
  });

  it('uses yellow background for mid ratings', () => {
    const { container } = render(<RatingBadge rating={3.5} />);
    const badge = container.querySelector('.bg-yellow-50');
    expect(badge).toBeInTheDocument();
  });

  it('uses red background for low ratings', () => {
    const { container } = render(<RatingBadge rating={2.5} />);
    const badge = container.querySelector('.bg-red-50');
    expect(badge).toBeInTheDocument();
  });
});
