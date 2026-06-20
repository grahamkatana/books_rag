export default function CitationBadge({ index, onClick }) {
  return (
    <button
      onClick={onClick}
      title="View source"
      className="inline-flex items-center justify-center w-5 h-5 mx-0.5 -translate-y-0.5 rounded-full bg-accent text-accent-foreground text-[11px] font-medium align-super hover:bg-primary hover:text-primary-foreground transition-colors"
    >
      {index}
    </button>
  );
}
