import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Download, Upload, Trash2, Smartphone, Loader2 } from "lucide-react";
import { Button } from "./ui/Button";
import { fetchReleases, uploadRelease, deleteRelease, downloadRelease, UnauthorizedError } from "../api/client";

const formatBytes = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`);
// The API stores UTC without a zone marker.
const formatDate = (iso) => (iso ? new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "");

const inputClass = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function ReleasesPage({ user, onBack, onSessionExpired }) {
  const [releases, setReleases] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [publishing, setPublishing] = useState(false);

  const handleError = useCallback((err) => {
    if (err instanceof UnauthorizedError) onSessionExpired();
    else setError(err.message);
  }, [onSessionExpired]);

  const load = useCallback(async () => {
    setError(null);
    try {
      setReleases(await fetchReleases());
    } catch (err) {
      handleError(err);
    } finally {
      setIsLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    load();
  }, [load]);

  const download = async (release) => {
    setBusyId(release.id);
    setError(null);
    try {
      await downloadRelease(release.id);
    } catch (err) {
      handleError(err);
    } finally {
      setTimeout(() => setBusyId(null), 1500);
    }
  };

  const remove = async (release) => {
    if (!window.confirm(`Delete version ${release.version_name}? It can no longer be downloaded. Phones that already have it keep working.`)) return;
    try {
      await deleteRelease(release.id);
      await load();
    } catch (err) {
      handleError(err);
    }
  };

  const latest = releases.find((r) => r.is_latest);
  const earlier = releases.filter((r) => !r.is_latest);

  return (
    <div className="thin-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-5 p-4 md:p-6">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to chat
        </button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-foreground">Android app</h1>
            <p className="text-sm text-muted-foreground">Ask the library and verify drafts from your phone. Open this page on the phone to download it directly.</p>
          </div>
          {user?.is_admin && !publishing && (
            <Button onClick={() => setPublishing(true)} className="shrink-0 gap-1.5">
              <Upload className="h-3.5 w-3.5" /> Publish a version
            </Button>
          )}
        </div>

        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        {publishing && (
          <PublishForm
            nextCode={(releases[0]?.version_code ?? 0) + 1}
            onCancel={() => setPublishing(false)}
            onPublished={async () => { setPublishing(false); await load(); }}
            onSessionExpired={onSessionExpired}
          />
        )}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : !latest ? (
          <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
            <Smartphone className="mx-auto h-8 w-8 text-muted-foreground/60" />
            <p className="mt-3 text-sm font-medium text-foreground">No Android app has been published yet</p>
            <p className="mt-1 text-sm text-muted-foreground">{user?.is_admin ? "Use “Publish a version” to upload the first APK." : "Ask an administrator to publish it."}</p>
          </div>
        ) : (
          <>
            <section className="rounded-xl border border-border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-semibold text-foreground">Version {latest.version_name}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">Latest · {formatBytes(latest.size_bytes)} · published {formatDate(latest.created_at)}</p>
                </div>
                <Button onClick={() => download(latest)} disabled={busyId === latest.id} className="gap-2">
                  {busyId === latest.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Download APK
                </Button>
              </div>
              {latest.notes && <p className="mt-4 whitespace-pre-wrap text-sm text-foreground">{latest.notes}</p>}
              <div className="mt-4 border-t border-border pt-3">
                <p className="text-xs text-muted-foreground">SHA-256, to check the file you received is the one published:</p>
                <code className="mt-1 block break-all font-mono text-xs text-foreground/80">{latest.sha256}</code>
              </div>
              {user?.is_admin && (
                <button className="mt-3 text-xs text-red-700 hover:underline" onClick={() => remove(latest)}>Delete version {latest.version_name}</button>
              )}
            </section>

            <section className="rounded-xl border border-border bg-card p-5">
              <h2 className="text-sm font-semibold text-foreground">How to install</h2>
              <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
                <li>On your phone, open this page and tap <span className="text-foreground">Download APK</span>.</li>
                <li>Open the downloaded file. If Android asks, allow your browser to <span className="text-foreground">install unknown apps</span>, then go back and tap <span className="text-foreground">Install</span>.</li>
                <li>If Play Protect warns about an unknown developer, choose <span className="text-foreground">Install anyway</span>. The app is signed by its author rather than the Play Store.</li>
                <li>Open Book RAG and log in with the same email and password as here.</li>
              </ol>
              <p className="mt-3 text-xs text-muted-foreground">Updating? Install the newer file over the old one; you stay logged in.</p>
            </section>

            {earlier.length > 0 && (
              <section>
                <h2 className="mb-2 text-sm font-semibold text-foreground">Earlier versions</h2>
                <ul className="divide-y divide-border rounded-xl border border-border bg-card">
                  {earlier.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground">{r.version_name} <span className="font-normal text-muted-foreground">· {formatBytes(r.size_bytes)} · {formatDate(r.created_at)}</span></p>
                        {r.notes && <p className="mt-0.5 truncate text-xs text-muted-foreground" title={r.notes}>{r.notes}</p>}
                      </div>
                      <button title={`Download ${r.version_name}`} disabled={busyId === r.id} onClick={() => download(r)} className="shrink-0 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                        <Download className="h-4 w-4" />
                      </button>
                      {user?.is_admin && (
                        <button title="Delete this version" onClick={() => remove(r)} className="shrink-0 rounded-md p-2 text-red-700 hover:bg-red-50">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function PublishForm({ nextCode, onCancel, onPublished, onSessionExpired }) {
  const [file, setFile] = useState(null);
  const [versionName, setVersionName] = useState("");
  const [versionCode, setVersionCode] = useState(String(nextCode));
  const [notes, setNotes] = useState("");
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const fileInput = useRef(null);

  const pick = (picked) => {
    setFile(picked);
    // book-rag-0.2.0.apk -> 0.2.0 (only a suggestion; it can be edited)
    const guess = picked?.name.match(/(\d+(?:\.\d+)+[0-9A-Za-z.+-]*)\.apk$/i)?.[1];
    if (guess && !versionName) setVersionName(guess);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await uploadRelease({ file, versionName: versionName.trim(), versionCode, notes });
      await onPublished();
    } catch (err) {
      if (err instanceof UnauthorizedError) return onSessionExpired();
      setError(err.message);
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-border bg-card p-5">
      <div>
        <h2 className="text-sm font-semibold text-foreground">Publish a version</h2>
        <p className="mt-1 text-xs text-muted-foreground">Earlier versions are kept. Every version needs a higher version code than the last: Android uses it to tell which is newer.</p>
      </div>
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <input ref={fileInput} type="file" accept=".apk,application/vnd.android.package-archive" className="hidden" onChange={(e) => pick(e.target.files?.[0] || null)} />
      <button type="button" onClick={() => fileInput.current?.click()} className="flex w-full items-center gap-3 rounded-lg border border-dashed border-border px-4 py-3 text-left hover:bg-accent/40">
        <Smartphone className="h-5 w-5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 break-all text-sm">{file ? <span className="font-medium text-foreground">{file.name} <span className="font-normal text-muted-foreground">({formatBytes(file.size)})</span></span> : <span className="text-muted-foreground">Choose the .apk file…</span>}</span>
      </button>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1.5 text-sm font-medium text-foreground">
          Version name
          <input className={inputClass} value={versionName} onChange={(e) => setVersionName(e.target.value)} placeholder="0.2.0" required />
        </label>
        <label className="space-y-1.5 text-sm font-medium text-foreground">
          Version code
          <input className={inputClass} type="number" min={1} value={versionCode} onChange={(e) => setVersionCode(e.target.value)} required />
        </label>
      </div>
      <label className="block space-y-1.5 text-sm font-medium text-foreground">
        What's new <span className="font-normal text-muted-foreground">(optional)</span>
        <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} className={`${inputClass} resize-y font-normal`} />
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
        <Button type="submit" disabled={!file || !versionName.trim() || !versionCode || isSaving}>
          {isSaving ? <><Loader2 className="h-4 w-4 animate-spin" /> Publishing…</> : "Publish"}
        </Button>
      </div>
    </form>
  );
}
