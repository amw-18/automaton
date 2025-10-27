interface StatusBadgeProps {
  status: string;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const statusConfig: Record<string, { label: string; className: string }> = {
    created: { label: 'Created', className: 'bg-gray-100 text-gray-800' },
    uploaded: { label: 'Uploaded', className: 'bg-blue-100 text-blue-800' },
    processing: { label: 'Processing', className: 'bg-yellow-100 text-yellow-800' },
    processed: { label: 'Ready', className: 'bg-green-100 text-green-800' },
    running: { label: 'Running', className: 'bg-purple-100 text-purple-800' },
    complete: { label: 'Complete', className: 'bg-green-100 text-green-800' },
    testing: { label: 'Testing', className: 'bg-orange-100 text-orange-800' },
    test_complete: { label: 'Test Complete', className: 'bg-green-100 text-green-800' },
    test_failed: { label: 'Test Failed', className: 'bg-red-100 text-red-800' },
    error: { label: 'Error', className: 'bg-red-100 text-red-800' },
  };

  const config = statusConfig[status] || statusConfig.created;

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  );
}
