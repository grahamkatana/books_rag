import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Label } from "./ui/Label";
import { Checkbox } from "./ui/Checkbox";

export default function BookEditDialog({ open, onOpenChange, book, onSubmit, isSubmitting, error }) {
  const [fields, setFields] = useState({});

  useEffect(() => {
    if (open && book) {
      setFields({
        title: book.title || "",
        authors: book.authors || "",
        year: book.year ?? "",
        publisher: book.publisher || "",
        edition: book.edition || "",
        is_editor: book.is_editor || false,
        work_key: book.work_key || "",
        is_preferred_edition: book.is_preferred_edition || false,
        edition_pinned: book.edition_pinned || false,
      });
    }
  }, [open, book]);

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));
  const setBool = (key) => (checked) => setFields((f) => ({ ...f, [key]: checked }));

  const submit = (e) => {
    e.preventDefault();
    onSubmit({
      ...fields,
      year: fields.year === "" ? null : Number(fields.year),
      authors: fields.authors || null,
      publisher: fields.publisher || null,
      edition: fields.edition || null,
      work_key: fields.work_key || null,
    });
  };

  if (!book) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Edit book</DialogTitle>
            <DialogDescription>
              {book.source_key} -- saving marks this verified and tags it as manually corrected.
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
            <div className="space-y-1.5">
              <Label>Authors</Label>
              <Input value={fields.authors || ""} onChange={set("authors")} placeholder="Surname, F." />
            </div>
            <div className="space-y-1.5">
              <Label>Year</Label>
              <Input type="number" value={fields.year ?? ""} onChange={set("year")} />
            </div>
            <div className="space-y-1.5">
              <Label>Publisher</Label>
              <Input value={fields.publisher || ""} onChange={set("publisher")} />
            </div>
            <div className="space-y-1.5">
              <Label>Edition</Label>
              <Input value={fields.edition || ""} onChange={set("edition")} placeholder="e.g. 9th ed." />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label>Work key (groups editions of the same book)</Label>
              <Input value={fields.work_key || ""} onChange={set("work_key")} placeholder="e.g. sommerville-software-engineering" />
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <Checkbox checked={fields.is_editor || false} onCheckedChange={setBool("is_editor")} />
              <span className="text-sm text-foreground">Is editor (not author)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <Checkbox checked={fields.is_preferred_edition || false} onCheckedChange={setBool("is_preferred_edition")} />
              <span className="text-sm text-foreground">Preferred edition</span>
            </label>
            <label className="col-span-2 flex items-center gap-2 cursor-pointer">
              <Checkbox checked={fields.edition_pinned || false} onCheckedChange={setBool("edition_pinned")} />
              <span className="text-sm text-foreground">
                Pin this edition (overrides automatic year-based preference)
              </span>
            </label>
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
