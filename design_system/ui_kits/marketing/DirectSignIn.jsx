// DirectSignIn — three states: fresh, remembered-account, signed-out banner.
function DirectSignIn() {
  const [email, setEmail] = React.useState('');
  // States: 'fresh' · 'remembered' · 'signed-out'
  const [state, setState] = React.useState('fresh');

  // Mock remembered identity
  const remembered = {
    name: 'Chlo\u00e9 Ouellet',
    email: 'chlo.ouellet@acme.com',
    initials: 'CO',
    groups: ['finance_all', 'marketing_read'],
    lastSeen: 'Apr 14, 09:42',
  };

  return (
    <section style={{padding:'72px 48px 64px'}}>
      <div style={{maxWidth:1040,margin:'0 auto',display:'grid',gridTemplateColumns:'1fr 1fr',gap:80,alignItems:'start'}}>
        {/* Left column — identity */}
        <div style={{paddingTop:24}}>
          <img src="../../assets/logo-wordmark.svg" alt="Data Dictionary" style={{height:56,marginBottom:40}}/>
          <div className="eyebrow" style={{marginBottom:16}}>§ Internal tool</div>
          <h1 style={{fontFamily:'var(--font-display)',fontSize:56,fontWeight:400,lineHeight:1.02,letterSpacing:'-.02em',margin:'0 0 18px'}}>
            Sign in to continue.
          </h1>
          <p className="p" style={{fontSize:16,color:'var(--ink-80)',maxWidth:'44ch'}}>
            Business Data Dictionary is an internal tool for Databricks Unity Catalog. Use your corporate account — you'll only see data your Unity Catalog grants allow.
          </p>
          <hr className="rule-soft" style={{margin:'32px 0 20px'}}/>
          <div style={{display:'flex',gap:28,fontFamily:'var(--font-mono)',fontSize:12,color:'var(--ink-60)',flexWrap:'wrap'}}>
            <span>2,341 tables · 18 schemas</span>
            <span>last synced 04:12 UTC</span>
          </div>
          {/* State switcher — demo-only */}
          <div style={{marginTop:40,display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
            <span className="meta" style={{fontSize:11}}>Preview state:</span>
            {[['fresh','Fresh'],['remembered','Remembered'],['signed-out','Just signed out']].map(([k,l])=> (
              <button key={k} onClick={()=>setState(k)} className={state===k?'btn':'btn sec'} style={{padding:'4px 10px',fontSize:11}}>{l}</button>
            ))}
          </div>
        </div>

        {/* Right column — sign-in card */}
        <aside style={{borderTop:'1px solid var(--ink)',paddingTop:28,position:'sticky',top:40}}>

          {/* Signed-out notice (appears above eyebrow) */}
          {state==='signed-out' && (
            <div style={{display:'flex',gap:10,alignItems:'flex-start',padding:'10px 12px',background:'var(--paper-deep)',border:'1px solid var(--ink-20)',borderLeft:'2px solid var(--accent)',borderRadius:2,marginBottom:20,fontSize:13,color:'var(--ink-80)'}}>
              <span style={{color:'var(--accent)',fontFamily:'var(--font-display)',fontSize:16,lineHeight:1,marginTop:1}}>†</span>
              <div>
                You were signed out for inactivity. Session ended <span className="mono" style={{fontSize:12}}>09:47 UTC</span>.
              </div>
            </div>
          )}

          <div className="eyebrow" style={{marginBottom:16}}>Sign in</div>

          {state==='remembered' ? (
            <>
              <h3 style={{fontFamily:'var(--font-display)',fontSize:26,fontWeight:500,letterSpacing:'-.015em',margin:'0 0 18px'}}>Welcome back.</h3>

              {/* Remembered identity card */}
              <div style={{border:'1px solid var(--ink)',padding:'16px 18px',display:'flex',gap:14,alignItems:'center',background:'var(--paper)',borderRadius:2,marginBottom:14}}>
                <div style={{width:44,height:44,borderRadius:'50%',background:'var(--paper-ink)',display:'flex',alignItems:'center',justifyContent:'center',fontFamily:'var(--font-display)',fontSize:16,color:'var(--ink)',flexShrink:0}}>{remembered.initials}</div>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontWeight:600,fontSize:14,color:'var(--ink)'}}>{remembered.name}</div>
                  <div className="mono" style={{fontSize:12,color:'var(--ink-60)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{remembered.email}</div>
                </div>
                <span style={{fontFamily:'var(--font-mono)',fontSize:10,padding:'2px 6px',border:'1px solid #C7D3C0',background:'var(--forest-wash)',color:'var(--forest)',borderRadius:2,letterSpacing:'.06em'}}>REMEMBERED</span>
              </div>

              <div className="meta" style={{fontSize:11,marginBottom:14,fontFamily:'var(--font-mono)'}}>
                Groups: {remembered.groups.join(' · ')} &nbsp;·&nbsp; last seen {remembered.lastSeen}
              </div>

              <button className="btn" style={{width:'100%',padding:'14px 18px',fontSize:15,display:'flex',alignItems:'center',justifyContent:'center',gap:10}}>
                <svg width="16" height="16" viewBox="0 0 23 23" fill="none"><rect x="1" y="1" width="10" height="10" fill="#F25022"/><rect x="12" y="1" width="10" height="10" fill="#7FBA00"/><rect x="1" y="12" width="10" height="10" fill="#00A4EF"/><rect x="12" y="12" width="10" height="10" fill="#FFB900"/></svg>
                Continue as Chlo&eacute;
              </button>

              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginTop:14,fontSize:13}}>
                <button onClick={()=>setState('fresh')} className="btn ghost" style={{fontSize:13}}>Use a different account</button>
                <button className="btn ghost" style={{fontSize:13,color:'var(--ink-60)'}}>Forget this account</button>
              </div>
            </>
          ) : (
            <>
              <h3 style={{fontFamily:'var(--font-display)',fontSize:26,fontWeight:500,letterSpacing:'-.015em',margin:'0 0 22px'}}>
                {state==='signed-out' ? 'Sign back in' : 'Use your corporate account'}
              </h3>

              <label style={{display:'block',fontSize:12,color:'var(--ink-60)',marginBottom:6}}>Work email</label>
              <input value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@acme.com"
                style={{width:'100%',boxSizing:'border-box',border:'1px solid var(--ink-20)',background:'var(--paper)',padding:'11px 12px',fontSize:14,borderRadius:2,fontFamily:'var(--font-sans)',color:'var(--ink)',marginBottom:16}}/>

              <button className="btn" style={{width:'100%',padding:'14px 18px',fontSize:15,display:'flex',alignItems:'center',justifyContent:'center',gap:10}}>
                <svg width="16" height="16" viewBox="0 0 23 23" fill="none"><rect x="1" y="1" width="10" height="10" fill="#F25022"/><rect x="12" y="1" width="10" height="10" fill="#7FBA00"/><rect x="1" y="12" width="10" height="10" fill="#00A4EF"/><rect x="12" y="12" width="10" height="10" fill="#FFB900"/></svg>
                Sign in with Entra ID
              </button>

              <div style={{margin:'18px 0',display:'flex',alignItems:'center',gap:10,color:'var(--ink-40)',fontSize:11,fontFamily:'var(--font-mono)',letterSpacing:'.08em',textTransform:'uppercase'}}>
                <span style={{flex:1,borderTop:'1px solid var(--ink-10)'}}/>or<span style={{flex:1,borderTop:'1px solid var(--ink-10)'}}/>
              </div>

              <button className="btn sec" style={{width:'100%',padding:'12px 18px',fontSize:14,display:'flex',alignItems:'center',justifyContent:'center',gap:8}}>
                <Icon name="lock" size={14}/> Sign in with SSO
              </button>

              <label style={{display:'flex',alignItems:'center',gap:8,marginTop:18,fontSize:13,color:'var(--ink-80)',cursor:'pointer'}}>
                <input type="checkbox" defaultChecked style={{accentColor:'#B8362A'}}/>
                Remember this account on this device
              </label>
            </>
          )}

          <p className="meta" style={{marginTop:18,fontSize:12}}>
            Access is permission-trimmed against Unity Catalog grants. By signing in you agree to the <a href="#">data access policy</a>.
          </p>

          <div style={{marginTop:24,paddingTop:16,borderTop:'1px solid var(--ink-10)',display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:11,color:'var(--ink-40)'}}>
            <span>SSO · Entra ID tenant</span>
            <span>v0.3.0</span>
          </div>
        </aside>
      </div>
    </section>
  );
}
window.DirectSignIn = DirectSignIn;
