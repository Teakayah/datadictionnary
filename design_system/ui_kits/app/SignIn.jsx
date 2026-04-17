// SignIn — Entra ID mock sign-in screen
function SignIn({ onSignIn }) {
  return (
    <div style={{display:'grid',gridTemplateColumns:'1.1fr .9fr',gap:64,alignItems:'center',minHeight:'calc(100vh - 200px)'}}>
      <div>
        <div className="eyebrow" style={{marginBottom:24}}>§ Business Data Dictionary</div>
        <h1 className="h1" style={{margin:'0 0 24px'}}>A card catalog<br/>for your warehouse.</h1>
        <p className="p-lead" style={{maxWidth:'46ch'}}>Search tables, columns, and business terms across Unity Catalog — filtered to what you have permission to see.</p>
        <hr className="rule"/>
        <div style={{display:'flex',gap:48}}>
          <Stat n="2,341" l="tables indexed"/>
          <Stat n="18" l="schemas"/>
          <Stat n="04:12" l="last synced UTC"/>
        </div>
      </div>
      <aside style={{borderTop:'1px solid var(--ink)', paddingTop:32}}>
        <div className="eyebrow" style={{marginBottom:16}}>Sign in</div>
        <h3 className="h3" style={{margin:'0 0 14px'}}>Use your corporate account</h3>
        <p className="p" style={{fontSize:15,marginBottom:28}}>The catalog is permission-trimmed by Microsoft Entra ID — you'll only see data your Unity Catalog grants allow.</p>
        <button onClick={onSignIn} className="btn" style={{width:'100%',padding:'14px 18px',fontSize:15,display:'flex',alignItems:'center',justifyContent:'center',gap:10}}>
          <svg width="16" height="16" viewBox="0 0 23 23" fill="none"><rect x="1" y="1" width="10" height="10" fill="#F25022"/><rect x="12" y="1" width="10" height="10" fill="#7FBA00"/><rect x="1" y="12" width="10" height="10" fill="#00A4EF"/><rect x="12" y="12" width="10" height="10" fill="#FFB900"/></svg>
          Sign in with Entra ID
        </button>
        <p className="meta" style={{marginTop:14,fontSize:12}}>By signing in you agree to the data access policy.</p>
      </aside>
    </div>
  );
}
function Stat({n,l}){
  return (<div>
    <div style={{fontFamily:'var(--font-display)', fontSize:40, fontWeight:500, lineHeight:1, letterSpacing:'-.02em'}}>{n}</div>
    <div className="meta" style={{marginTop:6,fontSize:12}}>{l}</div>
  </div>);
}
window.SignIn = SignIn;
