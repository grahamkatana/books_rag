import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Label } from "./ui/Label";

export default function PaperEditDialog({ open, onOpenChange, paper, onSubmit, isSubmitting, error }) {
  const [fields, setFields] = useState({});

  useEffect(() => {
    if (open && paper) {
      setFields({
        title: paper.title || "",
        authors: paper.authors || "",
        year: paper.year ?? "",
        venue: paper.venue || "",
        doi: paper.doi || "",
        abstract: paper.abstract || "",
      });
    }
  }, [open, paper]);

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    onSubmit({
      ...fields,
      year: fields.year === "" ? null : Number(fields.year),
      authors: fields.authors || null,
      venue: fields.venue || null,
      doi: fields.doi || null,
      abstract: fields.abstract || null,
    });
  };

  if (!paper) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Edit paper</DialogTitle>
            <DialogDescription>
              {paper.source_key} -- saving marks this verified and tags it as manually corrected.
            </DialogDescription>
          </DialogHeader>

          {error && (
            <p className="mb-4 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{error}</p>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 space-y-1.5">
              <Label>Title</Label>
              <Input value={fields.title || ""} onChange={set("title")} required />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label>Authors</Label>
              <Input
                value={fields.authors || ""}
                onChange={set("authors")}
                placeholder="Surname, F.; Surname2, F2."
              />
            </div>
            <div className="space-y-1.5">
              <Label>Year</Label>
              <Input type="number" value={fields.year ?? ""} onChange={set("year")} />
            </div>
            <div className="space-y-1.5">
              <Label>Venue</Label>
              <Input value={fields.venue || ""} onChange={set("venue")} placeholder="e.g. ICSE 2026" />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label>DOI</Label>
              <Input value={fields.doi || ""} onChange={set("doi")} placeholder="10.1145/xxxxxxx.xxxxxxx" />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label>Abstract</Label>
              <textarea
                value={fields.abstract || ""}
                onChange={(e) => setFields((f) => ({ ...f, abstract: e.target.value }))}
                rows={4}
                className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Saving..." : "Save changes"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
