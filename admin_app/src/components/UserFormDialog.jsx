import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Label } from "./ui/Label";
import { Checkbox } from "./ui/Checkbox";

export default function UserFormDialog({ open, onOpenChange, mode, initialUser, onSubmit, isSubmitting, error }) {
  const isEdit = mode === "edit";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    if (open) {
      setEmail(initialUser?.email || "");
      setPassword("");
      setIsAdmin(initialUser?.is_admin || false);
    }
  }, [open, initialUser]);

  const submit = (e) => {
    e.preventDefault();
    const fields = { email, is_admin: isAdmin };
    if (password) fields.password = password; // omit entirely when blank, esp. important on edit
    onSubmit(fields);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit user" : "Register a new user"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Leave the password blank to keep it unchanged."
                : "They'll be able to log in immediately with this email and password."}
            </DialogDescription>
          </DialogHeader>

          {error && (
            <p className="mb-4 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{error}</p>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="form-email">Email</Label>
              <Input
                id="form-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="form-password">
                Password {isEdit && <span className="text-muted-foreground">(optional)</span>}
              </Label>
              <Input
                id="form-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isEdit ? "Leave blank to keep unchanged" : ""}
                required={!isEdit}
                minLength={8}
              />
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <Checkbox checked={isAdmin} onCheckedChange={setIsAdmin} />
              <span className="text-sm text-foreground">Admin access</span>
            </label>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving..." : isEdit ? "Save changes" : "Create user"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
