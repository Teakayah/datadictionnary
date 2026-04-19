// Support — internal resources, no sales
function SupportFooter() {
  const cols = [
    ['Docs',['Install guide','Search syntax','Grants & access','Changelog']],
    ['Support',['#data-platform on Slack','File a ticket','On-call rotation','FAQ']],
    ['Governance',['Data access policy','PII handling','Security review','Audit log']],
  ];
  return (
    <footer style={{background:'var(--paper)',padding:'80px 48px 32px',borderTop:'1px solid var(--ink-20)'}}>
      <div style={{maxWidth:1200,margin:'0 auto',display:'grid',gridTemplateColumns:'1.4fr 1fr 1fr 1fr',gap:48}}>
        <div id="support">
          <img src="../../assets/logo-wordmark.svg" alt="Data Dictionary" style={{height:44,marginBottom:14}}/>
          <p className="p-small" style={{maxWidth:'36ch'}}>An internal tool built by the data platform team. Questions? Reach us on <a href="#">#data-platform</a>.</p>
        </div>
        {cols.map(([h,items])=> (
          <div key={h} id={h==='Docs'?'docs':undefined}>
            <div className="eyebrow" style={{marginBottom:14}}>{h}</div>
            <ul style={{listStyle:'none',padding:0,margin:0,display:'flex',flexDirection:'column',gap:8}}>
              {items.map(it=> <li key={it}><a href="#" style={{fontSize:14,color:'var(--ink-80)',textDecoration:'none'}}>{it}</a></li>)}
            </ul>
          </div>
        ))}
      </div>
      <div style={{maxWidth:1200,margin:'40px auto 0',paddingTop:20,borderTop:'1px solid var(--ink-10)',display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--ink-40)',flexWrap:'wrap',gap:12}}>
        <span>Internal use only · data platform team</span>
        <span>v0.3.0 · synced 04:12 UTC · main.data_governance.dictionary_cache</span>
      </div>
    </footer>
  );
}
window.SupportFooter = SupportFooter;
