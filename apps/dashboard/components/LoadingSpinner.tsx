export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-kama-yellow rounded-full animate-spin"
           style={{ borderTopColor: '#f5a623' }} />
    </div>
  );
}
