import { useCallback, useEffect, useState } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import { fetchUsage, fetchPrices, savePrice, fetchBalances, saveCredit, UnauthorizedError } from "../api/client";

const usd = (n) => (n == null ? "—" : `$${n.toFixed(n < 1 ? 4 : 2)}`);
const num = (n) => n.toLocaleString();

function Card({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-display text-2xl font-semibold text-foreground">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

export default function UsagePage({ onSessionExpired }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [prices, setPrices] = useState([]);
  const [bal, setBal] = useState(null);
  const [error, setError] = useState(null);
  const [price, setPrice] = useState({ provider: "", model: "", input_per_million: "", output_per_million: "" });
  const [credit, setCredit] = useState({ provider: "openai", amount: "" });

  const fail = useCallback((err) => (err instanceof UnauthorizedError ? onSessionExpired() : setError(err.message)), [onSessionExpired]);
  const load = useCallback(async () => {
    setError(null);
    try {
      const [u, p, b] = await Promise.all([fetchUsage(days), fetchPrices(), fetchBalances()]);
      setData(u); setPrices(p); setBal(b);
    } catch (err) { fail(err); }
  }, [days, fail]);
  useEffect(() => { load(); }, [load]);

  const submitPrice = async (e) => {
    e.preventDefault();
    try {
      await savePrice({ ...price, input_per_million: Number(price.input_per_million), output_per_million: Number(price.output_per_million) });
      setPrice({ provider: "", model: "", input_per_million: "", output_per_million: "" });
      load();
    } catch (err) { fail(err); }
  };
  const submitCredit = async (e) => {
    e.preventDefault();
    try { await saveCredit(credit.provider, Number(credit.amount)); setCredit({ ...credit, amount: "" }); load(); } catch (err) { fail(err); }
  };

  if (!data) return <div className="flex flex-1 items-center justify-center text-muted-foreground">{error ? error : <Loader2 className="h-5 w-5 animate-spin" />}</div>;
  const peak = Math.max(...data.by_day.map((d) => d.cost_usd), 0.000001);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="font-display text-xl font-semibold">Usage and cost</h1>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-md border border-border bg-background px-2 py-1 text-sm">
            {[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}
          </select>
        </div>
        {error && <div className="flex items-center gap-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{error}</div>}

        <div className="grid gap-3 sm:grid-cols-3">
          <Card label="This month so far" value={usd(data.month_to_date_usd)} hint="Priced models only" />
          <Card label="Projected for the month" value={usd(data.projected_month_usd)} hint="Current daily average carried to month end" />
          <Card label={`Last ${days} days`} value={usd(data.by_day.reduce((a, d) => a + d.cost_usd, 0))} />
        </div>
        {data.unpriced.length > 0 && (
          <p className="text-sm text-muted-foreground">No price set for: {data.unpriced.join(", ")}. Their tokens are counted but cost shows as $0 until you add a price below. Plan-based providers can stay at $0.</p>
        )}

        <section>
          <h2 className="mb-2 text-sm font-semibold">Cost per day</h2>
          <div className="flex h-28 items-end gap-1">
            {data.by_day.length === 0 && <span className="text-sm text-muted-foreground">No priced usage yet.</span>}
            {data.by_day.map((d) => <div key={d.day} title={`${d.day}: ${usd(d.cost_usd)}`} style={{ height: `${Math.max(4, (d.cost_usd / peak) * 100)}%` }} className="flex-1 rounded-t bg-primary/80" />)}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-semibold">By model</h2>
          <Table>
            <TableHeader><TableRow><TableHead>Provider / model</TableHead><TableHead>Use</TableHead><TableHead>Calls</TableHead><TableHead>Tokens in</TableHead><TableHead>Tokens out</TableHead><TableHead>Cost</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.by_model.map((m) => (
                <TableRow key={`${m.provider}${m.model}${m.kind}`}>
                  <TableCell>{m.provider} / {m.model}</TableCell><TableCell>{m.kind}</TableCell><TableCell>{num(m.calls)}</TableCell>
                  <TableCell>{num(m.input_tokens)}{m.estimated ? " ~" : ""}</TableCell><TableCell>{num(m.output_tokens)}</TableCell>
                  <TableCell>{m.priced ? usd(m.cost_usd) : "no price"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-1 text-xs text-muted-foreground">~ means some counts were estimated at four characters a token because the provider did not report them.</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Balances</h2>
          {bal?.checked.map((b, i) => (
            <div key={i} className="rounded-md border border-border p-3 text-sm">
              <b>{b.provider}</b>{" "}
              {b.kind === "balance" && b.balances.map((x) => <span key={x.currency}>{x.total_balance} {x.currency} available{b.available === false ? " (account says unavailable)" : ""}</span>)}
              {b.kind === "month_spend" && <span>spent {usd(b.month_to_date_usd)} this month (OpenAI reports spend, not credit left)</span>}
              {b.kind === "error" && <span className="text-destructive">check failed: {b.error}</span>}
              {(b.kind === "unsupported" || b.kind === "unsupported_balance") && <span className="text-muted-foreground">{b.note}</span>}
            </div>
          ))}
          {bal?.estimated_from_top_up.map((e) => (
            <div key={e.provider} className="rounded-md border border-border p-3 text-sm">
              <b>{e.provider}</b> estimated left {usd(e.estimated_left_usd)} (you entered {usd(e.entered_usd)} on {new Date(e.as_of).toLocaleDateString()}, spent since {usd(e.spent_since_usd)})
            </div>
          ))}
          <form onSubmit={submitCredit} className="flex flex-wrap items-end gap-2">
            <Input placeholder="provider" value={credit.provider} onChange={(e) => setCredit({ ...credit, provider: e.target.value })} className="w-32" />
            <Input placeholder="credit left, USD" type="number" step="0.01" min="0" value={credit.amount} onChange={(e) => setCredit({ ...credit, amount: e.target.value })} className="w-40" />
            <Button type="submit" disabled={!credit.provider || credit.amount === ""}>Set credit</Button>
          </form>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Prices (USD per million tokens)</h2>
          <Table>
            <TableHeader><TableRow><TableHead>Provider / model</TableHead><TableHead>In</TableHead><TableHead>Out</TableHead><TableHead>Note</TableHead></TableRow></TableHeader>
            <TableBody>
              {prices.map((p) => (
                <TableRow key={p.provider + p.model} onClick={() => setPrice({ provider: p.provider, model: p.model, input_per_million: p.input_per_million, output_per_million: p.output_per_million })} className="cursor-pointer">
                  <TableCell>{p.provider} / {p.model}</TableCell><TableCell>{p.input_per_million}</TableCell><TableCell>{p.output_per_million}</TableCell><TableCell>{p.note}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <form onSubmit={submitPrice} className="flex flex-wrap items-end gap-2">
            <Input placeholder="provider" value={price.provider} onChange={(e) => setPrice({ ...price, provider: e.target.value })} className="w-28" />
            <Input placeholder="model" value={price.model} onChange={(e) => setPrice({ ...price, model: e.target.value })} className="w-48" />
            <Input placeholder="in" type="number" step="any" min="0" value={price.input_per_million} onChange={(e) => setPrice({ ...price, input_per_million: e.target.value })} className="w-24" />
            <Input placeholder="out" type="number" step="any" min="0" value={price.output_per_million} onChange={(e) => setPrice({ ...price, output_per_million: e.target.value })} className="w-24" />
            <Button type="submit" disabled={!price.provider || !price.model || price.input_per_million === "" || price.output_per_million === ""}>Save price</Button>
          </form>
          <p className="text-xs text-muted-foreground">Copy prices from each provider's pricing page; they change. Click a row to edit it.</p>
        </section>
      </div>
    </div>
  );
}
