// TableDetail — right panel / modal showing a single table
const MOCK_COLS = [
  {n:'customer_id', t:'STRING', pk:true, desc:'Surrogate key.'},
  {n:'first_name', t:'STRING', pii:true, desc:'Given name, as captured at signup.'},
  {n:'last_name', t:'STRING', pii:true, desc:'Family name.'},
  {n:'email', t:'STRING', pii:true, desc:'Primary email address.'},
  {n:'signup_date', t:'DATE', desc:'UTC date of first account creation.'},
  {n:'lifetime_value', t:'DECIMAL(18,2)', desc:'Sum of net order value.'},
  {n:'segment', t:'STRING', desc:'Marketing segment, refreshed weekly.'},
];

function TableDetail({ table, onClose }) {
  if(!table) return (
    <aside style={{padding:'48px 28px',borderLeft:'1px solid var(--ink-20)',minHeight:400}}>
      <div className="eyebrow" style={{marginBottom:12}}>Detail</div>
      <p className="p" style={{color:'var(--ink-60)'}}>Select a table to read its columns, grants, and lineage.</p>
    </aside>
  );
  return (
    <aside style={{padding:'24px 28px 48px',borderLeft:'1px solid var(--ink-20)',background:'var(--paper)'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:18}}>
        <div className="eyebrow">Catalog · {table.cat}.{table.sch}</div>
        <button onClick={onClose} className="btn ghost" style={{fontSize:12,padding:0,borderBottom:'1px solid var(--ink-20)'}}>Close</button>
      </div>
      <h2 className="h2" style={{fontFamily:'var(--font-mono)',fontSize:34,fontWeight:500,margin:'0 0 6px',letterSpacing:'-0.01em'}}>{table.name}</h2>
      <p className="p" style={{fontSize:15,margin:'0 0 18px',color:'var(--ink-80)'}}>{table.desc}</p>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:24}}>
        <button className="btn accent" style={{padding:'8px 14px',fontSize:13}}>Request access</button>
        <button className="btn sec" style={{padding:'8px 14px',fontSize:13,display:'inline-flex',alignItems:'center',gap:6}}><Icon name="copy" size={13}/> Copy identifier</button>
        <button className="btn ghost" style={{fontSize:13,display:'inline-flex',alignItems:'center',gap:6}}><Icon name="link" size={13}/> Open in Databricks</button>
      </div>

      <Section eyebrow="§ Columns" count={MOCK_COLS.length}>
        <table style={{width:'100%',borderCollapse:'collapse',fontSize:13}}>
          <tbody>
            {MOCK_COLS.map((c,i)=> (
              <tr key={i} style={{borderTop:'1px solid var(--ink-10)'}}>
                <td style={{padding:'8px 0',fontFamily:'var(--font-mono)',color:'var(--ink)'}}>
                  {c.pk && <span style={{color:'var(--accent)',marginRight:4}}>◆</span>}{c.n}
                </td>
                <td style={{padding:'8px 8px',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--ink-40)',whiteSpace:'nowrap'}}>{c.t}</td>
                <td style={{padding:'8px 0',color:'var(--ink-60)'}}>{c.desc}</td>
                <td style={{padding:'8px 0',textAlign:'right'}}>
                  {c.pii && <span style={{fontFamily:'var(--font-mono)',fontSize:10,padding:'2px 5px',border:'1px solid #BDCBD9',background:'#DDE4EC',color:'#2B4A6B',borderRadius:2}}>PII</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section eyebrow="§ Grants" count="3">
        <GrantRow who="group/finance_all"  what="SELECT"/>
        <GrantRow who="group/marketing_read" what="SELECT"/>
        <GrantRow who="group/data_steward" what="MODIFY"/>
      </Section>

      <Section eyebrow="§ Freshness">
        <div style={{display:'flex',gap:32,fontFamily:'var(--font-mono)',fontSize:12,color:'var(--ink-60)'}}>
          <div><div style={{color:'var(--ink)',fontSize:22,fontFamily:'var(--font-display)'}}>04:12</div>last sync UTC</div>
          <div><div style={{color:'var(--ink)',fontSize:22,fontFamily:'var(--font-display)'}}>nightly</div>cadence</div>
          <div><div style={{color:'var(--forest)',fontSize:22,fontFamily:'var(--font-display)'}}>fresh</div>status</div>
        </div>
      </Section>
    </aside>
  );
}

function Section({eyebrow, count, children}){
  return (
    <section style={{marginBottom:28}}>
      <header style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',padding:'0 0 10px',borderBottom:'1px solid var(--ink)'}}>
        <span className="eyebrow">{eyebrow}</span>
        {count!==undefined && <span className="mono" style={{fontSize:11,color:'var(--ink-40)'}}>{count}</span>}
      </header>
      <div style={{paddingTop:8}}>{children}</div>
    </section>
  );
}
function GrantRow({who, what}){
  return (
    <div style={{display:'flex',justifyContent:'space-between',padding:'8px 0',borderTop:'1px solid var(--ink-10)',fontFamily:'var(--font-mono)',fontSize:12}}>
      <span style={{color:'var(--ink)'}}>{who}</span>
      <span style={{color:'var(--ink-60)'}}>{what}</span>
    </div>
  );
}
window.TableDetail = TableDetail;
