export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="muted">{label}</div>;
}

export function ErrorState({ error }: { error: unknown }) {
  const message =
    (error as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ??
    (error as Error)?.message ??
    "Something went wrong.";
  return (
    <div className="card" style={{ borderColor: "#e8590c" }}>
      <strong style={{ color: "#c92a2a" }}>Error:</strong> {message}
    </div>
  );
}
