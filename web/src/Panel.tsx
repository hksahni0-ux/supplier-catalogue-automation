import type { Panel as PanelData } from "./api";
import { money } from "./money";

export function Panel({ data }: { data: PanelData | null }) {
  if (!data) return <aside className="panel muted">Loading products…</aside>;
  return (
    <aside className="panel" aria-label="Products">
      <h2>Products</h2>
      {data.products.map((p) => (
        <article key={p.sku} className="product">
          <div className="product-head">
            <h3>{p.name}</h3>
            {p.needs_review > 0 && <span className="pill warn">{p.needs_review} to check</span>}
          </div>
          <p className="mono muted">{p.sku}</p>
          <p className="price">{money(p.base_price, p.currency)}</p>
          <p className="muted">
            {p.price_rows != null && `${p.price_rows.toLocaleString("en-GB")} price rows`}
          </p>
          <p className="muted small">{p.last_run ? `Last run ${p.last_run}` : "Not run yet"}</p>
          {p.drive && (
            <a href={p.drive} target="_blank" rel="noreferrer" aria-label={`${p.name} in Drive`}>Open in Drive</a>
          )}
        </article>
      ))}
      <h2>Needs a person</h2>
      {data.review.items.length === 0 ? (
        <p className="muted">Nothing to check.</p>
      ) : (
        <ul className="review">
          {data.review.items.map((item, i) => (
            <li key={i} className={item.severity}>
              <b>{item.product}</b> <span className="muted">· {item.about}</span>
              <p>{item.message}</p>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
