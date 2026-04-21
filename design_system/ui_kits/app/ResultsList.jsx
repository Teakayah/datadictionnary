// ResultsList — a table of search results, selectable rows
const MOCK_TABLES = [
  {cat:'main', sch:'sales', name:'dim_customers', desc:'Consolidated customer profile data.', cols:42, fresh:'fresh', pii:true},
  {cat:'main', sch:'sales', name:'fct_orders', desc:'Granular order transaction records.', cols:18, fresh:'fresh'},
  {cat:'main', sch:'sales', name:'fct_order_items', desc:'Line-item grain of fct_orders.', cols:12, fresh:'fresh'},
  {cat:'main', sch:'marketing', name:'customer_ltv', desc:'Lifetime value model output, refreshed weekly.', cols:6, fresh:'2d', pii:true},
  {cat:'main', sch:'marketing', name:'campaign_touches', desc:'Multi-touch attribution feed from ad platforms.', cols:24, fresh:'fresh'},
  {cat:'main', sch:'finance', name:'dim_accounts', desc:'Chart of accounts and hierarchy.', cols:11, fresh:'fresh', locked:true},
];

function highlight(text, q){
  if(!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if(i<0) return text;
  return <>{text.slice(0,i)}<span style={{background:'#F3DFD9',color:'var(--accent-ink)',padding:'0 2px'}}>{text.slice(i,i+q.length)}</span>{text.slice(i+q.length)}</>;
}

function ResultsList({ query, selected, onSelect }) {
  const q = (query||'').trim().toLowerCase();
  const rows = q
    ? MOCK_TABLES.filter(r => (r.name+' '+r.desc+' '+r.sch).toLowerCase().includes(q))
    : MOCK_TABLES;
  return (
    <section>
      <header style={{display:'flex',alignItems:'baseline',justifyContent:'space-between',padding:'0 0 16px',borderBottom:'1px solid var(--ink)'}}>
        <div>
          <span className="eyebrow">Results</span>
          <span className="mono" style={{marginLeft:12,color:'var(--ink-40)',fontSize:12}}>{rows.length} tables · permission-trimmed</span>
        </div>
        <div style={{display:'flex',gap:10}}>
          <button className="btn sec" style={{padding:'6px 12px',fontSize:12}}><Icon name="filter" size={13}/> Filter</button>
          <button className="btn ghost" style={{fontSize:12,padding:'4px 6px'}}>Sort: relevance</button>
        </div>
      </header>
      {rows.map((r,i)=> (
        <div key={i} onClick={()=>onSelect(r)}
          style={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(140px, 1fr))',gap:20,padding:'16px 8px',borderTop: i===0?'none':'1px solid var(--ink-10)',cursor:'pointer',alignItems:'baseline',background: selected?.name===r.name?'var(--accent-wash)':'transparent',transition:'background 120ms var(--ease)'}}
          onMouseEnter={e=>{ if(selected?.name!==r.name) e.currentTarget.style.background='var(--paper-deep)';}}
          onMouseLeave={e=>{ if(selected?.name!==r.name) e.currentTarget.style.background='transparent';}}>
          <div className="mono" style={{fontSize:11,color:'var(--ink-40)'}}>{r.cat}.{r.sch}</div>
          <div>
            <div className="mono" style={{fontSize:14,fontWeight:500,color: selected?.name===r.name?'var(--accent-ink)':'var(--ink)'}}>{highlight(r.name, query)}</div>
            <div style={{fontSize:13,color:'var(--ink-60)',marginTop:3}}>{r.desc}</div>
          </div>
          <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
            {r.pii && <span className="tag" style={{border:'1px solid #BDCBD9',background:'#DDE4EC',color:'#2B4A6B',fontSize:10,padding:'2px 6px',fontFamily:'var(--font-mono)',borderRadius:2}}>PII</span>}
            <span className="tag" style={{border:'1px solid var(--ink-20)',color:'var(--ink-60)',fontSize:10,padding:'2px 6px',fontFamily:'var(--font-mono)',borderRadius:2}}>{r.cols} cols</span>
            {r.fresh!=='fresh' && <span className="tag" style={{border:'1px solid #E0CE9E',background:'#F0E5CC',color:'#7A5512',fontSize:10,padding:'2px 6px',fontFamily:'var(--font-mono)',borderRadius:2}}>stale {r.fresh}</span>}
          </div>
          <div style={{textAlign:'right'}}>
            {r.locked ? <span className="meta" style={{display:'inline-flex',alignItems:'center',gap:4,fontSize:11}}><Icon name="lock" size={12}/> no access</span>
            : <span className="meta" style={{fontSize:11,color:'var(--forest)',display:'inline-flex',alignItems:'center',gap:4}}><Icon name="check" size={12}/> granted</span>}
          </div>
        </div>
      ))}
      {rows.length===0 && (
        <div style={{padding:'64px 8px',borderTop:'1px solid var(--ink-10)',textAlign:'center'}}>
          <div className="h3" style={{fontSize:22,marginBottom:8}}>No matches for "{query}".</div>
          <p className="p" style={{margin:'0 auto',color:'var(--ink-60)'}}>Try a shorter term, or request access to a catalog you don't yet see.</p>
        </div>
      )}
    </section>
  );
}
window.ResultsList = ResultsList;
