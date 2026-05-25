# ADR 006 — Entra ID groups overage handling

**Status:** Accepted
**Date:** 2026-05-08
**Deciders:** Platform team, Identity team

---

## Context

Authorisation in this app is push-down SQL: the `permissions_cache`
table stores one row per `(table, principal, privilege)`, and every
result-returning query joins `tables_metadata` against
`permissions_cache WHERE principal IN (user's Entra security groups)`.
The user's group set comes from the `groups` claim on their Entra ID
ID token, which the app reads on sign-in:

```python
st.session_state.user_groups = claims.get("groups", [])
```

This works for typical users. It silently fails for users with
**more than ~150 Entra security-group memberships**. Microsoft Entra
omits the inline `groups` claim in that case and adds a pointer:

```json
{
  "_claim_names":   { "groups": "src1" },
  "_claim_sources": { "src1": { "endpoint": "https://graph.microsoft.com/..." } }
}
```

Without explicit handling, `claims.get("groups", [])` returns `[]`,
the join returns no rows, and the user sees zero tables. This is
invisible in dev (small group counts) but a hard production failure
for enterprise tenants — IT admins, partner teams, anyone with broad
group membership.

A senior-developer audit (TODO #2) flagged this as a critical
production-failure mode worth fixing immediately.

### Alternatives considered

**Reduce Entra group emission to security-enabled-only.**
Entra has a token configuration option that only emits security
groups, raising the overage threshold. Helps but doesn't eliminate the
class of failure: tenants with >150 *security* groups (large
enterprises) still hit it. And it's a tenant-wide setting, not
something an app can rely on. Rejected as a sole solution.

**Switch the auth model to per-table grants in the app's own DB.**
Move authorisation out of Entra entirely and maintain our own
permission store. Far too invasive for the problem at hand and
abandons the "Entra is the source of truth" principle the app was
built on. Rejected.

**Read the access token's `groups` claim instead of the ID token.**
Same overage limit applies. Rejected.

**Document the limit and tell affected users to reduce their group
count.**
Not viable — a user can't reduce their own group count, and IT
admins can't either without security review.

---

## Decision

Detect the overage shape in `check_auth` and call Microsoft Graph's
`getMemberObjects` to fetch the transitive security-group list using
the access token MSAL has already produced.

### Detection

`src.auth_graph.has_groups_overage(claims)` returns True iff:

```python
"groups" not in claims and "groups" in (claims.get("_claim_names") or {})
```

Both conditions matter. A token with both inline groups and a
`_claim_names` entry (rare, but possible) still uses the inline list.

### Resolution

When overage is detected, `_resolve_user_groups` calls
`fetch_member_groups(access_token, user_oid)`:

```http
POST https://graph.microsoft.com/v1.0/me/getMemberObjects
Authorization: Bearer <access_token>
Content-Type: application/json

{"securityEnabledOnly": true}
```

Response is paginated via `@odata.nextLink` — first page is POST,
subsequent pages are GET against the absolute URL Graph returns. The
implementation caps pagination at 50 pages so a buggy server can't
loop forever. With the default 11 000-IDs-per-call from Graph that's
plenty.

### Caching

Results are cached in a process-level dict keyed by user OID with a
1 h TTL. Lock-protected because Streamlit's script-runner threads can
call into the cache concurrently.

`@st.cache_data` was deliberately rejected — it's
session-scoped, so each browser tab would force a fresh Graph call.
For a feature that exists to handle "this user is in many groups"
that's exactly the wrong default.

### Failure modes

Any error (network, 4xx including 403, 5xx) returns `[]` and logs a
warning. The user sees no tables. We **never silently grant access**
by returning a wider set on failure — fail-closed is the only correct
default for an authorisation layer.

### Cache invalidation

Two triggers:

1. **Sign-out** drops the user's cache entry (`_clear_auth_session`
   calls `clear_groups_cache(user_oid)`). Without this, "sign out and
   sign back in" would still read 1 h-stale group memberships and
   defeat the user's instinct for fixing access issues.

2. **Fresh OIDC code-exchange** clears the cache for the new user OID
   before resolving groups, so a successful sign-in always reflects
   current Entra state regardless of whether the previous session was
   signed out cleanly.

3. **Admin button** (`§ Group permissions cache → Flush groups
   cache`) drops every cached entry. Use case: an admin grants a user
   a new group, the user is still signed in, the admin clicks the
   button, the user reloads and sees the new tables.

### Required scope

Initially, `SCOPE` in `src/config.py` included `GroupMember.Read.All`. However, an audit (TODO #8) confirmed that `User.Read` is sufficient for the `/me/getMemberObjects` endpoint used here. To enforce the principle of least privilege, `GroupMember.Read.All` has been removed from `src/config.py`. Only `User.Read` and `email` are now requested.

---

## Consequences

**Positive:**

- Affected users (>150 groups) now see the catalog. Before this, they
  saw zero rows with no error message and no clear path to a fix.
- The cache invalidation invariants (sign-out, sign-in, admin flush)
  give admins three predictable ways to refresh permissions, all
  documented in the runbook and CLAUDE.md.
- Tests cover overage detection, pagination, all failure modes,
  cache hit/miss, and the three cache-clear paths.

**Negative:**

- One Microsoft Graph call per affected user per cache TTL — small
  cost. `getMemberObjects` returns up to 11 000 IDs per page; the
  cache amortises the cost across all renders for that user in the
  next hour.
- Pagination cap (50 pages, 550 000 IDs) is far above any real-world
  ceiling. If exceeded the daemon logs a warning and truncates; the
  user sees a subset of their groups. Acceptable given the contrived
  threshold.
- The admin "Flush groups cache" button affects every active user, not
  one. This is intentional — admins normally don't know which user
  needs the refresh, and the cost (one Graph call per active user on
  next render) is bounded.

**Out of scope:**

- SSO logout / forced silent re-auth on group-membership change.
  Group changes propagate at the next token refresh (≤1 h) plus the
  cache TTL (≤1 h). Combined with the explicit invalidation triggers
  above, the worst case is ~1 h delay; tighter latency would require
  webhooks or polling Graph, neither of which is justified at current
  scale.
- Pre-computing group lists at sync time. Group membership is a per-
  user concern at request time, not a property of the catalog data —
  caching it cluster-wide doesn't help.
